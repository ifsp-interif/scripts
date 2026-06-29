#!/usr/bin/env python3
"""Envia emails para responsáveis confirmarem tamanhos de camisetas."""

import argparse
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from config import BANNER, EMAIL_INTERIF, TITULO_EVENTO
from email_utils import send_email

CSV_FILE = Path(__file__).parent / "equipes_interif.csv"
SUBJECT = f"Confirmação de tamanhos de camiseta — {TITULO_EVENTO}"

_TIMESTAMP = datetime.now().strftime("até %Y-%m-%d %Hh%Mmin")
_PERSON_COLUMNS = {
    "responsavel": {
        "cpf": "CPF do Responsável pela Equipe",
        "nome": "Nome do Responsável pela Equipe",
        "email": "Email do Responsável pela Equipe",
    },
    "participante_1": {
        "cpf": "CPF Participante 1",
        "nome": "Nome Participante 1",
        "email": "Email Participante 1",
    },
    "participante_2": {
        "cpf": "CPF Participante 2",
        "nome": "Nome Participante 2",
        "email": "Email Participante 2",
    },
    "participante_3": {
        "cpf": "CPF Participante 3",
        "nome": "Nome Participante 3",
        "email": "Email Participante 3",
    },
}


def first_name(full_name: str) -> str:
    return full_name.strip().split()[0] if full_name.strip() else "Professor(a)"


def _get(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def _first_col(headers: list[str], name: str) -> int | None:
    try:
        return headers.index(name)
    except ValueError:
        return None


def _build_indices(headers: list[str]) -> dict:
    shirt_indices = [
        i for i, header in enumerate(headers) if header.strip().lower() == "tamanho da camiseta"
    ]
    used_shirts: set[int] = set()

    people: dict[str, dict[str, int | None]] = {}
    for key, columns in _PERSON_COLUMNS.items():
        cpf_idx = _first_col(headers, columns["cpf"])
        shirt_idx = min(
            (idx for idx in shirt_indices if cpf_idx is not None and idx > cpf_idx and idx not in used_shirts),
            default=None,
            key=lambda idx: idx - (cpf_idx or 0),
        )
        if shirt_idx is not None:
            used_shirts.add(shirt_idx)

        people[key] = {
            "cpf": cpf_idx,
            "nome": _first_col(headers, columns["nome"]),
            "email": _first_col(headers, columns["email"]),
            "camiseta": shirt_idx,
        }

    return {
        "nome_equipe": _first_col(headers, "Nome da Equipe"),
        "campus": _first_col(headers, "Campus"),
        "people": people,
    }


def _required_missing(indices: dict) -> list[str]:
    missing = []
    if indices["nome_equipe"] is None:
        missing.append("Nome da Equipe")
    if indices["campus"] is None:
        missing.append("Campus")
    for label, person in (
        ("Nome do Responsável pela Equipe", indices["people"]["responsavel"]["nome"]),
        ("Email do Responsável pela Equipe", indices["people"]["responsavel"]["email"]),
        ("CPF do Responsável pela Equipe", indices["people"]["responsavel"]["cpf"]),
    ):
        if person is None:
            missing.append(label)
    if indices["people"]["responsavel"]["camiseta"] is None:
        missing.append("Tamanho da camiseta do responsável")
    return missing


def load_teams(csv_path: Path) -> list[dict]:
    teams: list[dict] = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = next(reader, [])
        if not headers:
            raise ValueError(f"CSV vazio: {csv_path}")

        indices = _build_indices(headers)
        missing = _required_missing(indices)
        if missing:
            raise ValueError("Colunas obrigatórias ausentes: " + ", ".join(missing))

        for row in reader:
            nome_equipe = _get(row, indices["nome_equipe"])
            campus = _get(row, indices["campus"])
            if not nome_equipe or not campus:
                continue

            resp_idx = indices["people"]["responsavel"]
            responsavel = {
                "nome": _get(row, resp_idx["nome"]),
                "email": _get(row, resp_idx["email"]).lower(),
                "camiseta": normalize_shirt_size(_get(row, resp_idx["camiseta"])),
            }

            participantes = []
            for key in ("participante_1", "participante_2", "participante_3"):
                person_idx = indices["people"][key]
                nome = _get(row, person_idx["nome"])
                if not nome or nome == "--":
                    continue
                participantes.append(
                    {
                        "nome": nome,
                        "email": _get(row, person_idx["email"]).lower(),
                        "camiseta": normalize_shirt_size(_get(row, person_idx["camiseta"])),
                    }
                )

            teams.append(
                {
                    "nome": nome_equipe,
                    "campus": campus,
                    "responsavel": responsavel,
                    "participantes": participantes,
                }
            )

    return teams


def normalize_shirt_size(value: str) -> str:
    value = value.strip()
    if not value:
        return "não informado"
    return value


def group_by_responsible(teams: list[dict]) -> dict[str, dict]:
    groups = defaultdict(lambda: {"nome": "", "equipes": []})
    for team in teams:
        email = team["responsavel"]["email"]
        group = groups[email]
        group["nome"] = team["responsavel"]["nome"]
        group["equipes"].append(team)
    return dict(groups)


def format_team(team: dict) -> str:
    lines = [
        f"- Equipe {team['nome']} ({team['campus']})",
        f"  Responsável: {team['responsavel']['nome']} — camiseta: {team['responsavel']['camiseta']}",
        "  Participantes:",
    ]
    lines.extend(
        f"  - {participant['nome']} — camiseta: {participant['camiseta']}"
        for participant in team["participantes"]
    )
    return "\n".join(lines)


def render_email(data: dict) -> str:
    total = len(data["equipes"])
    lines = "\n\n".join(format_team(team) for team in data["equipes"])
    plural = "equipe" if total == 1 else "equipes"
    return (
        BANNER
        + f"Olá, {first_name(data['nome'])}!\n\n"
        + f"Seguem abaixo as {total} {plural} sob sua responsabilidade no {TITULO_EVENTO}, "
        + "com o tamanho de camiseta informado para cada participante e para o responsável.\n\n"
        + lines
        + "\n\nPedimos que confira os tamanhos listados acima. "
        + f"Se houver qualquer erro, envie um email para {EMAIL_INTERIF} o quanto antes "
        + "informando a equipe, a pessoa e o tamanho correto.\n\n"
        + "Atenciosamente,\n"
        + f"Organização {TITULO_EVENTO}"
    )


def send_responsible_emails(groups: dict[str, dict], dry_run: bool) -> tuple[int, int]:
    print("\n=== Emails para responsáveis confirmarem camisetas ===")
    sent = 0
    skipped = 0
    for email, data in groups.items():
        if not email:
            skipped += len(data["equipes"])
            print(
                f"  Aviso: responsável {data['nome']!r} sem email "
                f"({len(data['equipes'])} equipe(s)) — envio ignorado"
            )
            continue
        send_email(email, f"{SUBJECT} {_TIMESTAMP}", render_email(data), dry_run=dry_run)
        sent += 1
    return sent, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Envia emails para responsáveis confirmarem os tamanhos de camisetas."
    )
    parser.add_argument(
        "--csv",
        default=str(CSV_FILE),
        metavar="ARQUIVO",
        help=f"Caminho do CSV de equipes (padrão: {CSV_FILE.name})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula o envio sem disparar emails",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    teams = load_teams(Path(args.csv))
    groups = group_by_responsible(teams)

    print(f"Carregadas {len(teams)} equipes de '{args.csv}'.")
    sent, skipped = send_responsible_emails(groups, args.dry_run)
    print(f"\nPronto! {sent} email(s) processado(s), {skipped} equipe(s) sem email de responsável.")


if __name__ == "__main__":
    main()
