#!/usr/bin/env python3
"""
Gera etiquetas de credenciais BOCA (uma por equipe) em PDFs agrupados por campus.

Lê username/senha de usuarios.txt (fonte da verdade gerada por gerar_arquivos_boca.py)
e endereços de coordenadores do CSV de equipes.  Salva um PDF por campus no diretório
de saída.  Com --send envia cada PDF ao coordenador via `gws gmail +send --attach`.

Uso:
    uv run python gerar_etiquetas.py [--usuarios output/usuarios.txt]
                                  [--csv equipes_interif.csv]
                                  [--campi ifsp_campi.csv]
                                  [-o etiquetas/]
                                  [-s / --send]
                                  [--dry-run]
"""

import argparse
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from tabulate import tabulate

from config import (
    ETIQ_BODY_TEMPLATE,
    ETIQ_FONTE_MONO,
    ETIQ_SUBJECT,
    TITULO_EVENTO,
)
from email_utils import send_email
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

_HERE = Path(__file__).parent
_ASSETS = _HERE / "assets"
USUARIOS_FILE = _HERE / "output" / "usuarios.txt"
LOGO_PATH = _ASSETS / "logo.png"

# ── Layout das etiquetas ──────────────────────────────────────────────────────

_COLS = 2
_ROWS = 6
_LABEL_W = 95 * mm
_LABEL_H = 45 * mm
_X_MARGIN = 9.5 * mm
_Y_MARGIN = 10.57 * mm

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


# ── Geração de PDF de etiquetas ───────────────────────────────────────────────


def _registrar_fonte() -> None:
    """Registra a fonte monospaced definida em config.py."""
    caminho = _ASSETS / ETIQ_FONTE_MONO
    if not caminho.exists():
        print(
            f"Erro: fonte não encontrada: {caminho}\n"
            "Verifique ETIQ_FONTE_MONO em config.py e o diretório assets/."
        )
        sys.exit(1)
    pdfmetrics.registerFont(TTFont("EtiqMono", str(caminho)))


def gerar_pdf_campus(credenciais: list[CredencialEquipe], caminho_pdf: Path) -> None:
    """Gera um PDF de etiquetas para uma lista de equipes (mesmo campus)."""
    width, height = A4

    logo = ImageReader(str(LOGO_PATH)) if LOGO_PATH.exists() else None
    logo_w_mm = 12 * mm
    if logo:
        orig_w, orig_h = logo.getSize()
        logo_h_mm = logo_w_mm * orig_h / orig_w
    else:
        logo_h_mm = logo_w_mm

    c = canvas.Canvas(str(caminho_pdf), pagesize=A4)

    for i, cred in enumerate(credenciais):
        col = i % _COLS
        row = (i // _COLS) % _ROWS

        # Nova página a cada grade completa (exceto a primeira)
        if i != 0 and i % (_COLS * _ROWS) == 0:
            c.showPage()

        x = _X_MARGIN + col * _LABEL_W
        y = height - (_Y_MARGIN + (row + 1) * _LABEL_H)

        # Borda arredondada
        c.roundRect(x, y, _LABEL_W - 10, _LABEL_H - 5, 5, stroke=1, fill=0)

        # Logo (canto superior direito da etiqueta)
        logo_x = x + (_LABEL_W - 10) - logo_w_mm - 10
        logo_y = y + _LABEL_H - 50 - logo_h_mm
        if logo:
            c.drawImage(logo, logo_x, logo_y - 30, width=logo_w_mm, height=logo_h_mm, mask="auto")

        # ── Posições verticais explícitas (y cresce para cima no PDF) ──────────
        # De cima para baixo na etiqueta:
        #   logo_y + 65  →  "[IFSP - X]"
        #   logo_y + 50  →  nome da equipe
        #   logo_y + 18  →  Name: teamXXX
        #   logo_y +  4  →  Password: abc123
        #   logo_y -  2  →  linha separadora
        #   logo_y - 17  →  INTERIF TEAM CREDENTIALS
        #   logo_y - 29  →  TITULO_EVENTO

        # Campus e nome da equipe (topo da etiqueta)
        fullname = f"[IFSP - {cred.sigla or cred.campus}] {cred.nome_equipe}"
        parte1, parte2 = _separar_por_colchete(fullname)

        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(x + _LABEL_W / 2, logo_y + 65, parte1)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(x + _LABEL_W / 2, logo_y + 50, parte2)

        # Name
        login_label = "Name: "
        login_text = cred.username
        lw_label = c.stringWidth(login_label, "Helvetica-Bold", 11)
        lw_text = c.stringWidth(login_text, "EtiqMono", 11)
        start_x = x + (_LABEL_W - 10) / 2 - (lw_label + lw_text) / 2

        c.setFont("Helvetica-Bold", 11)
        c.drawString(start_x, logo_y + 18, login_label)
        c.setFont("EtiqMono", 11)
        c.drawString(start_x + lw_label, logo_y + 18, login_text)

        # Password
        senha_label = "Password: "
        senha_text = cred.password
        pw_label = c.stringWidth(senha_label, "Helvetica-Bold", 11)
        pw_text = c.stringWidth(senha_text, "EtiqMono", 11)
        start_px = x + (_LABEL_W - 10) / 2 - (pw_label + pw_text) / 2

        c.setFont("Helvetica-Bold", 11)
        c.drawString(start_px, logo_y + 4, senha_label)
        c.setFont("EtiqMono", 11)
        c.drawString(start_px + pw_label, logo_y + 4, senha_text)

        # Separador + rótulo do evento (abaixo das credenciais)
        c.setFont("Helvetica", 11)
        c.drawString(x + 5, logo_y - 2, "_______________________________")
        c.setFont("Helvetica", 8)
        c.drawString(x + 5, logo_y - 17, "INTERIF TEAM CREDENTIALS")
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x + 5, logo_y - 29, TITULO_EVENTO)

    c.save()


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Gera etiquetas de credenciais BOCA em PDFs agrupados por campus. "
            "Lê username/senha de usuarios.txt e endereços do CSV de equipes."
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
        "-o",
        "--output",
        default="etiquetas",
        metavar="DIR",
        help="Diretório de saída dos PDFs (padrão: etiquetas/)",
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

    usuarios_path = Path(args.usuarios)
    csv_path = Path(args.csv)
    campi_path = Path(args.campi)
    output_dir = Path(args.output)

    # Verifica arquivos de entrada
    for p in (usuarios_path, csv_path, campi_path):
        if not p.exists():
            print(f"Erro: arquivo não encontrado: {p}", file=sys.stderr)
            sys.exit(1)

    modo = "dry-run" if args.dry_run else ("envio real" if args.send else "somente geração")
    print("Geração de etiquetas - InterIF")
    print(f"Usuários: {usuarios_path.resolve()}")
    print(f"CSV:      {csv_path.resolve()}")
    print(f"Campi:    {campi_path.resolve()}")
    print(f"Saída:    {output_dir.resolve()}")
    print(f"Modo:     {modo}")

    # Registra fonte monospaced
    _registrar_fonte()

    # Carrega dados
    campi = load_campi(campi_path)
    teams_csv = load_teams(csv_path)
    usuarios = parse_usuarios(usuarios_path)

    print(f"{len(usuarios)} equipe(s) em usuarios.txt | {len(teams_csv)} linha(s) no CSV.\n")

    credenciais = enriquecer(usuarios, teams_csv, campi, emit=print)

    # Agrupa por campus (mantém label = campus_raw como chave de exibição)
    por_campus: dict[str, list[CredencialEquipe]] = defaultdict(list)
    for cred in credenciais:
        por_campus[cred.campus or cred.sigla or cred.username].append(cred)

    # Cria diretório de saída
    output_dir.mkdir(parents=True, exist_ok=True)

    n_pdfs = 0
    n_emails = 0

    for campus, grupo in por_campus.items():
        nome_arquivo = _limpar_nome(f"IFSP_-_{campus}") + ".pdf"
        caminho_pdf = output_dir / nome_arquivo

        gerar_pdf_campus(grupo, caminho_pdf)
        n_pdfs += 1

        print(f"OK: {campus} -> {caminho_pdf} ({len(grupo)} etiqueta(s))")

        # Envio opcional
        if args.send or args.dry_run:
            coord_email = grupo[0].coord_email if grupo else ""
            coord_nome = grupo[0].primeiro_nome_coord if grupo else "Coordenador(a)"

            if not coord_email:
                print(f"  Aviso: sem email de coordenador para {campus} — envio ignorado")
            else:
                body = ETIQ_BODY_TEMPLATE.format(nome=coord_nome, campus=campus)
                send_email(
                    coord_email,
                    f"{ETIQ_SUBJECT} — {campus}",
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
