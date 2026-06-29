#!/usr/bin/env python3
"""
Downloads two IFSP InterIF spreadsheets, joins them by Campus, and saves a
full team roster to equipes_interif.csv.

All columns from the teams spreadsheet are preserved; key columns are renamed
to canonical names expected by the downstream scripts (cpf_check.py,
inscricoes_atuais.py).  Two coordinator columns are inserted right after Campus.
"""

import argparse
import csv
import subprocess
import sys
from pathlib import Path

from config import EMAIL_INTERIF, SUMMARY_POST, SUMMARY_PRE, SUMMARY_SUBJECT, TITULO_EVENTO
from email_utils import send_email
from equipes_roster import (
    CAMPUS_COL,
    COORD_INSERT_POS,
    SHEET_NAME,
    TEAM_NAME_COL,
    build_coord_map,
    build_output_headers,
    build_team_row,
    get,
    read_sheet,
)

OUTPUT_FILE = Path(__file__).parent / "equipes_interif.csv"
COORD_OUTPUT_FILE = Path(__file__).parent / "coordenadores_interif.csv"


# ── I/O helpers ───────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gera equipes_interif.csv a partir de duas planilhas Google Sheets."
    )
    parser.add_argument(
        "--campi",
        required=True,
        metavar="SHEET_ID",
        help="ID da planilha de inscrição de campi",
    )
    parser.add_argument(
        "--teams",
        required=True,
        metavar="SHEET_ID",
        help="ID da planilha de inscrição de equipes",
    )
    parser.add_argument(
        "--output",
        "-o",
        metavar="ARQUIVO",
        default=str(OUTPUT_FILE),
        help=f"Caminho do CSV de saída (padrão: {OUTPUT_FILE.name})",
    )
    parser.add_argument(
        "--coordenadores",
        "-c",
        metavar="ARQUIVO",
        default=str(COORD_OUTPUT_FILE),
        help=f"Caminho do CSV de coordenadores (padrão: {COORD_OUTPUT_FILE.name})",
    )
    parser.add_argument(
        "--email",
        action="store_true",
        help=f"Envia email de resumo para {EMAIL_INTERIF}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula o envio do email sem realmente enviar",
    )
    return parser.parse_args()


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    args = parse_args()

    print("Lendo planilha 1 (coordenadores de campi)...")
    _, rows1 = read_sheet(args.campi, SHEET_NAME)
    print(f"  {len(rows1)} linhas lidas")

    print("Lendo planilha 2 (equipes)...")
    team_headers, rows2 = read_sheet(args.teams, SHEET_NAME)
    print(f"  {len(rows2)} linhas lidas")

    # Build coordinator lookup: normalised_campus → (campus original, nome, email)
    coord_map = build_coord_map(rows1)

    coord_output_path = Path(args.coordenadores)
    coord_rows = [
        [campus, nome, email]
        for _, (campus, nome, email) in sorted(coord_map.items(), key=lambda item: item[0])
    ]
    with open(coord_output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(
            [
                "Campus",
                "Nome do Coordenador do Campus",
                "Email do Coordenador do Campus",
            ]
        )
        writer.writerows(coord_rows)

    # Output headers: rename key columns; keep all others with original names.
    # Then splice coordinator columns in right after Campus.
    output_headers = build_output_headers(team_headers)

    # Build output rows (skip rows without a team name)
    result_rows: list[list[str]] = []
    for row in rows2:
        if not get(row, TEAM_NAME_COL):
            continue
        result_rows.append(build_team_row(row, team_headers, coord_map))

    # Sort by campus, then team name (case-insensitive)
    result_rows.sort(key=lambda r: (r[CAMPUS_COL].lower(), r[TEAM_NAME_COL].lower()))

    output_path = Path(args.output)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(output_headers)
        writer.writerows(result_rows)

    print(f"\n{len(result_rows)} equipes salvas em {output_path}")
    print(f"{len(coord_rows)} coordenador(es) salvo(s) em {coord_output_path}")
    print(f"Colunas no CSV: {len(output_headers)}")

    # Report teams with no matching campus coordinator
    unmatched = [r for r in result_rows if not r[COORD_INSERT_POS]]
    if unmatched:
        print(f"\nAtenção: {len(unmatched)} equipe(s) sem coordenador de campus correspondente:")
        for r in unmatched:
            print(f"  - {r[TEAM_NAME_COL]} ({r[CAMPUS_COL]})")

    if args.email:
        print(f"\n=== Email de resumo para a organização ({EMAIL_INTERIF}) ===")
        campus_counts: dict[str, int] = {}
        for r in result_rows:
            campus = r[CAMPUS_COL] or "Não informado"
            campus_counts[campus] = campus_counts.get(campus, 0) + 1
        campus_counts = dict(sorted(campus_counts.items(), key=lambda x: x[1], reverse=True))

        lines = "\n".join(
            f"  {campus}: {count} equipe(s)" for campus, count in campus_counts.items()
        )
        total = len(result_rows)
        body = SUMMARY_PRE + "\n" + lines + f"\n\nTotal geral: {total} equipe(s)" + "\n" + SUMMARY_POST
        send_email(
            EMAIL_INTERIF,
            SUMMARY_SUBJECT,
            body,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"Erro ao chamar gws: {e.stderr}", file=sys.stderr)
        sys.exit(1)
