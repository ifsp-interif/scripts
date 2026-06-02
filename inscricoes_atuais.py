#!/usr/bin/env python3
"""Envia emails de confirmação de inscrição para coordenadores e responsáveis."""

import argparse
import csv
from collections import defaultdict
from datetime import datetime

from config import (
    COORD_POST,
    COORD_PRE,
    COORD_SUBJECT,
    NO_TEAMS_BODY,
    NO_TEAMS_SUBJECT,
    RESP_POST,
    RESP_PRE,
    RESP_SUBJECT,
    SUMMARY_POST,
    SUMMARY_PRE,
    SUMMARY_SUBJECT,
)
from config import (
    EMAIL_INTERIF as SUMMARY_TO,
)
from email_utils import send_email

# ── Configuração local ────────────────────────────────────────────────────────

CSV_FILE = "equipes_interif.csv"
COORD_CSV_FILE = "coordenadores_interif.csv"

_now = datetime.now()
_TIMESTAMP = _now.strftime("até %Y-%m-%d %Hh%Mmin")


def first_name(full_name: str) -> str:
    return full_name.strip().split()[0] if full_name.strip() else full_name


def normalize_campus(campus: str) -> str:
    return campus.strip().lower()


def load_teams(csv_file: str) -> list[dict]:
    teams = []
    with open(csv_file, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row["Nome da Equipe"].strip():
                continue
            participants = [
                row[col].strip()
                for col in ("Nome Participante 1", "Nome Participante 2", "Nome Participante 3")
                if row.get(col, "").strip()
            ]
            teams.append(
                {
                    "equipe": row["Nome da Equipe"].strip(),
                    "campus": row["Campus"].strip(),
                    "coord_nome": row["Nome do Coordenador do Campus"].strip(),
                    "coord_email": row["Email do Coordenador do Campus"].strip().lower(),
                    "resp_nome": row["Nome do Responsável pela Equipe"].strip(),
                    "resp_email": row["Email do Responsável pela Equipe"].strip().lower(),
                    "participantes": participants,
                }
            )
    return teams


def load_coordinators(csv_file: str) -> list[dict]:
    coordinators = []
    with open(csv_file, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            campus = row.get("Campus", "").strip()
            if not campus:
                continue
            coordinators.append(
                {
                    "campus": campus,
                    "coord_nome": row.get("Nome do Coordenador do Campus", "").strip(),
                    "coord_email": row.get("Email do Coordenador do Campus", "").strip().lower(),
                }
            )
    return coordinators


def group_by_coordinator(teams: list[dict]) -> dict:
    por_campus = defaultdict(lambda: {"nome": "", "campus": "", "equipes": []})
    for t in teams:
        entry = por_campus[t["coord_email"]]
        entry["nome"] = t["coord_nome"]
        entry["campus"] = t["campus"]
        entry["equipes"].append(
            {
                "nome": t["equipe"],
                "responsavel": t["resp_nome"],
                "participantes": t["participantes"],
            }
        )
    return dict(por_campus)


def group_by_advisor(teams: list[dict]) -> dict:
    por_resp = defaultdict(lambda: {"nome": "", "equipes": []})
    for t in teams:
        entry = por_resp[t["resp_email"]]
        entry["nome"] = t["resp_nome"]
        entry["equipes"].append(
            {
                "nome": t["equipe"],
                "participantes": t["participantes"],
            }
        )
    return dict(por_resp)


def format_team_line_coord(equipe: dict) -> str:
    parts = ", ".join(equipe["participantes"])
    return f"- {equipe['nome']}: {parts} ({equipe['responsavel']})"


def format_team_line_resp(equipe: dict) -> str:
    parts = ", ".join(equipe["participantes"])
    return f"- {equipe['nome']}: {parts}"


def send_coordinator_emails(por_campus: dict, dry_run: bool) -> int:
    print("\n=== Emails para coordenadores de campus ===")
    count = 0
    for email, data in por_campus.items():
        lines = "\n".join(format_team_line_coord(e) for e in data["equipes"])
        body = (
            COORD_PRE.format(nome=first_name(data["nome"]), campus=data["campus"])
            + "\n"
            + lines
            + "\n"
            + COORD_POST
        )
        send_email(email, f"{COORD_SUBJECT} {_TIMESTAMP}", body, dry_run=dry_run)
        count += 1
    return count


def send_summary_email(por_campus: dict, dry_run: bool) -> None:
    print("\n=== Email de resumo para a organização ===")
    lines = "\n".join(
        f"- {data['campus']}: {len(data['equipes'])} equipe(s)"
        for data in sorted(por_campus.values(), key=lambda d: d["campus"])
    )
    total = sum(len(d["equipes"]) for d in por_campus.values())
    body = SUMMARY_PRE + "\n" + lines + f"\n\nTotal geral: {total} equipe(s)" + "\n" + SUMMARY_POST
    send_email(SUMMARY_TO, f"{SUMMARY_SUBJECT} {_TIMESTAMP}", body, dry_run=dry_run)


def find_no_teams_coordinators(coordinators: list[dict], teams: list[dict]) -> list[dict]:
    campi_com_equipes = {normalize_campus(t["campus"]) for t in teams}
    return [
        coord
        for coord in sorted(coordinators, key=lambda c: c["campus"])
        if normalize_campus(coord["campus"]) not in campi_com_equipes
    ]


def send_no_teams_emails(no_teams_coordinators: list[dict], dry_run: bool) -> int:
    print("\n=== Emails para coordenadores de campi sem equipes ===")
    count = 0

    for coord in no_teams_coordinators:
        email = coord["coord_email"]
        if not email:
            print(f"  Aviso: sem email de coordenador para {coord['campus']} — envio ignorado")
            continue

        body = NO_TEAMS_BODY.format(
            nome=first_name(coord["coord_nome"]),
            campus=coord["campus"],
        )
        send_email(email, f"{NO_TEAMS_SUBJECT} {_TIMESTAMP}", body, dry_run=dry_run)
        count += 1

    return count


def send_no_teams_summary_email(no_teams_coordinators: list[dict], dry_run: bool) -> None:
    print("\n=== Email de resumo para a organização ===")
    lines = "\n".join(f"- {coord['campus']}" for coord in no_teams_coordinators)
    total = len(no_teams_coordinators)
    body = (
        "Seguem abaixo os campi sem equipes inscritas:\n\n"
        + (lines or "- Nenhum campus sem equipes inscritas")
        + f"\n\nTotal: {total} campus sem equipes inscritas"
        + "\n"
        + SUMMARY_POST
    )
    send_email(SUMMARY_TO, f"{NO_TEAMS_SUBJECT} — resumo {_TIMESTAMP}", body, dry_run=dry_run)


def send_advisor_emails(por_resp: dict, dry_run: bool) -> int:
    print("\n=== Emails para responsáveis pelas equipes ===")
    count = 0
    for email, data in por_resp.items():
        lines = "\n".join(format_team_line_resp(e) for e in data["equipes"])
        body = RESP_PRE.format(nome=first_name(data["nome"])) + "\n" + lines + "\n" + RESP_POST
        send_email(email, f"{RESP_SUBJECT} {_TIMESTAMP}", body, dry_run=dry_run)
        count += 1
    return count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Envia emails de confirmação de inscrição para coordenadores e responsáveis."
    )
    parser.add_argument(
        "--csv",
        default=CSV_FILE,
        metavar="ARQUIVO",
        help=f"Caminho do CSV de equipes (padrão: {CSV_FILE})",
    )
    parser.add_argument(
        "--coordenadores",
        "-c",
        default=COORD_CSV_FILE,
        metavar="ARQUIVO",
        help=f"Caminho do CSV de coordenadores (padrão: {COORD_CSV_FILE})",
    )
    parser.add_argument(
        "--no-teams",
        "-n",
        action="store_true",
        help="Envia somente para coordenadores de campi que não possuem equipes inscritas",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula o envio sem disparar emails",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    teams = load_teams(args.csv)
    print(f"Carregadas {len(teams)} equipes de '{args.csv}'.")

    if args.no_teams:
        coordinators = load_coordinators(args.coordenadores)
        print(f"Carregados {len(coordinators)} coordenador(es) de '{args.coordenadores}'.")
        no_teams_coordinators = find_no_teams_coordinators(coordinators, teams)
        n_no_teams = send_no_teams_emails(no_teams_coordinators, args.dry_run)
        send_no_teams_summary_email(no_teams_coordinators, args.dry_run)
        print(
            f"\nPronto! {n_no_teams} email(s) para coordenadores de campi sem equipes, "
            f"1 resumo para {SUMMARY_TO}."
        )
        return

    por_campus = group_by_coordinator(teams)
    por_resp = group_by_advisor(teams)

    n_coord = send_coordinator_emails(por_campus, args.dry_run)
    n_resp = send_advisor_emails(por_resp, args.dry_run)
    send_summary_email(por_campus, args.dry_run)

    print(
        f"\nPronto! {n_coord} email(s) para coordenadores, {n_resp} email(s) para responsáveis, 1 resumo para {SUMMARY_TO}."
    )


if __name__ == "__main__":
    main()
