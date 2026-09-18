#!/usr/bin/env python3
"""
Gera crachás de identificação dos participantes (um por competidor) em PDFs
agrupados por campus.

Lê nomes e times direto do CSV de inscrições — não depende de usuarios.txt, já
que o crachá não exibe credenciais BOCA.  Salva um PDF por campus no diretório
de saída.  Com --send envia cada PDF ao coordenador via `gws gmail +send --attach`.

Com --combined gera, em vez dos PDFs por campus, um único PDF contendo os crachás de
todos os campi (ou do campus filtrado, se --campus for usado).  Nesse modo o envio de
emails (--send) é ignorado, pois não há um único coordenador para o PDF combinado.

Cada crachá tem 95mm (largura) x 80mm (altura): nome do participante como informação
principal, seguido do nome do time e do campus de origem, além do nome e data do
evento e do logo do InterIF no canto inferior direito.

Uso:
    uv run python gerar_crachas.py   [--csv equipes_interif.csv]
                                      [--campi assets/ifsp_campi.csv]
                                      [--campus SIGLA]
                                      [-o crachas/]
                                      [-s / --send]
                                      [--dry-run]
                                      [--combined]
"""

import argparse
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from tabulate import tabulate

from config import (
    CRACHA_BODY_TEMPLATE,
    CRACHA_DATA_EVENTO,
    CRACHA_SUBJECT,
    TITULO_EVENTO,
)
from email_utils import send_email
from interif_core import (
    CAMPI_FILE,
    CSV_FILE,
    _participantes_de,
    load_campi,
    load_teams,
)

# ── Caminhos padrão ───────────────────────────────────────────────────────────

_HERE = Path(__file__).parent
_ASSETS = _HERE / "assets"
LOGO_PATH = _ASSETS / "logo.png"

# Sufixo aplicado a todo nome de PDF gerado, para diferenciar de etiquetas/placas
# quando os três scripts escrevem no mesmo diretório de saída.
_TIPO = "Crachas"

# ── Layout dos crachás ────────────────────────────────────────────────────────

_COLS = 2
_ROWS = 3
_CRACHA_W = 90 * mm
_CRACHA_H = 60 * mm

_BORDA_LARGURA = 0.75  # espessura da borda do crachá (pt)
_SEPARADOR_LARGURA = 0.4  # espessura da linha separadora interna (pt)

# Recuo simétrico entre a marca de corte (dimensão real do crachá) e a borda
# desenhada, para que o conteúdo fique centralizado no crachá já cortado.
_PAD_X = 5  # pt, aplicado à esquerda e à direita
_PAD_Y = 2.5  # pt, aplicado em cima e embaixo

# Largura útil disponível para o texto dentro do crachá (mesma usada para
# calcular tanto o tamanho de fonte comum quanto o desenho de cada crachá).
_LARGURA_UTIL = _CRACHA_W - 2 * _PAD_X - 16

# ── Marcas de corte ────────────────────────────────────────────────────────────

_MARCA_CORTE_LARGURA = 0.3  # espessura das marcas de corte (pt)
_MARCA_CORTE_COMPRIMENTO = 3 * mm  # comprimento de cada tracinho
_MARCA_CORTE_GAP = 1 * mm  # distância entre o canto do crachá e o início da marca

# ── Tipos ─────────────────────────────────────────────────────────────────────


@dataclass
class Cracha:
    """Dados de um crachá individual (um por participante/competidor)."""

    nome: str
    nome_equipe: str
    campus: str
    sigla: str
    coord_nome: str
    coord_email: str


# ── Filtro por campus ─────────────────────────────────────────────────────────


def _filtrar_teams_por_sigla(teams: list[dict], sigla: str, campi: dict[str, str]) -> list[dict]:
    """
    Filtra linhas do CSV por campus, comparando a sigla (case-insensitive).
    Levanta ValueError se a sigla não existir no mapeamento de campi.
    """
    alvo = sigla.strip().upper()
    if alvo not in {s.upper() for s in campi.values()}:
        raise ValueError(f"sigla de campus desconhecida: {sigla!r}")
    return [t for t in teams if campi.get(t["campus"], "").upper() == alvo]


# ── Helpers de nome de arquivo ────────────────────────────────────────────────


def _limpar_nome(texto: str) -> str:
    """Remove colchetes, acentos e caracteres inválidos; substitui espaços por _."""
    texto = texto.strip().replace("[", "").replace("]", "")
    texto = unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("ASCII")
    return texto.replace(" ", "_").replace("/", "-")


# ── Ajuste automático de tamanho de fonte ─────────────────────────────────────


def _ajustar_fonte(
    texto: str,
    largura_max: float,
    fonte: str = "Helvetica-Bold",
    tamanho_max: int = 20,
    tamanho_min: int = 8,
    passo: int = 1,
) -> int:
    """Devolve o maior tamanho de fonte que faz `texto` caber em `largura_max`."""
    for tamanho in range(tamanho_max, tamanho_min - 1, -passo):
        if stringWidth(texto, fonte, tamanho) <= largura_max:
            return tamanho
    return tamanho_min


def _tamanho_comum(
    textos: list[str],
    fonte: str = "Helvetica-Bold",
    tamanho_max: int = 20,
    tamanho_min: int = 8,
) -> int:
    """
    Devolve o maior tamanho de fonte que faz TODOS os textos caberem em
    `_LARGURA_UTIL` — ou seja, o tamanho ditado pelo texto mais longo do lote.
    Usado para que nome e time tenham sempre o mesmo tamanho em todos os
    crachás gerados numa mesma execução, em vez de variar crachá a crachá.
    """
    if not textos:
        return tamanho_max
    return min(_ajustar_fonte(t, _LARGURA_UTIL, fonte, tamanho_max, tamanho_min) for t in textos)


# ── Marcas de corte ────────────────────────────────────────────────────────────


def _desenhar_marcas_corte(c: canvas.Canvas, x: float, y: float, w: float, h: float) -> None:
    """
    Desenha tracinhos de corte nos 4 cantos do retângulo (x, y, w, h) — dimensões
    reais do crachá —, apontando para fora, com um pequeno vão até o canto para
    não interferir na borda desenhada do crachá.
    """
    d = _MARCA_CORTE_COMPRIMENTO
    g = _MARCA_CORTE_GAP

    c.setLineWidth(_MARCA_CORTE_LARGURA)

    for cx, sinal_x in ((x, -1), (x + w, 1)):
        for cy, sinal_y in ((y, -1), (y + h, 1)):
            # Tracinho horizontal, afastando-se do canto
            c.line(cx + sinal_x * g, cy, cx + sinal_x * (g + d), cy)
            # Tracinho vertical, afastando-se do canto
            c.line(cx, cy + sinal_y * g, cx, cy + sinal_y * (g + d))


# ── Geração de PDF de crachás ─────────────────────────────────────────────────


def gerar_pdf_campus(
    crachas: list[Cracha],
    caminho_pdf: Path,
    *,
    tam_nome: int,
    tam_time: int,
) -> None:
    """
    Gera um PDF de crachás para uma lista de participantes.

    `tam_nome` e `tam_time` são fixos e devem ser calculados uma única vez (via
    `_tamanho_comum`) sobre todo o lote de crachás da execução, para que o
    tamanho da fonte não varie de crachá para crachá.
    """
    width, height = A4

    x_margin = (width - _COLS * _CRACHA_W) / 2
    y_margin = (height - _ROWS * _CRACHA_H) / 2

    logo = ImageReader(str(LOGO_PATH)) if LOGO_PATH.exists() else None
    logo_w = 12 * mm
    if logo:
        orig_w, orig_h = logo.getSize()
        logo_h = logo_w * orig_h / orig_w
    else:
        logo_h = logo_w

    c = canvas.Canvas(str(caminho_pdf), pagesize=A4)

    for i, cracha in enumerate(crachas):
        col = i % _COLS
        row = (i // _COLS) % _ROWS

        # Nova página a cada grade completa (exceto a primeira)
        if i != 0 and i % (_COLS * _ROWS) == 0:
            c.showPage()

        x = x_margin + col * _CRACHA_W
        y = height - (y_margin + (row + 1) * _CRACHA_H)

        inner_w = _CRACHA_W - 2 * _PAD_X
        inner_h = _CRACHA_H - 2 * _PAD_Y
        bx = x + _PAD_X
        by = y + _PAD_Y

        # Marcas de corte nas dimensões reais do crachá (95mm x 80mm)
        _desenhar_marcas_corte(c, x, y, _CRACHA_W, _CRACHA_H)

        # Borda arredondada (centralizada dentro da área de corte)
        c.setLineWidth(_BORDA_LARGURA)
        c.roundRect(bx, by, inner_w, inner_h, 6, stroke=1, fill=0)

        centro_x = bx + inner_w / 2

        # ── Cabeçalho: nome e data do evento ────────────────────────────────
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(centro_x, by + inner_h - 16, TITULO_EVENTO)
        c.setFont("Helvetica", 7)
        c.drawCentredString(centro_x, by + inner_h - 25, CRACHA_DATA_EVENTO)

        c.setLineWidth(_SEPARADOR_LARGURA)
        c.line(bx + 10, by + inner_h - 31, bx + inner_w - 10, by + inner_h - 31)

        # ── Informação principal: nome do participante ──────────────────────
        largura_util = inner_w - 16
        c.setFont("Helvetica-Bold", tam_nome)
        c.drawCentredString(centro_x, by + inner_h / 2 + 4, cracha.nome)

        # ── Nome do time ─────────────────────────────────────────────────────
        c.setFont("Helvetica-Bold", tam_time)
        c.drawCentredString(centro_x, by + inner_h / 2 - 14, cracha.nome_equipe)

        # ── Campus de origem ─────────────────────────────────────────────────
        campus_label = f"IFSP - {cracha.sigla or cracha.campus}"
        tam_campus = _ajustar_fonte(campus_label, largura_util, "Helvetica", 11, 7)
        c.setFont("Helvetica", tam_campus)
        c.drawCentredString(centro_x, by + inner_h / 2 - 27, campus_label)

        # ── Logo (canto inferior direito) ───────────────────────────────────
        if logo:
            c.drawImage(
                logo,
                bx + inner_w - logo_w - 6,
                by + 6,
                width=logo_w,
                height=logo_h,
                mask="auto",
            )

    c.save()


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Gera crachás de identificação dos participantes em PDFs agrupados por "
            "campus. Lê nomes e times direto do CSV de inscrições."
        )
    )
    parser.add_argument(
        "--csv",
        default=str(CSV_FILE),
        metavar="ARQUIVO",
        help=f"CSV de equipes (padrão: {CSV_FILE.name})",
    )
    parser.add_argument(
        "--campi",
        default=str(CAMPI_FILE),
        metavar="ARQUIVO",
        help=f"Mapeamento campus→sigla (padrão: {CAMPI_FILE})",
    )
    parser.add_argument(
        "--campus",
        default=None,
        metavar="SIGLA",
        help="Processa apenas o campus informado (sigla, ex.: SPO). Padrão: todos.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="crachas",
        metavar="DIR",
        help="Diretório de saída dos PDFs (padrão: crachas/)",
    )
    parser.add_argument(
        "-s",
        "--send",
        action="store_true",
        help="Envia cada PDF ao coordenador do campus via gws gmail",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Gera os PDFs mas não envia emails (implica --send em modo simulado)",
    )
    parser.add_argument(
        "--combined",
        action="store_true",
        help=(
            "Gera um único PDF com todos os crachás de todos os campi "
            "(ou do campus filtrado por --campus), em vez de PDFs separados "
            "por campus. Ignora --send."
        ),
    )
    return parser.parse_args()


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    args = parse_args()

    csv_path = Path(args.csv)
    campi_path = Path(args.campi)
    output_dir = Path(args.output)

    # Verifica arquivos de entrada
    for p in (csv_path, campi_path):
        if not p.exists():
            print(f"Erro: arquivo não encontrado: {p}", file=sys.stderr)
            sys.exit(1)

    modo = "dry-run" if args.dry_run else ("envio real" if args.send else "somente geração")
    print(f"Geração de crachás - {TITULO_EVENTO}")
    print(f"CSV:      {csv_path.resolve()}")
    print(f"Campi:    {campi_path.resolve()}")
    print(f"Saída:    {output_dir.resolve()}")
    print(f"Modo:     {modo}")

    # Carrega dados
    campi = load_campi(campi_path)
    teams_csv = load_teams(csv_path)

    print(f"{len(teams_csv)} equipe(s) no CSV.\n")

    # Filtro opcional por campus (sigla)
    if args.campus:
        try:
            teams_csv = _filtrar_teams_por_sigla(teams_csv, args.campus, campi)
        except ValueError as exc:
            print(f"Erro: {exc}", file=sys.stderr)
            sys.exit(1)
        if not teams_csv:
            print(f"Nenhuma equipe encontrada para o campus {args.campus.upper()!r}.")
            sys.exit(0)
        print(f"Filtrando apenas o campus {args.campus.upper()!r}: {len(teams_csv)} equipe(s).\n")

    # Explode equipes em crachás individuais (um por participante)
    crachas: list[Cracha] = []
    sem_participantes = 0
    for team in teams_csv:
        participantes = _participantes_de(team)
        if not participantes:
            sem_participantes += 1
            continue
        campus = team["campus"]
        sigla = campi.get(campus, "")
        for p in participantes:
            crachas.append(
                Cracha(
                    nome=p["nome"],
                    nome_equipe=team["nome_equipe"],
                    campus=campus,
                    sigla=sigla,
                    coord_nome=team["coord_nome"],
                    coord_email=team["coord_email"],
                )
            )
    if sem_participantes:
        print(f"Aviso: {sem_participantes} equipe(s) sem participantes — sem crachá.\n")

    # Tamanho de fonte único (nome e time) para todos os crachás desta execução —
    # calculado a partir do texto mais longo do lote, para não variar crachá a crachá.
    tam_nome = _tamanho_comum([cr.nome for cr in crachas], "Helvetica-Bold", 20, 10)
    tam_time = _tamanho_comum([cr.nome_equipe for cr in crachas], "Helvetica-Bold", 13, 8)
    print(f"Fonte nome: {tam_nome}pt | Fonte time: {tam_time}pt\n")

    # Cria diretório de saída
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Modo combinado: um único PDF com todos os crachás ─────────────────────
    if args.combined:
        if args.send:
            print(
                "Aviso: --send é ignorado em modo --combined "
                "(não há um coordenador único para o PDF combinado).\n"
            )

        crachas_ordenados = sorted(
            crachas, key=lambda cr: (cr.campus or cr.sigla or "", cr.nome_equipe, cr.nome)
        )

        nome_arquivo = _limpar_nome("IFSP_-_Todos_os_Campi") + f"-{_TIPO}.pdf"
        caminho_pdf = output_dir / nome_arquivo
        gerar_pdf_campus(crachas_ordenados, caminho_pdf, tam_nome=tam_nome, tam_time=tam_time)

        print(f"OK combinado: {caminho_pdf} ({len(crachas_ordenados)} crachá(s))")

        print()
        rows_combinado: list[list[str | int]] = [
            ["Participantes", len(crachas_ordenados)],
            ["Equipes", len(teams_csv)],
            ["Campi", len({cr.campus or cr.sigla for cr in crachas_ordenados})],
            ["PDFs gerados", 1],
        ]
        print("Resumo")
        print(tabulate(rows_combinado, tablefmt="simple"))
        return

    # Agrupa por campus
    por_campus: dict[str, list[Cracha]] = defaultdict(list)
    for cracha in crachas:
        por_campus[cracha.campus or cracha.sigla].append(cracha)

    n_pdfs = 0
    n_emails = 0

    for campus, grupo in por_campus.items():
        nome_arquivo = _limpar_nome(f"IFSP_-_{campus}") + f"-{_TIPO}.pdf"
        caminho_pdf = output_dir / nome_arquivo

        gerar_pdf_campus(grupo, caminho_pdf, tam_nome=tam_nome, tam_time=tam_time)
        n_pdfs += 1

        print(f"OK: {campus} -> {caminho_pdf} ({len(grupo)} crachá(s))")

        # Envio opcional
        if args.send or args.dry_run:
            coord_email = grupo[0].coord_email if grupo else ""
            coord_nome = grupo[0].coord_nome.strip().split()[0] if grupo and grupo[0].coord_nome.strip() else "Coordenador(a)"

            if not coord_email:
                print(f"  Aviso: sem email de coordenador para {campus} — envio ignorado")
            else:
                body = CRACHA_BODY_TEMPLATE.format(nome=coord_nome, campus=campus)
                send_email(
                    coord_email,
                    f"{CRACHA_SUBJECT} — {campus}",
                    body,
                    attach=caminho_pdf,
                    dry_run=args.dry_run,
                )
                n_emails += 1

    # Resumo final
    print()
    rows: list[list[str | int]] = [
        ["Participantes", len(crachas)],
        ["Equipes", len(teams_csv)],
        ["Campus", len(por_campus)],
        ["PDFs", n_pdfs],
    ]
    if args.dry_run:
        rows.append(["Emails", f"dry-run ({n_emails} simulado(s))"])
    elif args.send:
        rows.append(["Emails", f"{n_emails} enviado(s)"])

    print("Resumo")
    print(tabulate(rows, tablefmt="simple"))


if __name__ == "__main__":
    main()
