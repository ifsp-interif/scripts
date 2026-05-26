#!/usr/bin/env python3
"""
Downloads two IFSP InterIF spreadsheets, joins them by Campus in a SQLite
in-memory database, and saves a team roster to equipes_interif.csv.
"""

import argparse
import csv
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

SHEET_NAME = "Respostas ao formulário 1"
OUTPUT_FILE = Path(__file__).parent / "equipes_interif.csv"


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
    parser = argparse.ArgumentParser(description="Gera equipes_interif.csv a partir de duas planilhas Google Sheets.")
    parser.add_argument("--campi", required=True, metavar="SHEET_ID", help="ID da planilha de inscrição de campi")
    parser.add_argument("--teams", required=True, metavar="SHEET_ID", help="ID da planilha de inscrição de equipes")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("Lendo planilha 1 (coordenadores de campus)...")
    _, rows1 = read_sheet(args.campi, SHEET_NAME)
    print(f"  {len(rows1)} linhas lidas")

    print("Lendo planilha 2 (equipes)...")
    _, rows2 = read_sheet(args.teams, SHEET_NAME)
    print(f"  {len(rows2)} linhas lidas")

    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE coordenadores (
            campus          TEXT,
            nome_coord      TEXT,
            email_coord     TEXT
        )
        """
    )
    for row in rows1:
        campus = get(row, 3)
        if campus:
            cur.execute(
                "INSERT INTO coordenadores VALUES (?, ?, ?)",
                (campus, get(row, 2), get(row, 4)),
            )

    cur.execute(
        """
        CREATE TABLE equipes (
            campus          TEXT,
            nome_equipe     TEXT,
            nome_resp       TEXT,
            cpf_resp        TEXT,
            email_resp      TEXT,
            nome_m1         TEXT,
            cpf_m1          TEXT,
            email_m1        TEXT,
            nome_m2         TEXT,
            cpf_m2          TEXT,
            email_m2        TEXT,
            nome_m3         TEXT,
            cpf_m3          TEXT,
            email_m3        TEXT
        )
        """
    )
    for row in rows2:
        cur.execute(
            "INSERT INTO equipes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                get(row, 3),   # campus
                get(row, 2),   # team name
                get(row, 6),   # advisor name
                get(row, 7),   # advisor CPF
                get(row, 8),   # advisor email
                get(row, 11),  # member 1 name
                get(row, 13),  # member 1 CPF
                get(row, 14),  # member 1 email
                get(row, 18),  # member 2 name
                get(row, 20),  # member 2 CPF
                get(row, 21),  # member 2 email
                get(row, 25),  # member 3 name
                get(row, 27),  # member 3 CPF
                get(row, 28),  # member 3 email
            ),
        )

    cur.execute(
        """
        SELECT
            e.nome_equipe,
            e.campus,
            c.nome_coord,
            c.email_coord,
            e.nome_resp,
            e.cpf_resp,
            e.email_resp,
            e.nome_m1, e.cpf_m1, e.email_m1,
            e.nome_m2, e.cpf_m2, e.email_m2,
            e.nome_m3, e.cpf_m3, e.email_m3
        FROM equipes e
        LEFT JOIN coordenadores c
               ON LOWER(TRIM(e.campus)) = LOWER(TRIM(c.campus))
        ORDER BY e.campus, e.nome_equipe
        """
    )
    result_rows = cur.fetchall()
    conn.close()

    headers = [
        "Nome da Equipe",
        "Campus",
        "Nome do Coordenador do Campus",
        "Email do Coordenador do Campus",
        "Nome do Responsável pela Equipe",
        "CPF do Responsável pela Equipe",
        "Email do Responsável pela Equipe",
        "Nome Participante 1",
        "CPF Participante 1",
        "Email Participante 1",
        "Nome Participante 2",
        "CPF Participante 2",
        "Email Participante 2",
        "Nome Participante 3",
        "CPF Participante 3",
        "Email Participante 3",
    ]

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(result_rows)

    print(f"\n{len(result_rows)} equipes salvas em {OUTPUT_FILE}")

    # Report teams with no matching campus coordinator
    unmatched = [r for r in result_rows if not r[2]]
    if unmatched:
        print(f"\nAtenção: {len(unmatched)} equipe(s) sem coordenador de campus correspondente:")
        for r in unmatched:
            print(f"  - {r[0]} ({r[1]})")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"Erro ao chamar gws: {e.stderr}", file=sys.stderr)
        sys.exit(1)
