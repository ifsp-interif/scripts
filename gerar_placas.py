#!/usr/bin/env python3
"""
Gera placas de identificação de equipes (uma página landscape A4 por equipe)
agrupadas em PDFs por campus.

Lê username/senha de usuarios.txt (fonte da verdade gerada por gerar_arquivos_boca.py)
e dados das equipes do CSV de inscrições.  Salva um PDF por campus no diretório de
saída.  Com --send envia cada PDF ao coordenador via `gws gmail +send --attach`.

Uso:
    uv run python gerar_placas.py [--usuarios output/usuarios.txt]
                                  [--csv equipes_interif.csv]
                                  [--campi assets/ifsp_campi.csv]
                                  [-o placas/]
                                  [-s / --send]
                                  [--dry-run]
"""

import argparse
import io
import subprocess
import sys
import unicodedata
from collections import defaultdict
from contextlib import suppress
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from tabulate import tabulate

from config import (
    PLACA_BODY_TEMPLATE,
    PLACA_DATA_EVENTO,
    PLACA_FONTE_NOME,
    PLACA_FONTE_NOME_BOLD,
    PLACA_FONTE_TITULO,
    PLACA_SUBJECT,
    PLACA_TITULO_LINHA1,
    PLACA_TITULO_LINHA2,
    TITULO_EVENTO,
)
from interif_core import (
    CAMPI_FILE,
    CSV_FILE,
    CredencialEquipe,
    enriquecer,
    load_campi,
    load_teams,
    parse_usuarios,
)

# ── Caminhos padrão ───────────────────────────────────────────────────────────

_HERE         = Path(__file__).parent
_ASSETS       = _HERE / "assets"
USUARIOS_FILE = _HERE / "output" / "usuarios.txt"
LOGO_PATH     = _ASSETS / "logo.png"
LOGO_DIREITA  = _ASSETS / "IFSP_Logo.jpg"

# ── Helpers de nome de arquivo ────────────────────────────────────────────────

def _limpar_nome(texto: str) -> str:
    """Remove colchetes, acentos e caracteres inválidos; substitui espaços por _."""
    texto = texto.strip().replace("[", "").replace("]", "")
    texto = unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("ASCII")
    return texto.replace(" ", "_").replace("/", "-")


# ── Separação de fullname ─────────────────────────────────────────────────────

def _separar_por_colchete(texto: str) -> tuple[str, str]:
    """'[IFSP - X] Nome' → ('[IFSP - X]', 'Nome')."""
    if "]" in texto:
        parte1, parte2 = texto.split("]", 1)
        return parte1 + "]", parte2.strip()
    return texto, ""


# ── Registro de fontes ────────────────────────────────────────────────────────

def _registrar_fontes() -> None:
    """Registra as fontes decorativas usadas nas placas."""
    fontes = {
        "PlacaTitulo":   PLACA_FONTE_TITULO,
        "PlacaNome":     PLACA_FONTE_NOME,
        "PlacaNomeBold": PLACA_FONTE_NOME_BOLD,
    }
    for alias, arquivo in fontes.items():
        caminho = _ASSETS / arquivo
        if not caminho.exists():
            print(
                f"Erro: fonte não encontrada: {caminho}\n"
                f"Verifique {arquivo!r} em config.py e o diretório assets/."
            )
            sys.exit(1)
        pdfmetrics.registerFont(TTFont(alias, str(caminho)))


# ── Gradiente em memória ──────────────────────────────────────────────────────

def _gerar_gradiente(
    largura: int,
    altura: int,
    margem_recuo: int = 10,
    espessura_borda: int = 20,
) -> io.BytesIO:
    """
    Cria uma imagem PNG com borda gradiente vertical e centro branco.
    Retorna um BytesIO pronto para ImageReader — nenhum arquivo é gravado em disco.
    """
    cores = [
        (246, 79,  89),   # vermelho-rosado
        (196, 113, 237),  # roxo
        (18,  194, 233),  # azul claro
    ]

    img  = Image.new("RGB", (largura, altura), color="white")
    draw = ImageDraw.Draw(img)

    n = len(cores) - 1
    span = altura - 2 * margem_recuo

    for y in range(margem_recuo, altura - margem_recuo):
        t        = (y - margem_recuo) / span
        t_scaled = t * n
        i        = min(int(t_scaled), n - 1)
        f        = t_scaled - i
        r1, g1, b1 = cores[i]
        r2, g2, b2 = cores[i + 1]
        r = int(r1 + (r2 - r1) * f)
        g = int(g1 + (g2 - g1) * f)
        b = int(b1 + (b2 - b1) * f)
        draw.line([(margem_recuo, y), (largura - margem_recuo, y)], fill=(r, g, b))

    # Área central branca (sobre o gradiente)
    draw.rectangle(
        [
            margem_recuo + espessura_borda,
            margem_recuo + espessura_borda,
            largura  - margem_recuo - espessura_borda,
            altura   - margem_recuo - espessura_borda,
        ],
        fill="white",
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ── Ajuste automático de tamanho de fonte ─────────────────────────────────────

def _ajustar_fonte(
    texto: str,
    largura_max: float,
    fonte: str = "Helvetica",
    tamanho_max: int = 72,
    tamanho_min: int = 8,
    passo: int = 1,
) -> int:
    """Devolve o maior tamanho de fonte que faz `texto` caber em `largura_max`."""
    for tamanho in range(tamanho_max, tamanho_min - 1, -passo):
        if stringWidth(texto, fonte, tamanho) <= largura_max:
            return tamanho
    return tamanho_min


# ── Geração de PDF ────────────────────────────────────────────────────────────

def gerar_pdf_campus(credenciais: list[CredencialEquipe], caminho_pdf: Path) -> None:
    """
    Gera um PDF com uma página landscape A4 por equipe.
    O gradiente de fundo é criado em memória uma única vez e reutilizado em todas
    as páginas via ImageReader (que cacheia internamente).
    """
    larg_pag, alt_pag = landscape(A4)
    largura, altura   = int(larg_pag), int(alt_pag)

    # Gradiente gerado em memória — sem arquivo temporário em disco
    buf      = _gerar_gradiente(largura, altura)
    bg_img   = ImageReader(buf)

    c = canvas.Canvas(str(caminho_pdf), pagesize=(larg_pag, alt_pag))

    for cred in credenciais:
        # ── fundo ──────────────────────────────────────────────────────────────
        c.drawImage(bg_img, 0, 0, width=larg_pag, height=alt_pag)

        # ── cabeçalho (fonte decorativa) ───────────────────────────────────────
        c.setFont("PlacaTitulo", 36)
        c.drawCentredString(larg_pag / 2, alt_pag - 100, PLACA_TITULO_LINHA1)
        c.setFont("PlacaTitulo", 34)
        c.drawCentredString(larg_pag / 2, alt_pag - 140, PLACA_TITULO_LINHA2)

        # ── logos ──────────────────────────────────────────────────────────────
        if LOGO_PATH.exists():
            with suppress(Exception):
                c.drawImage(str(LOGO_PATH),
                            15 * mm + 20, alt_pag - 190,
                            width=100, height=130, mask="auto")
        if LOGO_DIREITA.exists():
            with suppress(Exception):
                c.drawImage(str(LOGO_DIREITA),
                            larg_pag - 170, alt_pag - 210,
                            width=120, height=160, mask="auto")

        # ── nome da equipe (centralizado, tamanho automático) ──────────────────
        fullname   = f"[IFSP - {cred.sigla or cred.campus}] {cred.nome_equipe}"
        _, nome_eq = _separar_por_colchete(fullname)
        margem_recuo  = 10
        largura_util  = larg_pag - 2 * margem_recuo - 55
        tamanho_nome  = _ajustar_fonte(nome_eq, largura_util, "PlacaNomeBold")

        c.setFont("PlacaNomeBold", tamanho_nome)
        c.drawCentredString(larg_pag / 2, alt_pag / 2 - 30, nome_eq)

        # ── campus (fonte fina, tamanho ligeiramente menor) ────────────────────
        campus_label = f"IFSP - {cred.sigla or cred.campus}"
        c.setFont("PlacaNome", max(tamanho_nome - 30, 8))
        c.drawCentredString(larg_pag / 2, alt_pag / 2 - 90, campus_label)

        # ── faixa preta inferior com data do evento ────────────────────────────
        margem      = 15 * mm
        faixa_altura = 35

        c.setFillColor(colors.black)
        c.rect(margem, margem,
               larg_pag - 2 * margem - 100,
               faixa_altura, fill=1)

        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 17)
        c.drawString(margem + 10, margem + 10, PLACA_DATA_EVENTO)

        # ── faixa verde com username da equipe ─────────────────────────────────
        c.setFillColor(colors.green)
        c.rect(larg_pag - margem - 150, margem, 150, faixa_altura, fill=1)

        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 19)
        c.drawCentredString(larg_pag - margem - 90, margem + 10,
                            cred.username.upper())

        c.showPage()

    c.save()


# ── Envio de email ────────────────────────────────────────────────────────────

def _send_pdf(
    to: str,
    subject: str,
    body: str,
    attach: Path,
    *,
    dry_run: bool,
) -> None:
    """Envia um PDF como anexo via `gws gmail +send`. Em dry-run apenas exibe."""
    if dry_run:
        print(f"  -> Para: {to}")
        print(f"     Assunto: {subject}")
        print(f"     Anexo: {attach}")
        return

    print(f"  -> Enviando para {to} ...")
    cmd = [
        "gws", "gmail", "+send",
        "--to",      to,
        "--subject", subject,
        "--body",    body,
        "--attach",  str(attach),
    ]
    try:
        subprocess.run(cmd, check=True)
        print("    OK")
    except subprocess.CalledProcessError as exc:
        print(f"    Erro: {exc}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Gera placas de identificação de equipes em PDFs agrupados por campus. "
            "Lê username/senha de usuarios.txt e dados das equipes do CSV de inscrições."
        )
    )
    parser.add_argument(
        "--usuarios",
        default=str(USUARIOS_FILE),
        metavar="ARQUIVO",
        help=f"Caminho para usuarios.txt (padrão: {USUARIOS_FILE})",
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
        "-o", "--output",
        default="placas",
        metavar="DIR",
        help="Diretório de saída dos PDFs (padrão: placas/)",
    )
    parser.add_argument(
        "-s", "--send",
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

    usuarios_path = Path(args.usuarios)
    csv_path      = Path(args.csv)
    campi_path    = Path(args.campi)
    output_dir    = Path(args.output)

    # Verifica arquivos de entrada
    for p in (usuarios_path, csv_path, campi_path):
        if not p.exists():
            print(f"Erro: arquivo não encontrado: {p}", file=sys.stderr)
            sys.exit(1)

    modo = "dry-run" if args.dry_run else ("envio real" if args.send else "somente geração")
    print(f"Geração de placas - {TITULO_EVENTO}")
    print(f"Usuários: {usuarios_path.resolve()}")
    print(f"CSV:      {csv_path.resolve()}")
    print(f"Campi:    {campi_path.resolve()}")
    print(f"Saída:    {output_dir.resolve()}")
    print(f"Modo:     {modo}")

    # Registra fontes decorativas
    _registrar_fontes()

    # Carrega dados
    campi     = load_campi(campi_path)
    teams_csv = load_teams(csv_path)
    usuarios  = parse_usuarios(usuarios_path)

    print(f"{len(usuarios)} equipe(s) em usuarios.txt | {len(teams_csv)} linha(s) no CSV.\n")

    credenciais = enriquecer(usuarios, teams_csv, campi, emit=print)

    # Agrupa por campus
    por_campus: dict[str, list[CredencialEquipe]] = defaultdict(list)
    for cred in credenciais:
        por_campus[cred.campus or cred.sigla or cred.username].append(cred)

    # Cria diretório de saída
    output_dir.mkdir(parents=True, exist_ok=True)

    n_pdfs   = 0
    n_emails = 0

    for campus, grupo in por_campus.items():
        nome_arquivo = _limpar_nome(f"IFSP_-_{campus}") + ".pdf"
        caminho_pdf  = output_dir / nome_arquivo

        gerar_pdf_campus(grupo, caminho_pdf)
        n_pdfs += 1

        print(f"OK: {campus} -> {caminho_pdf} ({len(grupo)} placa(s))")

        # Envio opcional
        if args.send or args.dry_run:
            coord_email = grupo[0].coord_email if grupo else ""
            coord_nome  = grupo[0].primeiro_nome_coord if grupo else "Coordenador(a)"

            if not coord_email:
                print(f"  Aviso: sem email de coordenador para {campus} — envio ignorado")
            else:
                body = PLACA_BODY_TEMPLATE.format(nome=coord_nome, campus=campus)
                _send_pdf(
                    to=coord_email,
                    subject=f"{PLACA_SUBJECT} — {campus}",
                    body=body,
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
