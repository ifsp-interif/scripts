#!/usr/bin/env python3
"""
Gera os gráficos de distribuição e de inscrições acumuladas a partir do CSV
de equipes produzido por equipes_interif.py.
"""

import argparse
import csv
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import matplotlib
import matplotlib.dates
import matplotlib.pyplot as plt
from tabulate import tabulate

from config import EMAIL_INTERIF, SPECIAL_SUMMARY_SUBJECT, TITULO_EVENTO
from email_utils import send_email

matplotlib.use("Agg")

CHART_OUTPUT_FILE = Path(__file__).parent / "distribuicao_equipes.png"
CUMULATIVE_CHART_FILE = Path(__file__).parent / "inscricoes_acumuladas.png"
COURSE_LEVEL_CHART_FILE = Path(__file__).parent / "distribuicao_nivel_curso.png"
COURSE_LEVEL_PIE_CHART_FILE = Path(__file__).parent / "distribuicao_nivel_ensino.png"
COURSE_NAME_BY_CAMPUS_CHART_FILE = Path(__file__).parent / "distribuicao_curso_por_campus.png"
COURSE_NAME_PIE_CHART_FILE = Path(__file__).parent / "distribuicao_curso.png"
COURSE_NAME_BY_CAMPUS_DIR = "cursos_por_campus"
HIGH_SCHOOL_CHART_FILE = Path(__file__).parent / "distribuicao_ensino_medio.png"
GENDER_CHART_FILE = Path(__file__).parent / "distribuicao_genero.png"
TEAM_SIZE_CHART_FILE = Path(__file__).parent / "distribuicao_tamanho_equipes.png"
WOMEN_PIE_CHART_FILE = Path(__file__).parent / "participacao_mulheres.png"
HIGH_SCHOOL_PIE_CHART_FILE = Path(__file__).parent / "participacao_ensino_medio.png"
INPUT_FILE = Path(__file__).parent / "equipes_interif.csv"
DEFAULT_CHART_DIR = Path(__file__).parent

# Nomes de colunas no CSV de entrada
CAMPUS_HEADER = "Campus"
TIMESTAMP_HEADER = "Carimbo de data/hora"
PARTICIPANT_NAME_PREFIX = "Nome Participante"
COURSE_LEVEL_HEADER = "Nível do curso"
COURSE_NAME_HEADER = "Nome do curso"
TEAM_NAME_HEADER = "Nome da Equipe"
WOMEN_HEADER = "Quantas mulheres na equipe?"
HIGH_SCHOOL_HEADER = "Composta apenas por alunos do ensino médio?"

SPECIAL_REQUIRED_COLUMNS = [
    TEAM_NAME_HEADER,
    CAMPUS_HEADER,
    WOMEN_HEADER,
    HIGH_SCHOOL_HEADER,
]


@dataclass(frozen=True)
class Team:
    campus: str
    nome: str
    mulheres: int | None
    apenas_ensino_medio: bool
    participantes: int


@dataclass
class TeamGroups:
    total_equipes: int
    ensino_medio: list[Team]
    tres_mulheres: list[Team]
    duas_mulheres: list[Team]
    uma_mulher: list[Team]
    demais: list[Team]


# ── Helpers ───────────────────────────────────────────────────────────────────


def read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _read_participant_col_counts(path: Path, col_header: str) -> dict[str, Counter[str]]:
    """Conta, por campus, os valores de `col_header` para cada participante presente."""
    counts: dict[str, Counter[str]] = defaultdict(Counter)

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)

        try:
            campus_idx = header.index(CAMPUS_HEADER)
        except ValueError as exc:
            raise ValueError(f"Coluna obrigatória ausente: {CAMPUS_HEADER}") from exc

        participant_name_idxs = [
            idx for idx, name in enumerate(header) if name.startswith(PARTICIPANT_NAME_PREFIX)
        ]
        col_idxs = [idx for idx, name in enumerate(header) if name == col_header]

        if len(participant_name_idxs) != len(col_idxs):
            raise ValueError(
                "Número de colunas de participante não corresponde ao número "
                f"de colunas {col_header!r}."
            )

        for row in reader:
            campus = _cell(row, campus_idx).strip() or "Não informado"
            for participant_idx, col_idx in zip(participant_name_idxs, col_idxs, strict=True):
                participant_name = _cell(row, participant_idx).strip()
                value = _cell(row, col_idx).strip()

                if not participant_name and not value:
                    continue

                counts[campus][value or "Não informado"] += 1

    return dict(counts)


def read_course_level_counts(path: Path) -> dict[str, Counter[str]]:
    return _read_participant_col_counts(path, COURSE_LEVEL_HEADER)


def read_course_name_counts(path: Path) -> dict[str, Counter[str]]:
    counts_by_campus = _read_participant_col_counts(path, COURSE_NAME_HEADER)
    variants_by_key: dict[str, Counter[str]] = defaultdict(Counter)

    for course_counts in counts_by_campus.values():
        for course, count in course_counts.items():
            display_name = " ".join(course.split())
            variants_by_key[display_name.casefold()][display_name] += count

    canonical_names = {
        key: variants.most_common(1)[0][0] for key, variants in variants_by_key.items()
    }
    normalized_counts: dict[str, Counter[str]] = {}

    for campus, course_counts in counts_by_campus.items():
        normalized_counts[campus] = Counter()
        for course, count in course_counts.items():
            display_name = " ".join(course.split())
            canonical_name = canonical_names[display_name.casefold()]
            normalized_counts[campus][canonical_name] += count

    return normalized_counts


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


def validate_special_headers(headers: list[str], csv_path: Path) -> None:
    missing = [column for column in SPECIAL_REQUIRED_COLUMNS if column not in headers]
    if missing:
        missing_fmt = ", ".join(missing)
        raise ValueError(f"Coluna(s) obrigatória(s) ausente(s) em {csv_path}: {missing_fmt}")


def load_teams(csv_path: Path) -> list[Team]:
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        if not headers:
            raise ValueError(f"CSV vazio: {csv_path}")
        validate_special_headers(headers, csv_path)

        teams: list[Team] = []
        for row in reader:
            nome = row.get(TEAM_NAME_HEADER, "").strip()
            campus = row.get(CAMPUS_HEADER, "").strip()
            if not nome or not campus:
                continue
            participantes = sum(
                1
                for header, value in row.items()
                if header
                and header.startswith(PARTICIPANT_NAME_PREFIX)
                and (value or "").strip()
            )
            teams.append(
                Team(
                    campus=campus,
                    nome=nome,
                    mulheres=parse_women_count(row.get(WOMEN_HEADER, "")),
                    apenas_ensino_medio=parse_yes(row.get(HIGH_SCHOOL_HEADER, "")),
                    participantes=participantes,
                )
            )

    teams.sort(key=lambda team: (team.campus.lower(), team.nome.lower()))
    return teams


def _cell(row: list[str], idx: int) -> str:
    if idx >= len(row):
        return ""
    return row[idx]


def _filename_slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.casefold()).strip("_") or "campus"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gera gráficos a partir do CSV de equipes do InterIF."
    )
    parser.add_argument(
        "--input",
        "-i",
        metavar="ARQUIVO",
        default=str(INPUT_FILE),
        help=f"CSV de equipes de entrada (padrão: {INPUT_FILE.name})",
    )
    parser.add_argument(
        "--charts-dir",
        metavar="DIRETORIO",
        default=str(DEFAULT_CHART_DIR),
        help=(
            "Diretório onde os gráficos serão salvos; criado se não existir "
            f"(padrão: {DEFAULT_CHART_DIR})"
        ),
    )
    parser.add_argument(
        "--output",
        "-o",
        metavar="ARQUIVO.md",
        help="Salva a lista de equipes especiais (ou o resumo, com --resumo) em Markdown",
    )
    parser.add_argument(
        "--resumo",
        action="store_true",
        help=(
            "Gera e envia o quadro resumo para interif@ifsp.edu.br; não lista equipes individuais"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Com --resumo: imprime o e-mail sem enviá-lo",
    )
    parser.add_argument(
        "--course-charts-by-campus",
        action="store_true",
        help=(
            "Além do gráfico combinado, gera um gráfico de distribuição de cursos "
            "para cada campus"
        ),
    )
    return parser.parse_args()


# ── Special team lists ────────────────────────────────────────────────────────


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


def build_summary(groups: TeamGroups) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for title, teams, _ in group_tables(groups):
        campus_counts: dict[str, int] = {}
        for team in teams:
            campus_counts[team.campus] = campus_counts.get(team.campus, 0) + 1
        summary[title] = campus_counts
    return summary


def render_summary(groups: TeamGroups, csv_path: Path) -> str:
    lines = [
        "Quadro resumo — Equipes especiais",
        f"Arquivo: {csv_path.resolve()}",
        f"Total de equipes: {groups.total_equipes}",
    ]
    for title, campus_counts in build_summary(groups).items():
        total_cat = sum(campus_counts.values())
        lines.append("")
        lines.append(f"{title} ({total_cat})")
        for campus in sorted(campus_counts):
            lines.append(f"  {campus}: {campus_counts[campus]}")
    return "\n".join(lines)


def render_summary_markdown(groups: TeamGroups, csv_path: Path) -> str:
    lines = [
        "# Quadro resumo — Equipes especiais",
        "",
        f"Arquivo: `{csv_path}`",
        f"Total de equipes: **{groups.total_equipes}**",
        "",
    ]
    for title, campus_counts in build_summary(groups).items():
        total_cat = sum(campus_counts.values())
        lines.append(f"## {title} ({total_cat})")
        lines.append("")
        if campus_counts:
            rows = [[campus, campus_counts[campus]] for campus in sorted(campus_counts)]
            lines.extend(
                tabulate(rows, headers=["Campus", "Equipes"], tablefmt="github").splitlines()
            )
        else:
            lines.append("*(nenhuma equipe)*")
        lines.append("")
    return "\n".join(lines)


def render_special_lists(groups: TeamGroups, csv_path: Path) -> None:
    print("Equipes especiais - InterIF")
    print(f"Arquivo: {csv_path.resolve()}")
    print(f"Total de equipes carregadas: {groups.total_equipes}")
    print()

    for idx, (title, teams, show_high_school) in enumerate(group_tables(groups)):
        if idx:
            print()
        print(f"{title} ({len(teams)})")
        print(build_table(teams, show_high_school=show_high_school))


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


# ── Charts ────────────────────────────────────────────────────────────────────


def generate_pie_chart(campus_counts: dict[str, int], chart_path: Path) -> None:
    labels = list(campus_counts.keys())
    sizes = list(campus_counts.values())
    total = sum(sizes)

    fig, ax = plt.subplots(figsize=(10, 8))

    wedges, _, autotexts = ax.pie(
        sizes,
        labels=None,
        autopct="%1.1f%%",
        startangle=140,
        pctdistance=1.18,
    )
    for autotext in autotexts:
        autotext.set_fontsize(8)

    ax.legend(
        wedges,
        [f"{label} ({count})" for label, count in zip(labels, sizes, strict=True)],
        title="Campus",
        loc="upper center",
        bbox_to_anchor=(0.5, -0.05),
        ncols=3,
        fontsize=9,
    )
    ax.set_title(
        f"Distribuição de Equipes por Campus\n{TITULO_EVENTO} — {total} equipes no total",
        pad=20,
    )

    plt.tight_layout()
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Gráfico de distribuição salvo em {chart_path}")


def generate_cumulative_chart(rows: list[dict[str, str]], chart_path: Path) -> None:
    parsed_dates: list[date] = []
    for row in rows:
        raw = row.get(TIMESTAMP_HEADER, "").strip()
        if not raw:
            continue
        # Google Forms timestamps: "DD/MM/YYYY HH:MM:SS"
        try:
            day_str = raw.split(" ")[0]
            d, m, y = day_str.split("/")
            parsed_dates.append(date(int(y), int(m), int(d)))
        except (ValueError, IndexError):
            continue

    if not parsed_dates:
        print("Aviso: nenhuma data encontrada para o gráfico acumulado.")
        return

    first_day = min(parsed_dates)
    last_day = max(parsed_dates)
    total_days = (last_day - first_day).days + 1

    all_days = [first_day + timedelta(days=i) for i in range(total_days)]
    counts_by_day: dict[date, int] = {}
    for d in parsed_dates:
        counts_by_day[d] = counts_by_day.get(d, 0) + 1

    cumulative = 0
    xs: list[date] = []
    ys: list[int] = []
    for d in all_days:
        cumulative += counts_by_day.get(d, 0)
        xs.append(d)
        ys.append(cumulative)

    # Extra point so the final step is visible instead of being cut off at xlim
    xs.append(last_day + timedelta(days=1))
    ys.append(cumulative)

    total = cumulative
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.step(xs, ys, where="post", linewidth=2, color="#1f77b4")
    ax.fill_between(xs, ys, step="post", alpha=0.15, color="#1f77b4")

    ax.set_xlim(first_day, last_day + timedelta(days=1))
    ax.set_ylim(0, total * 1.08)
    ax.set_xlabel("Data")
    ax.set_ylabel("Equipes inscritas (acumulado)")
    ax.set_title(
        f"Inscrições Acumuladas de Equipes\n{TITULO_EVENTO} — {total} equipes no total",
        pad=14,
    )
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%d/%m"))
    ax.xaxis.set_major_locator(matplotlib.dates.DayLocator())
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", fontsize=8)
    ax.yaxis.get_major_locator().set_params(integer=True)
    ax.grid(axis="y", linestyle="--", alpha=0.4)

    plt.tight_layout()
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Gráfico acumulado salvo em {chart_path}")


def _bar_labels(ax: plt.Axes, lefts: list[int], widths: list[int], ys: range) -> None:
    for y, left, width in zip(ys, lefts, widths, strict=True):
        if width <= 0:
            continue
        ax.text(
            left + width / 2,
            y,
            str(width),
            ha="center",
            va="center",
            fontsize=8,
            color="black",
        )


def generate_course_level_chart(
    counts_by_campus: dict[str, Counter[str]], chart_path: Path
) -> None:
    total_by_campus = {
        campus: sum(level_counts.values()) for campus, level_counts in counts_by_campus.items()
    }
    if not total_by_campus:
        print("Aviso: nenhum participante encontrado para o gráfico de nível do curso.")
        return

    campuses = sorted(total_by_campus, key=total_by_campus.get, reverse=True)
    levels = [
        level
        for level, _ in Counter(
            level for level_counts in counts_by_campus.values() for level in level_counts
        ).most_common()
    ]
    ys = range(len(campuses))
    total_participants = sum(total_by_campus.values())

    colors = [
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728",
        "#9467bd",
        "#8c564b",
        "#e377c2",
        "#7f7f7f",
    ]

    fig, ax = plt.subplots(figsize=(10, max(4, len(campuses) * 0.42)))
    lefts = [0] * len(campuses)

    for idx, level in enumerate(levels):
        values = [counts_by_campus[campus][level] for campus in campuses]
        ax.barh(
            list(ys),
            values,
            left=lefts,
            color=colors[idx % len(colors)],
            label=level,
        )
        _bar_labels(ax, lefts, values, ys)
        lefts = [left + value for left, value in zip(lefts, values, strict=True)]

    ax.set_yticks(list(ys))
    ax.set_yticklabels(campuses, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Número de participantes")
    ax.set_title(
        "Distribuição de nível do curso dos participantes por campi\n"
        f"{TITULO_EVENTO} — {total_participants} participantes no total",
        pad=12,
    )
    ax.legend(loc="lower right", fontsize=9)
    ax.set_xlim(0, max(total_by_campus.values()) * 1.08)

    plt.tight_layout()
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Gráfico de nível do curso salvo em {chart_path}")


def generate_course_level_pie_chart(
    counts_by_campus: dict[str, Counter[str]], chart_path: Path
) -> None:
    totals: Counter[str] = Counter()
    for level_counts in counts_by_campus.values():
        totals.update(level_counts)

    if not totals:
        print("Aviso: nenhum participante encontrado para o gráfico de pizza por nível.")
        return

    levels, sizes = zip(*totals.most_common(), strict=True)
    total = sum(sizes)

    fig, ax = plt.subplots(figsize=(10, 8))

    wedges, _, autotexts = ax.pie(
        sizes,
        labels=None,
        autopct="%1.1f%%",
        startangle=140,
        pctdistance=1.18,
    )
    for autotext in autotexts:
        autotext.set_fontsize(8)

    ax.legend(
        wedges,
        [f"{level} ({count})" for level, count in zip(levels, sizes, strict=True)],
        title="Nível de ensino",
        loc="upper center",
        bbox_to_anchor=(0.5, -0.05),
        ncols=2,
        fontsize=9,
    )
    ax.set_title(
        "Distribuição de Participantes por Nível de Ensino\n"
        f"{TITULO_EVENTO} — {total} participantes no total",
        pad=20,
    )

    plt.tight_layout()
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Gráfico de pizza por nível de ensino salvo em {chart_path}")


def generate_course_name_by_campus_chart(
    counts_by_campus: dict[str, Counter[str]], chart_path: Path
) -> None:
    total_by_campus = {
        campus: sum(level_counts.values()) for campus, level_counts in counts_by_campus.items()
    }
    if not total_by_campus:
        print("Aviso: nenhum participante encontrado para o gráfico de curso por campus.")
        return

    campuses = sorted(total_by_campus, key=total_by_campus.get, reverse=True)
    courses = [
        course
        for course, _ in Counter(
            course for course_counts in counts_by_campus.values() for course in course_counts
        ).most_common()
    ]
    ys = range(len(campuses))
    total_participants = sum(total_by_campus.values())

    colors = [
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728",
        "#9467bd",
        "#8c564b",
        "#e377c2",
        "#7f7f7f",
        "#bcbd22",
        "#17becf",
        "#aec7e8",
        "#ffbb78",
        "#98df8a",
        "#ff9896",
        "#c5b0d5",
    ]

    fig, ax = plt.subplots(figsize=(12, max(4, len(campuses) * 0.42)))
    lefts = [0] * len(campuses)

    for idx, course in enumerate(courses):
        values = [counts_by_campus[campus][course] for campus in campuses]
        ax.barh(
            list(ys),
            values,
            left=lefts,
            color=colors[idx % len(colors)],
            label=course,
        )
        _bar_labels(ax, lefts, values, ys)
        lefts = [left + value for left, value in zip(lefts, values, strict=True)]

    ax.set_yticks(list(ys))
    ax.set_yticklabels(campuses, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Número de participantes")
    ax.set_title(
        "Distribuição de participantes por curso e campus\n"
        f"{TITULO_EVENTO} — {total_participants} participantes no total",
        pad=12,
    )
    ax.legend(loc="lower right", fontsize=8, ncols=2)
    ax.set_xlim(0, max(total_by_campus.values()) * 1.08)

    plt.tight_layout()
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Gráfico de curso por campus salvo em {chart_path}")


def generate_course_name_charts_by_campus(
    counts_by_campus: dict[str, Counter[str]], output_dir: Path
) -> None:
    if not counts_by_campus:
        print("Aviso: nenhum participante encontrado para os gráficos por campus.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    used_slugs: Counter[str] = Counter()

    for campus in sorted(counts_by_campus, key=str.casefold):
        course_counts = counts_by_campus[campus]
        if not course_counts:
            continue

        courses_and_counts = course_counts.most_common()
        courses = [course for course, _ in courses_and_counts]
        values = [count for _, count in courses_and_counts]
        total = sum(values)
        ys = range(len(courses))

        fig, ax = plt.subplots(figsize=(11, max(4, len(courses) * 0.5)))
        bars = ax.barh(list(ys), values, color="#1f77b4")

        ax.set_yticks(list(ys))
        ax.set_yticklabels(courses, fontsize=9)
        ax.invert_yaxis()
        ax.set_xlabel("Número de participantes")
        ax.set_title(
            f"Distribuição de participantes por curso — {campus}\n"
            f"{TITULO_EVENTO} — {total} participantes no total",
            pad=12,
        )
        ax.set_xlim(0, max(values) * 1.12)
        ax.bar_label(bars, labels=[str(value) for value in values], padding=3, fontsize=8)
        ax.grid(axis="x", linestyle="--", alpha=0.3)

        slug = _filename_slug(campus)
        used_slugs[slug] += 1
        if used_slugs[slug] > 1:
            slug = f"{slug}_{used_slugs[slug]}"
        chart_path = output_dir / f"distribuicao_curso_{slug}.png"

        plt.tight_layout()
        fig.savefig(chart_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"Gráfico de cursos de {campus} salvo em {chart_path}")


def generate_course_name_pie_chart(
    counts_by_campus: dict[str, Counter[str]], chart_path: Path
) -> None:
    totals: Counter[str] = Counter()
    for course_counts in counts_by_campus.values():
        totals.update(course_counts)

    if not totals:
        print("Aviso: nenhum participante encontrado para o gráfico de pizza por curso.")
        return

    courses, sizes = zip(*totals.most_common(), strict=True)
    total = sum(sizes)

    fig, ax = plt.subplots(figsize=(10, 8))

    wedges, _, autotexts = ax.pie(
        sizes,
        labels=None,
        autopct="%1.1f%%",
        startangle=140,
        pctdistance=1.18,
    )
    for autotext in autotexts:
        autotext.set_fontsize(8)

    ax.legend(
        wedges,
        [f"{course} ({count})" for course, count in zip(courses, sizes, strict=True)],
        title="Curso",
        loc="upper center",
        bbox_to_anchor=(0.5, -0.05),
        ncols=2,
        fontsize=8,
    )
    ax.set_title(
        f"Distribuição de Participantes por Curso\n{TITULO_EVENTO} — {total} participantes no total",
        pad=20,
    )

    plt.tight_layout()
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Gráfico de pizza por curso salvo em {chart_path}")


def _campus_order(teams: list[Team]) -> list[str]:
    """Campuses ordenados por total de equipes crescente (maior fica no topo do barh)."""
    total = Counter(team.campus for team in teams)
    return sorted(total, key=lambda campus: total[campus])


def generate_high_school_chart(teams: list[Team], chart_path: Path) -> None:
    if not teams:
        print("Aviso: nenhuma equipe encontrada para o gráfico de ensino médio.")
        return

    campuses = _campus_order(teams)
    total_campus = Counter(team.campus for team in teams)
    high_school_campus = Counter(team.campus for team in teams if team.apenas_ensino_medio)

    high_school = [high_school_campus[campus] for campus in campuses]
    others = [total_campus[campus] - high_school_campus[campus] for campus in campuses]
    ys = range(len(campuses))

    fig, ax = plt.subplots(figsize=(10, max(4, len(campuses) * 0.42)))

    ax.barh(list(ys), high_school, color="#43a047", label="Ensino médio integrado")
    ax.barh(list(ys), others, left=high_school, color="#bdbdbd", label="Demais equipes")

    _bar_labels(ax, [0] * len(campuses), high_school, ys)
    _bar_labels(ax, high_school, others, ys)

    ax.set_yticks(list(ys))
    ax.set_yticklabels(campuses, fontsize=9)
    ax.set_xlabel("Número de equipes")
    ax.set_title(
        "Equipes exclusivamente de ensino médio integrado por campi\n"
        f"{TITULO_EVENTO} — {len(teams)} equipes no total",
        pad=12,
    )
    ax.legend(loc="lower right", fontsize=9)
    ax.set_xlim(0, max(total_campus.values()) * 1.08)

    plt.tight_layout()
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Gráfico de ensino médio salvo em {chart_path}")


def generate_gender_chart(teams: list[Team], chart_path: Path) -> None:
    if not teams:
        print("Aviso: nenhuma equipe encontrada para o gráfico de gênero.")
        return

    campuses = _campus_order(teams)
    total_campus = Counter(team.campus for team in teams)
    count_3 = Counter(team.campus for team in teams if team.mulheres == 3)
    count_2 = Counter(team.campus for team in teams if team.mulheres == 2)
    count_1 = Counter(team.campus for team in teams if team.mulheres == 1)

    three = [count_3[campus] for campus in campuses]
    two = [count_2[campus] for campus in campuses]
    one = [count_1[campus] for campus in campuses]
    none = [
        total_campus[campus] - count_3[campus] - count_2[campus] - count_1[campus]
        for campus in campuses
    ]
    ys = range(len(campuses))

    fig, ax = plt.subplots(figsize=(10, max(4, len(campuses) * 0.42)))

    left_3 = [0] * len(campuses)
    left_2 = three
    left_1 = [a + b for a, b in zip(three, two, strict=True)]
    left_0 = [a + b for a, b in zip(left_1, one, strict=True)]

    ax.barh(list(ys), three, left=left_3, color="#7b1fa2", label="3 mulheres")
    ax.barh(list(ys), two, left=left_2, color="#ce93d8", label="2 mulheres")
    ax.barh(list(ys), one, left=left_1, color="#f3e5f5", label="1 mulher")
    ax.barh(list(ys), none, left=left_0, color="#bdbdbd", label="Nenhuma mulher")

    _bar_labels(ax, left_3, three, ys)
    _bar_labels(ax, left_2, two, ys)
    _bar_labels(ax, left_1, one, ys)
    _bar_labels(ax, left_0, none, ys)

    ax.set_yticks(list(ys))
    ax.set_yticklabels(campuses, fontsize=9)
    ax.set_xlabel("Número de equipes")
    ax.set_title(
        "Composição por gênero das equipes por campi\n"
        f"{TITULO_EVENTO} — {len(teams)} equipes no total",
        pad=12,
    )
    ax.legend(loc="lower right", fontsize=9)
    ax.set_xlim(0, max(total_campus.values()) * 1.08)

    plt.tight_layout()
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Gráfico de gênero salvo em {chart_path}")


def _two_slice_pie(
    sizes: list[int],
    labels: list[str],
    colors: list[str],
    title: str,
    legend_title: str,
    chart_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(10, 8))

    wedges, _, autotexts = ax.pie(
        sizes,
        labels=None,
        autopct="%1.1f%%",
        startangle=140,
        pctdistance=0.7,
        colors=colors,
    )
    for autotext in autotexts:
        autotext.set_fontsize(10)
        autotext.set_color("white")
        autotext.set_fontweight("bold")

    ax.legend(
        wedges,
        [f"{label} ({size})" for label, size in zip(labels, sizes, strict=True)],
        title=legend_title,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.05),
        ncols=2,
        fontsize=10,
    )
    ax.set_title(title, pad=20)

    plt.tight_layout()
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def generate_team_size_chart(teams: list[Team], chart_path: Path) -> None:
    if not teams:
        print("Aviso: nenhuma equipe encontrada para o gráfico de tamanho das equipes.")
        return

    counts = Counter(team.participantes for team in teams)
    sizes = [3, 2, 1]
    values = [counts.get(size, 0) for size in sizes]
    labels = [f"{size} participantes" if size != 1 else "1 participante" for size in sizes]
    colors = ["#1565c0", "#42a5f5", "#bbdefb"]
    total = len(teams)

    fig, ax = plt.subplots(figsize=(11, 3.2))
    lefts = [sum(values[:idx]) for idx in range(len(values))]

    for value, left, label, color in zip(values, lefts, labels, colors, strict=True):
        if value <= 0:
            continue
        ax.barh(0, value, left=left, color=color, label=label)
        ax.text(
            left + value / 2,
            0,
            str(value),
            ha="center",
            va="center",
            fontsize=10,
            color="black",
        )

    ax.set_yticks([])
    ax.set_xlabel("Número de equipes")
    ax.set_xlim(0, total)
    ax.set_title(
        "Distribuição de equipes por número de participantes\n"
        f"{TITULO_EVENTO} — {total} equipes no total",
        pad=12,
    )
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.55),
        ncols=len(sizes),
        fontsize=9,
    )

    plt.tight_layout()
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Gráfico de tamanho das equipes salvo em {chart_path}")


def generate_women_pie_chart(teams: list[Team], chart_path: Path) -> None:
    if not teams:
        print("Aviso: nenhuma equipe encontrada para o gráfico de participação de mulheres.")
        return

    total_participantes = sum(team.participantes for team in teams)
    mulheres = sum(team.mulheres or 0 for team in teams)

    if total_participantes <= 0:
        print("Aviso: nenhum participante encontrado para o gráfico de participação de mulheres.")
        return

    demais = max(total_participantes - mulheres, 0)
    _two_slice_pie(
        sizes=[mulheres, demais],
        labels=["Mulheres", "Demais inscritos"],
        colors=["#d81b60", "#bdbdbd"],
        title=(
            "Participação de mulheres entre os inscritos\n"
            f"{TITULO_EVENTO} — {total_participantes} inscritos no total"
        ),
        legend_title="Participantes",
        chart_path=chart_path,
    )
    print(f"Gráfico de participação de mulheres salvo em {chart_path}")


def generate_high_school_pie_chart(teams: list[Team], chart_path: Path) -> None:
    if not teams:
        print("Aviso: nenhuma equipe encontrada para o gráfico de participação do ensino médio.")
        return

    total = len(teams)
    apenas_em = sum(1 for team in teams if team.apenas_ensino_medio)
    demais = total - apenas_em

    _two_slice_pie(
        sizes=[apenas_em, demais],
        labels=["Apenas ensino médio", "Demais equipes"],
        colors=["#43a047", "#bdbdbd"],
        title=(
            "Equipes compostas apenas por alunos do ensino médio\n"
            f"{TITULO_EVENTO} — {total} equipes no total"
        ),
        legend_title="Equipes",
        chart_path=chart_path,
    )
    print(f"Gráfico de participação do ensino médio salvo em {chart_path}")


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        print(f"Erro: arquivo não encontrado: {input_path}", file=sys.stderr)
        sys.exit(1)

    try:
        teams = load_teams(input_path)
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        sys.exit(1)

    groups = group_teams(teams)

    if args.resumo:
        body = render_summary(groups, input_path)
        print(body)
        print()
        send_email(EMAIL_INTERIF, SPECIAL_SUMMARY_SUBJECT, body, dry_run=args.dry_run)
        if args.output:
            output_path = Path(args.output)
            output_path.write_text(render_summary_markdown(groups, input_path), encoding="utf-8")
            print(f"\nMarkdown salvo em {output_path}")
        return

    rows = read_csv(input_path)
    print(f"{len(rows)} equipes lidas de {input_path}")
    print()
    render_special_lists(groups, input_path)
    print()

    campus_counts: dict[str, int] = {}
    for row in rows:
        campus = row.get(CAMPUS_HEADER, "").strip() or "Não informado"
        campus_counts[campus] = campus_counts.get(campus, 0) + 1
    campus_counts = dict(sorted(campus_counts.items(), key=lambda x: x[1], reverse=True))

    charts_dir = Path(args.charts_dir)
    charts_dir.mkdir(parents=True, exist_ok=True)

    generate_pie_chart(campus_counts, charts_dir / CHART_OUTPUT_FILE.name)
    generate_cumulative_chart(rows, charts_dir / CUMULATIVE_CHART_FILE.name)
    course_level_counts = read_course_level_counts(input_path)
    course_name_counts = read_course_name_counts(input_path)
    generate_course_level_chart(
        course_level_counts,
        charts_dir / COURSE_LEVEL_CHART_FILE.name,
    )
    generate_course_level_pie_chart(
        course_level_counts,
        charts_dir / COURSE_LEVEL_PIE_CHART_FILE.name,
    )
    generate_course_name_by_campus_chart(
        course_name_counts,
        charts_dir / COURSE_NAME_BY_CAMPUS_CHART_FILE.name,
    )
    if args.course_charts_by_campus:
        generate_course_name_charts_by_campus(
            course_name_counts,
            charts_dir / COURSE_NAME_BY_CAMPUS_DIR,
        )
    generate_course_name_pie_chart(
        course_name_counts,
        charts_dir / COURSE_NAME_PIE_CHART_FILE.name,
    )
    generate_high_school_chart(teams, charts_dir / HIGH_SCHOOL_CHART_FILE.name)
    generate_gender_chart(teams, charts_dir / GENDER_CHART_FILE.name)
    generate_team_size_chart(teams, charts_dir / TEAM_SIZE_CHART_FILE.name)
    generate_women_pie_chart(teams, charts_dir / WOMEN_PIE_CHART_FILE.name)
    generate_high_school_pie_chart(teams, charts_dir / HIGH_SCHOOL_PIE_CHART_FILE.name)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(render_markdown(groups, input_path), encoding="utf-8")
        print(f"\nMarkdown salvo em {output_path}")


if __name__ == "__main__":
    main()
