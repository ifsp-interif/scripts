#!/usr/bin/env python3
"""Envia emails de confirmação de inscrição para coordenadores e responsáveis."""

import csv
import subprocess
from collections import defaultdict
from datetime import datetime

from config import (
    COORD_POST,
    COORD_PRE,
    COORD_SUBJECT,
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

# ── Configuração local ────────────────────────────────────────────────────────

CSV_FILE = "equipes_interif.csv"
DRY_RUN  = False   # True → não envia emails de verdade

_now = datetime.now()
_TIMESTAMP = _now.strftime("até %Y-%m-%d %Hh%Mmin")


def first_name(full_name: str) -> str:
    return full_name.strip().split()[0] if full_name.strip() else full_name


def send_email(to: str, subject: str, body: str) -> None:
    cmd = ["gws", "gmail", "+send", "--to", to, "--subject", subject, "--body", body]
    if DRY_RUN:
        cmd.append("--dry-run")
    print(f"  → Enviando para {to} ...")
    subprocess.run(cmd, check=True)


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
            teams.append({
                "equipe":        row["Nome da Equipe"].strip(),
                "campus":        row["Campus"].strip(),
                "coord_nome":    row["Nome do Coordenador do Campus"].strip(),
                "coord_email":   row["Email do Coordenador do Campus"].strip().lower(),
                "resp_nome":     row["Nome do Responsável pela Equipe"].strip(),
                "resp_email":    row["Email do Responsável pela Equipe"].strip().lower(),
                "participantes": participants,
            })
    return teams


def group_by_coordinator(teams: list[dict]) -> dict:
    por_campus = defaultdict(lambda: {"nome": "", "campus": "", "equipes": []})
    for t in teams:
        entry = por_campus[t["coord_email"]]
        entry["nome"]   = t["coord_nome"]
        entry["campus"] = t["campus"]
        entry["equipes"].append({
            "nome":         t["equipe"],
            "responsavel":  t["resp_nome"],
            "participantes": t["participantes"],
        })
    return dict(por_campus)


def group_by_advisor(teams: list[dict]) -> dict:
    por_resp = defaultdict(lambda: {"nome": "", "equipes": []})
    for t in teams:
        entry = por_resp[t["resp_email"]]
        entry["nome"] = t["resp_nome"]
        entry["equipes"].append({
            "nome":         t["equipe"],
            "participantes": t["participantes"],
        })
    return dict(por_resp)


def format_team_line_coord(equipe: dict) -> str:
    parts = ", ".join(equipe["participantes"])
    return f"- {equipe['nome']}: {parts} ({equipe['responsavel']})"


def format_team_line_resp(equipe: dict) -> str:
    parts = ", ".join(equipe["participantes"])
    return f"- {equipe['nome']}: {parts}"


def send_coordinator_emails(por_campus: dict) -> int:
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
        send_email(email, f"{COORD_SUBJECT} {_TIMESTAMP}", body)
        count += 1
    return count


def send_summary_email(por_campus: dict) -> None:
    print("\n=== Email de resumo para a organização ===")
    lines = "\n".join(
        f"- {data['campus']}: {len(data['equipes'])} equipe(s)"
        for data in sorted(por_campus.values(), key=lambda d: d["campus"])
    )
    total = sum(len(d["equipes"]) for d in por_campus.values())
    body = SUMMARY_PRE + "\n" + lines + f"\n\nTotal geral: {total} equipe(s)" + "\n" + SUMMARY_POST
    send_email(SUMMARY_TO, f"{SUMMARY_SUBJECT} {_TIMESTAMP}", body)


def send_advisor_emails(por_resp: dict) -> int:
    print("\n=== Emails para responsáveis pelas equipes ===")
    count = 0
    for email, data in por_resp.items():
        lines = "\n".join(format_team_line_resp(e) for e in data["equipes"])
        body = (
            RESP_PRE.format(nome=first_name(data["nome"]))
            + "\n"
            + lines
            + "\n"
            + RESP_POST
        )
        send_email(email, f"{RESP_SUBJECT} {_TIMESTAMP}", body)
        count += 1
    return count


def main() -> None:
    teams = load_teams(CSV_FILE)
    print(f"Carregadas {len(teams)} equipes de '{CSV_FILE}'.")

    por_campus = group_by_coordinator(teams)
    por_resp   = group_by_advisor(teams)

    n_coord = send_coordinator_emails(por_campus)
    n_resp  = send_advisor_emails(por_resp)
    send_summary_email(por_campus)

    print(f"\nPronto! {n_coord} email(s) para coordenadores, {n_resp} email(s) para responsáveis, 1 resumo para {SUMMARY_TO}.")


if __name__ == "__main__":
    main()
