#!/usr/bin/env python3
"""
Gera listas de presença (PDF A4 retrato) para assinatura dos participantes,
agrupadas por campus.

Lê todos os dados (equipes, participantes com prontuário/CPF, coordenador e
responsável) do CSV de inscrições — única fonte da verdade.  Cada página traz, no
canto superior direito, os logos do InterIF e do IFSP, e o cabeçalho com o título do
evento e o prazo de envio; no rodapé, "Página X de Y".  Cada participante aparece com
prontuário e CPF entre parênteses para conferência, e ao final há um bloco "Correções"
com linhas pautadas.  Salva um PDF por campus no diretório de saída.  Com --send envia
cada PDF ao coordenador do campus via `gws gmail +send --attach`.

Uso:
    uv run python gerar_lista_presenca.py [--csv equipes_interif.csv]
                                          [--campi assets/ifsp_campi.csv]
                                          [--campus SIGLA]
                                          [-o listas_presenca/]
                                          [-s / --send]
                                          [--dry-run]
"""

import argparse
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import getAscent
from reportlab.pdfgen import canvas
from tabulate import tabulate

from config import (
    DATA_EVENTO,
    EMAIL_INTERIF,
    LISTA_BODY_TEMPLATE,
    LISTA_PRAZO_DIAS,
    LISTA_SUBJECT,
    TITULO_EVENTO,
)
from email_utils import send_email
from interif_core import (
    CAMPI_FILE,
    CSV_FILE,
    CredencialEquipe,
    credenciais_de_csv,
    filtrar_por_sigla,
    load_campi,
    load_teams,
)

# ── Caminhos padrão ───────────────────────────────────────────────────────────

_HERE = Path(__file__).parent
_ASSETS = _HERE / "assets"
LOGO_INTERIF = _ASSETS / "logo.png"
LOGO_IFSP = _ASSETS / "IFSP_Logo.jpg"

# ── Layout da página ──────────────────────────────────────────────────────────

_MARGEM_ESQ = 20 * mm
_MARGEM_DIR = 15 * mm
_MARGEM_TOPO = 15 * mm
_MARGEM_BASE = 20 * mm

_LOGO_ALT = 20 * mm  # 2 cm de altura, conforme solicitado
_LOGO_GAP = 5 * mm  # espaço entre os dois logos

# Grade de participantes, no estilo "relação de alunos" (ver exemplo.pdf):
# faixa cinza com o nome da equipe + tabela fina com colunas fixas.
_COL_DEFS: list[tuple[str, float]] = [
    ("Matrícula", 24 * mm),
    ("CPF", 28 * mm),
    ("Nome", 63 * mm),
    ("Assinatura", 60 * mm),
]
_ROW_H = 5.5 * mm  # altura de cada linha da tabela
_BAND_H = 7 * mm  # altura da faixa com o nome da equipe
_GAP_BLOCO = _ROW_H / 2  # meia linha entre blocos de equipe
_CELL_PAD = 2 * mm  # recuo do texto dentro da célula

_FILL_BAND = 0.88  # cinza da faixa do nome da equipe
_FILL_HEADER = 0.80  # cinza do cabeçalho de colunas
_GRID_GRAY = 0.55  # cor das linhas da grade
_GRID_LW = 0.4  # espessura das linhas da grade

_LINHA_ASSINATURA = 6 * mm  # altura das linhas de assinatura (equipe local / correções)

_FONTE_EQUIPE = 14  # nome da equipe (negrito)
_FONTE_SECAO = 12  # cabeçalhos "Equipe local" e "Correções"
_FONTE_TABELA = 8  # texto da grade (igual ao exemplo.pdf)
_FONTE_ASSINATURA = 9  # rótulos das assinaturas da equipe local
_FONTE_RODAPE = 8  # "Página X de Y"
_FONTE_CORRECOES = 9  # instrução do bloco de correções


# ── Helpers de nome de arquivo ────────────────────────────────────────────────


def _limpar_nome(texto: str) -> str:
    """Remove colchetes, acentos e caracteres inválidos; substitui espaços por _."""
    texto = texto.strip().replace("[", "").replace("]", "")
    texto = unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("ASCII")
    return texto.replace(" ", "_").replace("/", "-")


def _data_limite() -> str:
    """DATA_EVENTO + LISTA_PRAZO_DIAS, formatada como dd/mm/aaaa."""
    base = datetime.strptime(DATA_EVENTO, "%Y-%m-%d")
    return (base + timedelta(days=LISTA_PRAZO_DIAS)).strftime("%d/%m/%Y")


# ── Logos ─────────────────────────────────────────────────────────────────────


def _carregar_logo(path: Path, altura: float) -> tuple[ImageReader, float, float] | None:
    """Devolve (ImageReader, largura, altura) preservando a proporção, ou None."""
    if not path.exists():
        return None
    img = ImageReader(str(path))
    w, h = img.getSize()
    return img, altura * w / h, altura


# ── Canvas com rodapé "Página X de Y" ─────────────────────────────────────────


class _NumberedCanvas(canvas.Canvas):
    """
    Canvas que adia o desenho das páginas até `save()`, quando o total já é
    conhecido, e estampa "Página X de Y" centralizado no rodapé de cada página.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_states: list[dict] = []

    def showPage(self) -> None:
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            self._desenhar_rodape(total)
            super().showPage()
        super().save()

    def _desenhar_rodape(self, total: int) -> None:
        width, _ = A4
        self.setFont("Helvetica", _FONTE_RODAPE)
        self.drawCentredString(width / 2, 10 * mm, f"Página {self._pageNumber} de {total}")


def _quebrar_texto(
    c: canvas.Canvas, texto: str, fonte: str, tamanho: float, largura_max: float
) -> list[str]:
    """Quebra `texto` em linhas que cabem em `largura_max` na fonte dada."""
    linhas: list[str] = []
    atual = ""
    for palavra in texto.split():
        teste = f"{atual} {palavra}".strip()
        if c.stringWidth(teste, fonte, tamanho) <= largura_max:
            atual = teste
        else:
            if atual:
                linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


# ── Grade de participantes (estilo "relação de alunos") ───────────────────────


def _col_bounds() -> list[tuple[float, float]]:
    """Devolve [(x_esquerda, largura), …] de cada coluna, a partir da margem."""
    bounds: list[tuple[float, float]] = []
    x = _MARGEM_ESQ
    for _, w in _COL_DEFS:
        bounds.append((x, w))
        x += w
    return bounds


def _grade_largura() -> float:
    return sum(w for _, w in _COL_DEFS)


def _desenhar_linha_grade(
    c: canvas.Canvas,
    y_topo: float,
    valores: list[str],
    *,
    bold: bool = False,
    fill: float | None = None,
    align: str = "left",
) -> float:
    """Desenha uma linha (4 células) da grade e devolve o novo y (base da linha)."""
    fonte = "Helvetica-Bold" if bold else "Helvetica"
    base = y_topo - _ROW_H
    ty = base + (_ROW_H - _FONTE_TABELA) / 2 + _FONTE_TABELA * 0.18
    for (x, w), texto in zip(_col_bounds(), valores, strict=True):
        if fill is not None:
            c.setFillGray(fill)
            c.rect(x, base, w, _ROW_H, stroke=0, fill=1)
        c.setStrokeGray(_GRID_GRAY)
        c.setLineWidth(_GRID_LW)
        c.rect(x, base, w, _ROW_H, stroke=1, fill=0)
        if texto:
            c.setFillGray(0)
            c.setFont(fonte, _FONTE_TABELA)
            if align == "center":
                c.drawCentredString(x + w / 2, ty, texto)
            else:
                c.drawString(x + _CELL_PAD, ty, texto)
    return base


def _desenhar_faixa(c: canvas.Canvas, y_topo: float, texto: str, *, tam: int) -> float:
    """Desenha a faixa cinza (nome da equipe ou seção) e devolve o novo y."""
    largura = _grade_largura()
    base = y_topo - _BAND_H
    c.setFillGray(_FILL_BAND)
    c.rect(_MARGEM_ESQ, base, largura, _BAND_H, stroke=0, fill=1)
    c.setStrokeGray(_GRID_GRAY)
    c.setLineWidth(_GRID_LW)
    c.rect(_MARGEM_ESQ, base, largura, _BAND_H, stroke=1, fill=0)
    c.setFillGray(0)
    c.setFont("Helvetica-Bold", tam)
    ty = base + (_BAND_H - tam) / 2 + tam * 0.2
    c.drawString(_MARGEM_ESQ + _CELL_PAD, ty, texto)
    return base


# ── Desenho do cabeçalho (repetido em todas as páginas) ───────────────────────


def _desenhar_cabecalho(
    c: canvas.Canvas, width: float, height: float, data_limite: str, campus: str = ""
) -> float:
    """
    Desenha logos (canto superior direito), título, nome do campus e instrução
    de envio.  Devolve a coordenada y onde o conteúdo da página deve começar.
    """
    topo_logo = height - _MARGEM_TOPO
    base_logo = topo_logo - _LOGO_ALT

    # Logos lado-a-lado, alinhados à direita: InterIF, depois IFSP.
    logos = [
        _carregar_logo(LOGO_INTERIF, _LOGO_ALT),
        _carregar_logo(LOGO_IFSP, _LOGO_ALT),
    ]
    logos = [logo for logo in logos if logo is not None]
    if logos:
        largura_total = sum(w for _, w, _ in logos) + _LOGO_GAP * (len(logos) - 1)
        x = width - _MARGEM_DIR - largura_total
        for img, w, h in logos:
            c.drawImage(img, x, base_logo, width=w, height=h, mask="auto")
            x += w + _LOGO_GAP

    # Título (14 pt) no topo da página, alinhado com o topo dos logos.
    y = topo_logo - getAscent("Helvetica-Bold", 14)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(_MARGEM_ESQ, y, f"Lista de presença do {TITULO_EVENTO}")

    # Nome do campus (11 pt) logo abaixo do título.
    if campus:
        y -= 6 * mm
        c.setFont("Helvetica-Bold", 11)
        c.drawString(_MARGEM_ESQ, y, f"Campus {campus}")

    # Instrução de envio (10 pt) abaixo da faixa dos logos, com a data em negrito.
    y = base_logo - 4 * mm
    pre = f"Após o término, digitalizar e enviar por email para {EMAIL_INTERIF} até "
    suf = "."
    c.setFont("Helvetica", 10)
    c.drawString(_MARGEM_ESQ, y, pre)
    x = _MARGEM_ESQ + c.stringWidth(pre, "Helvetica", 10)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, data_limite)
    x += c.stringWidth(data_limite, "Helvetica-Bold", 10)
    c.setFont("Helvetica", 10)
    c.drawString(x, y, suf)

    # Linha separadora abaixo do cabeçalho.
    y -= 5 * mm
    c.setLineWidth(0.5)
    c.line(_MARGEM_ESQ, y, width - _MARGEM_DIR, y)

    return y - 8 * mm


def _linha_assinatura(c: canvas.Canvas, x: float, y: float, x_dir: float, rotulo: str) -> None:
    """Desenha '{rotulo}: ____' com uma linha contínua até a margem direita."""
    c.setFont("Helvetica", _FONTE_ASSINATURA)
    texto = f"{rotulo}: "
    c.drawString(x, y, texto)
    inicio_linha = x + c.stringWidth(texto, "Helvetica", _FONTE_ASSINATURA)
    c.setLineWidth(0.5)
    c.line(inicio_linha, y - 1, x_dir, y - 1)


# ── Geração de PDF ────────────────────────────────────────────────────────────


def gerar_pdf_campus(credenciais: list[CredencialEquipe], caminho_pdf: Path) -> None:
    """Gera o PDF da lista de presença de um campus (uma ou mais páginas A4)."""
    width, height = A4
    data_limite = _data_limite()
    x_dir = width - _MARGEM_DIR

    campus = credenciais[0].campus if credenciais else ""

    c = _NumberedCanvas(str(caminho_pdf), pagesize=A4)

    def abrir_pagina() -> float:
        """Cabeçalho do evento + cabeçalho de colunas; devolve o y inicial."""
        yy = _desenhar_cabecalho(c, width, height, data_limite, campus)
        return _desenhar_linha_grade(
            c, yy, [nome for nome, _ in _COL_DEFS], bold=True, fill=_FILL_HEADER, align="center"
        )

    def nova_pagina() -> float:
        c.showPage()
        return abrir_pagina()

    y = abrir_pagina()

    # ── Equipes ────────────────────────────────────────────────────────────────
    for cred in credenciais:
        participantes = cred.participantes or [{}]
        # Mantém o bloco inteiro (faixa + linhas) numa mesma página.
        bloco = _BAND_H + len(participantes) * _ROW_H + _GAP_BLOCO
        if y - bloco < _MARGEM_BASE:
            y = nova_pagina()

        y = _desenhar_faixa(c, y, cred.nome_equipe, tam=_FONTE_EQUIPE)
        for p in participantes:
            valores = [
                p.get("prontuario", "").strip(),
                p.get("cpf", "").strip(),
                p.get("nome", "").strip(),
                "",  # assinatura — espaço em branco
            ]
            y = _desenhar_linha_grade(c, y, valores)
        y -= _GAP_BLOCO

    # ── Assinatura da equipe local (coordenador + responsáveis pelas equipes) ────
    coord_nome = credenciais[0].coord_nome.strip() if credenciais else ""

    # Responsáveis distintos do campus (os "técnicos"), na ordem de aparição.
    # Deduplica de forma insensível a acentos/maiúsculas/espaços, pois o CSV
    # costuma trazer o mesmo nome grafado de formas diferentes.
    def _chave(nome: str) -> str:
        nome = unicodedata.normalize("NFKD", nome).encode("ASCII", "ignore").decode("ASCII")
        return " ".join(nome.lower().split())

    vistos: set[str] = {_chave(coord_nome)}
    responsaveis: list[str] = []
    for cred in credenciais:
        nome = cred.resp_nome.strip()
        chave = _chave(nome)
        if nome and chave not in vistos:
            vistos.add(chave)
            responsaveis.append(nome)

    n_linhas = (1 if coord_nome else 0) + len(responsaveis)
    bloco_local = _BAND_H + 6 * mm + n_linhas * _LINHA_ASSINATURA + _GAP_BLOCO
    if y - bloco_local < _MARGEM_BASE:
        y = nova_pagina()

    y -= 2 * mm
    y = _desenhar_faixa(c, y, f"Equipe local — campus {campus}", tam=_FONTE_SECAO)
    y -= 6 * mm

    c.setStrokeGray(0)
    if coord_nome:
        _linha_assinatura(c, _MARGEM_ESQ + 4 * mm, y, x_dir, f"{coord_nome} (Coordenador(a))")
        y -= _LINHA_ASSINATURA

    for nome in responsaveis:
        _linha_assinatura(c, _MARGEM_ESQ + 4 * mm, y, x_dir, f"{nome} (Responsável)")
        y -= _LINHA_ASSINATURA

    # ── Correções ────────────────────────────────────────────────────────────────
    instrucao = (
        "Caso o prontuário ou o CPF de algum participante esteja incorreto, "
        "por favor indique as correções necessárias no espaço abaixo."
    )
    linhas_inst = _quebrar_texto(c, instrucao, "Helvetica", _FONTE_CORRECOES, x_dir - _MARGEM_ESQ)
    n_linhas_corr = 4
    bloco_corr = (
        3 * mm
        + _BAND_H
        + 6 * mm
        + len(linhas_inst) * 5 * mm
        + 2 * mm
        + n_linhas_corr * _LINHA_ASSINATURA
    )
    if y - bloco_corr < _MARGEM_BASE:
        y = nova_pagina()

    y -= 3 * mm
    y = _desenhar_faixa(c, y, "Correções", tam=_FONTE_SECAO)
    y -= 6 * mm

    c.setFillGray(0)
    c.setFont("Helvetica", _FONTE_CORRECOES)
    for linha in linhas_inst:
        c.drawString(_MARGEM_ESQ, y, linha)
        y -= 5 * mm
    y -= 2 * mm

    c.setStrokeGray(0)
    for _ in range(n_linhas_corr):
        c.setLineWidth(0.5)
        c.line(_MARGEM_ESQ, y - 1, x_dir, y - 1)
        y -= _LINHA_ASSINATURA

    c.showPage()  # finaliza a última página para o _NumberedCanvas registrá-la
    c.save()


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Gera listas de presença (PDF A4) para assinatura, agrupadas por campus. "
            "Lê todos os dados (equipes, participantes com prontuário/CPF, coordenador "
            "e responsável) do CSV de inscrições."
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
        default="listas_presenca",
        metavar="DIR",
        help="Diretório de saída dos PDFs (padrão: listas_presenca/)",
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
    print(f"Geração de listas de presença - {TITULO_EVENTO}")
    print(f"CSV:      {csv_path.resolve()}")
    print(f"Campi:    {campi_path.resolve()}")
    print(f"Saída:    {output_dir.resolve()}")
    print(f"Modo:     {modo}")

    # Carrega dados (única fonte: o CSV de inscrições)
    campi = load_campi(campi_path)
    teams_csv = load_teams(csv_path)

    print(f"{len(teams_csv)} equipe(s) no CSV.\n")

    credenciais = credenciais_de_csv(teams_csv, campi)

    # Filtro opcional por campus (sigla)
    if args.campus:
        try:
            credenciais = filtrar_por_sigla(credenciais, args.campus, campi)
        except ValueError as exc:
            print(f"Erro: {exc}", file=sys.stderr)
            sys.exit(1)
        if not credenciais:
            print(f"Nenhuma equipe encontrada para o campus {args.campus.upper()!r}.")
            sys.exit(0)
        print(f"Filtrando apenas o campus {args.campus.upper()!r}: {len(credenciais)} equipe(s).\n")

    # Agrupa por campus
    por_campus: dict[str, list[CredencialEquipe]] = defaultdict(list)
    for cred in credenciais:
        por_campus[cred.campus or cred.sigla].append(cred)

    # Cria diretório de saída
    output_dir.mkdir(parents=True, exist_ok=True)

    n_pdfs = 0
    n_emails = 0

    for campus, grupo in por_campus.items():
        nome_arquivo = _limpar_nome(f"IFSP_-_{campus}") + ".pdf"
        caminho_pdf = output_dir / nome_arquivo

        gerar_pdf_campus(grupo, caminho_pdf)
        n_pdfs += 1

        print(f"OK: {campus} -> {caminho_pdf} ({len(grupo)} equipe(s))")

        # Envio opcional
        if args.send or args.dry_run:
            coord_email = grupo[0].coord_email if grupo else ""
            coord_nome = grupo[0].primeiro_nome_coord if grupo else "Coordenador(a)"

            if not coord_email:
                print(f"  Aviso: sem email de coordenador para {campus} — envio ignorado")
            else:
                body = LISTA_BODY_TEMPLATE.format(
                    nome=coord_nome, campus=campus, data_limite=_data_limite()
                )
                send_email(
                    coord_email,
                    f"{LISTA_SUBJECT} — {campus}",
                    body,
                    attach=caminho_pdf,
                    dry_run=args.dry_run,
                )
                n_emails += 1

    # Resumo final
    print()
    rows: list[list[str | int]] = [
        ["Equipes", len(credenciais)],
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
