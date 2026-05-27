#!/usr/bin/env python3
"""
Lê equipes_interif.csv e lista equipes em categorias especiais.

Uso:
    uv run python lista_equipes_especiais.py
    uv run python lista_equipes_especiais.py --input equipes_interif.csv
    uv run python lista_equipes_especiais.py -o equipes_especiais.md
"""

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

from tabulate import tabulate

CSV_FILE = Path(__file__).parent / "equipes_interif.csv"

TEAM_NAME_COL = "Nome da Equipe"
CAMPUS_COL = "Campus"
WOMEN_COL = "Quantas mulheres na equipe?"
HIGH_SCHOOL_COL = "Composta apenas por alunos do ensino médio?"

REQUIRED_COLUMNS = [
    TEAM_NAME_COL,
    CAMPUS_COL,
    WOMEN_COL,
    HIGH_SCHOOL_COL,
]

@dataclass(frozen=True)
class Team:
    campus: str
    nome: str
    mulheres: int | None
    apenas_ensino_medio: bool


@dataclass
class TeamGroups:
    total_equipes: int
    ensino_medio: list[Team]
    tres_mulheres: list[Team]
    duas_mulheres: list[Team]
    uma_mulher: list[Team]
    demais: list[Team]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lista equipes especiais a partir de equipes_interif.csv."
    )
    parser.add_argument(
        "--input",
        "-i",
        metavar="ARQUIVO",
        default=str(CSV_FILE),
        help=f"Caminho do CSV de entrada (padrão: {CSV_FILE.name})",
    )
    parser.add_argument(
        "--output",
        "-o",
        metavar="ARQUIVO.md",
        help="Salva as listas também em um arquivo Markdown",
    )
    return parser.parse_args()


def parse_women_count(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_yes(value: str) -> bool:
    return value.strip().lower() == "sim"


def validate_headers(headers: list[str], csv_path: Path) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in headers]
    if missing:
        missing_fmt = ", ".join(missing)
        raise ValueError(f"Coluna(s) obrigatória(s) ausente(s) em {csv_path}: {missing_fmt}")


def load_teams(csv_path: Path) -> list[Team]:
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        if not headers:
            raise ValueError(f"CSV vazio: {csv_path}")
        validate_headers(headers, csv_path)

        teams: list[Team] = []
        for row in reader:
            nome = row.get(TEAM_NAME_COL, "").strip()
            campus = row.get(CAMPUS_COL, "").strip()
            if not nome or not campus:
                continue
            teams.append(
                Team(
                    campus=campus,
                    nome=nome,
                    mulheres=parse_women_count(row.get(WOMEN_COL, "")),
                    apenas_ensino_medio=parse_yes(row.get(HIGH_SCHOOL_COL, "")),
                )
            )

    teams.sort(key=lambda team: (team.campus.lower(), team.nome.lower()))
    return teams


def group_teams(teams: list[Team]) -> TeamGroups:
    groups = TeamGroups(len(teams), [], [], [], [], [])

    for team in teams:
        if team.apenas_ensino_medio:
            groups.ensino_medio.append(team)

        if team.mulheres == 3:
            groups.tres_mulheres.append(team)
        elif team.mulheres == 2:
            groups.duas_mulheres.append(team)
        elif team.mulheres == 1:
            groups.uma_mulher.append(team)

        if not team.apenas_ensino_medio and team.mulheres not in {1, 2, 3}:
            groups.demais.append(team)

    return groups


def high_school_text(team: Team) -> str:
    return "Sim" if team.apenas_ensino_medio else "Não"


def build_table(teams: list[Team], *, show_high_school: bool = False) -> str:
    headers = ["Campus", "Equipe"]
    rows: list[list[str]] = []
    if show_high_school:
        headers.append("Ensino médio")

    prev_campus = None
    for team in teams:
        campus_cell = ""
        if team.campus != prev_campus:
            campus_cell = team.campus
            prev_campus = team.campus

        row = [campus_cell, team.nome]
        if show_high_school:
            row.append(high_school_text(team))
        rows.append(row)

    if not teams:
        empty_row = ["-", "Nenhuma equipe"]
        if show_high_school:
            empty_row.append("-")
        rows.append(empty_row)

    return tabulate(rows, headers=headers, tablefmt="simple")


def group_tables(groups: TeamGroups) -> list[tuple[str, list[Team], bool]]:
    return [
        ("Apenas alunos do ensino médio integrado", groups.ensino_medio, False),
        ("Exatamente três mulheres", groups.tres_mulheres, True),
        ("Exatamente duas mulheres", groups.duas_mulheres, True),
        ("Exatamente uma mulher", groups.uma_mulher, True),
        ("Demais equipes", groups.demais, False),
    ]


def render(groups: TeamGroups, csv_path: Path) -> None:
    print("Equipes especiais - InterIF")
    print(f"Arquivo: {csv_path.resolve()}")
    print(f"Total de equipes carregadas: {groups.total_equipes}")
    print()

    for idx, (title, teams, show_high_school) in enumerate(group_tables(groups)):
        if idx:
            print()
        print(f"{title} ({len(teams)})")
        print(build_table(teams, show_high_school=show_high_school))


def render_markdown(groups: TeamGroups, csv_path: Path) -> str:
    lines = [
        "# Equipes especiais - InterIF",
        "",
        f"Arquivo: `{csv_path}`",
        f"Total de equipes carregadas: **{groups.total_equipes}**",
        "",
    ]

    for title, teams, show_high_school in group_tables(groups):
        lines.extend(
            [
                f"## {title} ({len(teams)})",
                "",
            ]
        )
        lines.extend(markdown_table(teams, show_high_school=show_high_school))
        lines.append("")

    return "\n".join(lines)


def markdown_cell(value: str) -> str:
    return value.replace("|", "\\|")


def markdown_table(teams: list[Team], *, show_high_school: bool = False) -> list[str]:
    headers = ["Campus", "Equipe"]
    rows: list[list[str]] = []

    if show_high_school:
        headers.append("Ensino médio")

    if teams:
        for team in teams:
            row = [markdown_cell(team.campus), markdown_cell(team.nome)]
            if show_high_school:
                row.append(high_school_text(team))
            rows.append(row)
    else:
        row = ["-", "Nenhuma equipe"]
        if show_high_school:
            row.append("-")
        rows.append(row)

    return tabulate(rows, headers=headers, tablefmt="github").splitlines()


def main() -> None:
    args = parse_args()
    csv_path = Path(args.input)

    if not csv_path.exists():
        print(f"Erro: arquivo não encontrado: {csv_path}", file=sys.stderr)
        sys.exit(1)

    try:
        teams = load_teams(csv_path)
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        sys.exit(1)

    groups = group_teams(teams)
    render(groups, csv_path)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(render_markdown(groups, csv_path), encoding="utf-8")
        print(f"\nMarkdown salvo em {output_path}")


if __name__ == "__main__":
    main()
