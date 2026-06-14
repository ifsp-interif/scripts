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
import json
import subprocess
import sys
from pathlib import Path

from config import EMAIL_INTERIF, SUMMARY_POST, SUMMARY_PRE, SUMMARY_SUBJECT, TITULO_EVENTO
from email_utils import send_email

SHEET_NAME = "Respostas ao formulário 1"
OUTPUT_FILE = Path(__file__).parent / "equipes_interif.csv"
COORD_OUTPUT_FILE = Path(__file__).parent / "coordenadores_interif.csv"

# ── Column layout of the *teams* sheet (0-based, header row excluded) ─────────
# Adjust these constants if the spreadsheet columns are ever reordered.

CAMPUS_COL = 3  # Campus
TEAM_NAME_COL = 2  # Nome da Equipe

# Key columns that are renamed to canonical names used by downstream scripts.
# All other columns are kept with their original spreadsheet header.
TEAM_KEY_COLUMNS: dict[int, str] = {
    2: "Nome da Equipe",
    3: "Campus",
    6: "Nome do Responsável pela Equipe",
    7: "CPF do Responsável pela Equipe",
    8: "Email do Responsável pela Equipe",
    11: "Nome Participante 1",
    13: "CPF Participante 1",
    14: "Email Participante 1",
    18: "Nome Participante 2",
    20: "CPF Participante 2",
    21: "Email Participante 2",
    25: "Nome Participante 3",
    27: "CPF Participante 3",
    28: "Email Participante 3",
}

# Coordinator columns are inserted at this position (right after Campus).
_COORD_INSERT_POS = CAMPUS_COL + 1  # → index 4 in the output


# ── I/O helpers ───────────────────────────────────────────────────────────────


def read_sheet(spreadsheet_id: str, sheet_name: str) -> tuple[list[str], list[list[str]]]:
    result = subprocess.run(
        ["gws", "sheets", "+read", "--spreadsheet", spreadsheet_id, "--range", sheet_name],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    values = data.get("values", [])
    if not values:
        return [], []
    headers = values[0]
    rows = values[1:]
    # Pad short rows so index access is safe
    rows = [r + [""] * (len(headers) - len(r)) for r in rows]
    return headers, rows


def get(row: list[str], idx: int) -> str:
    return row[idx].strip() if idx < len(row) else ""


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
    coord_map: dict[str, tuple[str, str, str]] = {}
    for row in rows1:
        campus = get(row, 3).strip()
        if campus:
            coord_map[campus.lower()] = (campus, get(row, 2), get(row, 4))

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
    renamed: list[str] = [TEAM_KEY_COLUMNS.get(i, h) for i, h in enumerate(team_headers)]
    output_headers: list[str] = (
        renamed[:_COORD_INSERT_POS]
        + ["Nome do Coordenador do Campus", "Email do Coordenador do Campus"]
        + renamed[_COORD_INSERT_POS:]
    )

    # Build output rows (skip rows without a team name)
    result_rows: list[list[str]] = []
    for row in rows2:
        team_name = get(row, TEAM_NAME_COL)
        if not team_name:
            continue

        campus = get(row, CAMPUS_COL)
        _, coord_nome, coord_email = coord_map.get(campus.lower(), ("", "", ""))

        values = [get(row, i) for i in range(len(team_headers))]
        values = values[:_COORD_INSERT_POS] + [coord_nome, coord_email] + values[_COORD_INSERT_POS:]
        result_rows.append(values)

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
    unmatched = [r for r in result_rows if not r[_COORD_INSERT_POS]]
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
