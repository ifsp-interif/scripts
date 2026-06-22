#!/usr/bin/env python3
"""
Seleciona as equipes classificadas para a fase seguinte do InterIF com base
na coluna "Classificação na prova da Fase Local" (posição no ranking: 1 = melhor).

Critérios (em ordem de aplicação):
  Inciso I   – melhor equipe de cada campus
  Inciso II  – top --geral equipes na classificação geral (excluídas as do I)
  Inciso III – top --medio equipes exclusivamente de ensino médio integrado,
               máx. 1 por campus (excluídas as dos incisos I e II)
  Inciso IV  – top --mulheres equipes exclusivamente femininas (excluídas as dos
               incisos I, II e III); fallback progressivo: ≥2 mulheres, ≥1 mulher
"""

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt

matplotlib.use("Agg")

SHEET_NAME = "Respostas ao formulário 1"
OUTPUT_FILE = Path(__file__).parent / "classificados_interif.csv"
CHART_FILE = Path(__file__).parent / "classificados_interif.png"

def _parse_women_count(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_yes(value: str) -> bool:
    return value.strip().lower() == "sim"


SCORE_HEADER = "Classificação na prova da Fase Local"
WOMEN_HEADER = "Quantas mulheres na equipe?"
HIGH_SCHOOL_HEADER = "Composta apenas por alunos do ensino médio?"

# Posições fixas no sheet bruto (mesmas constantes de equipes_interif.py).
# Esses campos têm nomes originais do Google Forms que diferem dos nomes canônicos.
_TEAM_NAME_COL = 2
_CAMPUS_COL = 3
_PART_NOME_COLS = [11, 18, 25]  # Nome Participante 1, 2, 3


@dataclass
class Team:
    nome: str
    campus: str
    rank: int
    mulheres: int | None
    apenas_medio: bool
    participantes: int  # número de slots preenchidos
    part_nomes: list[str]  # sempre 3 elementos; vazio = ""


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
    rows = [r + [""] * (len(headers) - len(r)) for r in rows]
    return headers, rows


def _cell(row: list[str], idx: int) -> str:
    return row[idx].strip() if idx < len(row) else ""


def _active_participants(nomes: list[str]) -> int:
    return sum(1 for n in nomes if n and n != "--")


def _find_col(headers: list[str], name: str) -> int:
    try:
        return headers.index(name)
    except ValueError as exc:
        raise ValueError(f"Coluna obrigatória não encontrada na planilha: '{name}'") from exc


def load_teams(headers: list[str], rows: list[list[str]]) -> list[Team]:
    i_mulheres = _find_col(headers, WOMEN_HEADER)
    i_medio = _find_col(headers, HIGH_SCHOOL_HEADER)
    i_score = _find_col(headers, SCORE_HEADER)

    teams: list[Team] = []
    skipped_no_rank = 0

    for row in rows:
        nome = _cell(row, _TEAM_NAME_COL)
        campus = _cell(row, _CAMPUS_COL)
        if not nome or not campus:
            continue

        raw_rank = _cell(row, i_score)
        if not raw_rank:
            skipped_no_rank += 1
            continue
        try:
            rank = int(raw_rank)
        except ValueError:
            skipped_no_rank += 1
            continue

        part_nomes = [_cell(row, i) for i in _PART_NOME_COLS]

        teams.append(
            Team(
                nome=nome,
                campus=campus,
                rank=rank,
                mulheres=_parse_women_count(_cell(row, i_mulheres)),
                apenas_medio=_parse_yes(_cell(row, i_medio)),
                participantes=_active_participants(part_nomes),
                part_nomes=part_nomes,
            )
        )

    if skipped_no_rank:
        print(
            f"Aviso: {skipped_no_rank} equipe(s) sem classificação — ignoradas na seleção.",
            file=sys.stderr,
        )

    return teams


# ── Seleção ───────────────────────────────────────────────────────────────────


def selecionar(
    teams: list[Team],
    *,
    n_geral: int,
    n_medio: int,
    n_mulheres: int,
) -> list[tuple[str, Team]]:
    """
    Retorna lista de (critério, team) na ordem dos incisos, com rank ASC dentro
    de cada inciso.
    """
    sorted_teams = sorted(teams, key=lambda t: t.rank)
    selected: set[int] = set()  # índices em sorted_teams

    def pick(predicate, limit: int, *, max_one_per_campus: bool = False) -> list[Team]:
        chosen: list[Team] = []
        campus_seen: set[str] = set()
        for i, team in enumerate(sorted_teams):
            if len(chosen) >= limit:
                break
            if i in selected:
                continue
            if max_one_per_campus and team.campus in campus_seen:
                continue
            if not predicate(team):
                continue
            chosen.append(team)
            selected.add(i)
            campus_seen.add(team.campus)
        return chosen

    # Inciso I — melhor classificação por campus
    campus_best: dict[str, Team] = {}
    inciso_i: list[Team] = []
    for i, team in enumerate(sorted_teams):
        if team.campus not in campus_best:
            campus_best[team.campus] = team
            inciso_i.append(team)
            selected.add(i)

    # Inciso II — top n_geral na classificação geral
    inciso_ii = pick(lambda _: True, n_geral)

    # Inciso III — top n_medio exclusivamente ensino médio, máx 1 por campus
    inciso_iii = pick(lambda t: t.apenas_medio, n_medio, max_one_per_campus=True)

    # Inciso IV — exclusivamente mulheres, com fallback progressivo (§1)
    inciso_iv: list[Team] = []
    for threshold in (
        lambda t: t.mulheres is not None and t.mulheres == t.participantes,
        lambda t: t.mulheres is not None and t.mulheres >= 2,
        lambda t: t.mulheres is not None and t.mulheres >= 1,
    ):
        if len(inciso_iv) >= n_mulheres:
            break
        remaining = n_mulheres - len(inciso_iv)
        for i, team in enumerate(sorted_teams):
            if remaining <= 0:
                break
            if i in selected:
                continue
            if not threshold(team):
                continue
            inciso_iv.append(team)
            selected.add(i)
            remaining -= 1

    result: list[tuple[str, Team]] = []
    for label, group in (
        ("Inciso I", inciso_i),
        ("Inciso II", inciso_ii),
        ("Inciso III", inciso_iii),
        ("Inciso IV", inciso_iv),
    ):
        for team in group:
            result.append((label, team))

    return result


# ── Gráfico ──────────────────────────────────────────────────────────────────


_INCISO_COLORS = {
    "Inciso I": "#1f77b4",
    "Inciso II": "#ff7f0e",
    "Inciso III": "#2ca02c",
    "Inciso IV": "#d62728",
}


def generate_chart(classificados: list[tuple[str, Team]], chart_path: Path) -> None:
    campus_inciso: dict[str, dict[str, int]] = {}
    for criterio, team in classificados:
        campus_inciso.setdefault(team.campus, {}).setdefault(criterio, 0)
        campus_inciso[team.campus][criterio] += 1

    campus_total = {c: sum(v.values()) for c, v in campus_inciso.items()}
    campuses = sorted(campus_inciso, key=lambda c: (-campus_total[c], c))
    incisos = list(_INCISO_COLORS)
    ys = range(len(campuses))
    total = len(classificados)

    fig, ax = plt.subplots(figsize=(10, max(4, len(campuses) * 0.45)))
    lefts = [0] * len(campuses)

    for inciso in incisos:
        values = [campus_inciso[c].get(inciso, 0) for c in campuses]
        ax.barh(list(ys), values, left=lefts, color=_INCISO_COLORS[inciso], label=inciso)
        for y, left, val in zip(ys, lefts, values, strict=True):
            if val > 0:
                ax.text(left + val / 2, y, str(val), ha="center", va="center",
                        fontsize=8, color="white", fontweight="bold")
        lefts = [left + val for left, val in zip(lefts, values, strict=True)]

    ax.set_yticks(list(ys))
    ax.set_yticklabels(campuses, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Número de equipes classificadas")
    ax.set_title(
        f"Equipes classificadas por campus e critério\n{total} equipes no total",
        pad=12,
    )
    ax.legend(loc="lower right", fontsize=9)
    ax.set_xlim(0, max(campus_total.values()) * 1.08)
    ax.xaxis.get_major_locator().set_params(integer=True)

    plt.tight_layout()
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Gráfico salvo em {chart_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gera a lista de equipes classificadas para a fase seguinte do InterIF."
    )
    parser.add_argument("--teams", required=True, metavar="SHEET_ID",
                        help="ID da planilha de equipes")
    parser.add_argument("--output", "-o", metavar="ARQUIVO", default=str(OUTPUT_FILE),
                        help=f"Arquivo CSV de saída (padrão: {OUTPUT_FILE.name})")
    parser.add_argument("--geral", type=int, default=11, metavar="N",
                        help="Vagas pelo inciso II — classificação geral (padrão: 11)")
    parser.add_argument("--medio", type=int, default=3, metavar="N",
                        help="Vagas pelo inciso III — ensino médio integrado (padrão: 3)")
    parser.add_argument("--mulheres", type=int, default=4, metavar="N",
                        help="Vagas pelo inciso IV — exclusivamente mulheres (padrão: 4)")
    return parser.parse_args()


# ── Saída ─────────────────────────────────────────────────────────────────────


def escrever_resultado(classificados: list[tuple[str, Team]], output_path: Path) -> None:
    """Grava o CSV de classificados, gera o gráfico e imprime o resumo."""
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow([
            "Critério", "Nome da Equipe", "Campus",
            "Nome Participante 1", "Nome Participante 2", "Nome Participante 3",
            "Classificação",
        ])
        for criterio, team in classificados:
            writer.writerow([
                criterio,
                team.nome,
                team.campus,
                team.part_nomes[0],
                team.part_nomes[1],
                team.part_nomes[2],
                team.rank,
            ])

    chart_path = output_path.parent / CHART_FILE.name
    generate_chart(classificados, chart_path)

    print(f"\n{len(classificados)} equipes classificadas salvas em {output_path}")

    counts: dict[str, int] = {}
    for criterio, _ in classificados:
        counts[criterio] = counts.get(criterio, 0) + 1
    for criterio, n in counts.items():
        print(f"  {criterio}: {n} equipe(s)")


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    args = parse_args()

    print("Lendo planilha de equipes...")
    headers, rows = read_sheet(args.teams, SHEET_NAME)
    print(f"  {len(rows)} linhas lidas")

    teams = load_teams(headers, rows)
    print(f"  {len(teams)} equipes com classificação válida")

    classificados = selecionar(
        teams,
        n_geral=args.geral,
        n_medio=args.medio,
        n_mulheres=args.mulheres,
    )

    escrever_resultado(classificados, Path(args.output))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"Erro ao chamar gws: {e.stderr}", file=sys.stderr)
        sys.exit(1)
