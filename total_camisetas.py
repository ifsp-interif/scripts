#!/usr/bin/env python3
"""
Lê equipes_interif.csv e exibe o total de camisetas por tamanho em cada campus.

Gera duas tabelas:
  - Competidores: Participantes 1, 2 e 3.
  - Não competidores: Responsável pela Equipe.

Cada pessoa é contada uma única vez: deduplicação global por CPF.
Primeira ocorrência do CPF vale; as demais são ignoradas.

Uso:
    uv run python total_camisetas.py --input equipes_interif.csv
    uv run python total_camisetas.py -i equipes_interif.csv -o camisetas.md
"""

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from tabulate import tabulate

CSV_FILE = Path(__file__).parent / "equipes_interif.csv"
OUTPUT_FILE = Path(__file__).parent / "camisetas.md"

NO_SHIRT_VALUES = {
    "nao quero camiseta",
    "não quero camiseta",
}
SIZE_ORDER = ["PP", "P", "M", "G", "GG", "3G", "4G", "XG", "XGG"]

# Nomes das colunas de CPF reconhecidas no CSV (espelhando cpf_check._CPF_COL_MAP).
# Cada coluna de CPF é pareada com a coluna "Tamanho da camiseta" mais próxima
# que apareça depois dela no cabeçalho.
_COMPETITOR_CPF_COLUMNS: tuple[str, ...] = (
    "CPF Participante 1",
    "CPF Participante 2",
    "CPF Participante 3",
)
_NON_COMPETITOR_CPF_COLUMNS: tuple[str, ...] = ("CPF do Responsável pela Equipe",)
_CPF_COLUMNS: tuple[str, ...] = _NON_COMPETITOR_CPF_COLUMNS + _COMPETITOR_CPF_COLUMNS


@dataclass
class GroupTotals:
    """Totais de camisetas de um grupo de pessoas (competidores ou não)."""

    by_campus: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    total: Counter[str] = field(default_factory=Counter)
    no_shirt_by_campus: Counter[str] = field(default_factory=Counter)

    @property
    def total_no_shirt(self) -> int:
        return sum(self.no_shirt_by_campus.values())

    def add(self, campus: str, raw_size: str) -> None:
        if is_no_shirt(raw_size):
            self.no_shirt_by_campus[campus] += 1
        else:
            size = normalize_size(raw_size)
            self.by_campus[campus][size] += 1
            self.total[size] += 1


@dataclass
class ShirtTotals:
    competitors: GroupTotals
    non_competitors: GroupTotals
    shirt_columns: int
    duplicates_skipped: int = field(default=0)


def _digits(value: str) -> str:
    """Extrai apenas os dígitos de um CPF."""
    return re.sub(r"\D", "", value.strip())


def _build_cpf_shirt_pairs(headers: list[str]) -> dict[str, int]:
    """
    Para cada coluna de CPF conhecida presente no cabeçalho, localiza a coluna
    'Tamanho da camiseta' mais próxima que apareça *depois* dela.

    Retorna dict {nome_coluna_cpf: índice_camiseta}.
    """
    shirt_indices = [i for i, h in enumerate(headers) if h.strip().lower() == "tamanho da camiseta"]

    pairs: dict[str, int] = {}
    used_shirt: set[int] = set()

    for cpf_col in _CPF_COLUMNS:
        if cpf_col not in headers:
            continue
        cpf_idx = headers.index(cpf_col)
        # Camiseta mais próxima após o CPF, ainda não usada
        candidate = min(
            (s for s in shirt_indices if s > cpf_idx and s not in used_shirt),
            default=None,
            key=lambda s: s - cpf_idx,
        )
        if candidate is not None:
            pairs[cpf_col] = candidate
            used_shirt.add(candidate)

    return pairs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Conta camisetas por tamanho e por campus a partir de equipes_interif.csv."
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
        metavar="ARQUIVO",
        help=f"Caminho do Markdown de saída (ex.: {OUTPUT_FILE.name})",
    )
    return parser.parse_args()


def normalize_size(value: str) -> str:
    return value.strip().upper()


def is_no_shirt(value: str) -> bool:
    return value.strip().lower() in NO_SHIRT_VALUES


def sort_sizes(sizes: set[str]) -> list[str]:
    known = [size for size in SIZE_ORDER if size in sizes]
    unknown = sorted(sizes - set(SIZE_ORDER))
    return known + unknown


def load_totals(csv_path: Path) -> ShirtTotals:
    competitors = GroupTotals()
    non_competitors = GroupTotals()
    duplicates_skipped = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = next(reader, [])
        if not headers:
            raise ValueError(f"CSV vazio: {csv_path}")

        try:
            campus_idx = headers.index("Campus")
        except ValueError as exc:
            raise ValueError("Coluna obrigatória ausente: Campus") from exc

        cpf_shirt_pairs = _build_cpf_shirt_pairs(headers)
        if not cpf_shirt_pairs:
            raise ValueError(
                "Nenhuma coluna de CPF reconhecida para parear com 'Tamanho da camiseta'."
            )

        # (índice_cpf, índice_camiseta, grupo) na ordem em que aparecem na linha.
        plan: list[tuple[int, int, GroupTotals]] = []
        for cpf_col, shirt_idx in cpf_shirt_pairs.items():
            group = (
                competitors if cpf_col in _COMPETITOR_CPF_COLUMNS else non_competitors
            )
            plan.append((headers.index(cpf_col), shirt_idx, group))

        seen_cpfs: set[str] = set()

        for row in reader:
            if len(row) <= campus_idx:
                continue
            campus = row[campus_idx].strip()
            if not campus:
                continue

            for cpf_idx, shirt_idx, group in plan:
                if shirt_idx >= len(row):
                    continue

                raw_size = row[shirt_idx].strip()
                if not raw_size:
                    continue

                # Deduplicação: ignora se CPF já foi contado
                cpf_digits = _digits(row[cpf_idx]) if cpf_idx < len(row) else ""
                if cpf_digits and cpf_digits in seen_cpfs:
                    duplicates_skipped += 1
                    continue

                group.add(campus, raw_size)

                if cpf_digits:
                    seen_cpfs.add(cpf_digits)

    return ShirtTotals(
        competitors=competitors,
        non_competitors=non_competitors,
        shirt_columns=len(cpf_shirt_pairs),
        duplicates_skipped=duplicates_skipped,
    )


def _build_rows(group: GroupTotals, sizes: list[str]) -> list[list[str | int]]:
    rows: list[list[str | int]] = []
    for campus in sorted(group.by_campus):
        campus_counts = group.by_campus[campus]
        rows.append(
            [
                campus,
                *(campus_counts.get(size, 0) for size in sizes),
                sum(campus_counts.values()),
            ]
        )
    rows.append(
        [
            "Total",
            *(group.total.get(size, 0) for size in sizes),
            sum(group.total.values()),
        ]
    )
    return rows


def _group_table(group: GroupTotals, tablefmt: str) -> str:
    sizes = sort_sizes(set(group.total))
    headers = ["Campus", *sizes, "Total"]
    return tabulate(_build_rows(group, sizes), headers=headers, tablefmt=tablefmt)


def _summary_table(totals: ShirtTotals, tablefmt: str) -> str:
    """Resumo geral: contagem por tamanho para cada tipo (competidor/não)."""
    sizes = sort_sizes(set(totals.competitors.total) | set(totals.non_competitors.total))
    headers = ["Tipo", *sizes, "Total"]
    rows: list[list[str | int]] = [
        [
            "Competidores",
            *(totals.competitors.total.get(size, 0) for size in sizes),
            sum(totals.competitors.total.values()),
        ],
        [
            "Não competidores",
            *(totals.non_competitors.total.get(size, 0) for size in sizes),
            sum(totals.non_competitors.total.values()),
        ],
        [
            "Total",
            *(
                totals.competitors.total.get(size, 0)
                + totals.non_competitors.total.get(size, 0)
                for size in sizes
            ),
            sum(totals.competitors.total.values())
            + sum(totals.non_competitors.total.values()),
        ],
    ]
    return tabulate(rows, headers=headers, tablefmt=tablefmt)


def build_terminal_tables(totals: ShirtTotals) -> str:
    parts = [
        "Camisetas de competidores por campus",
        _group_table(totals.competitors, "simple"),
        "",
        "Camisetas de não competidores (responsável) por campus",
        _group_table(totals.non_competitors, "simple"),
        "",
        "Resumo geral por tamanho e tipo",
        _summary_table(totals, "simple"),
    ]
    return "\n".join(parts)


def render_markdown(totals: ShirtTotals) -> str:
    lines = [
        "# Camisetas por campus",
        "",
        "## Competidores (Participantes 1, 2 e 3)",
        "",
        *_group_table(totals.competitors, "github").splitlines(),
    ]
    if totals.competitors.total_no_shirt:
        lines += [
            "",
            "Solicitações sem camiseta ignoradas no total por tamanho: "
            f"{totals.competitors.total_no_shirt}.",
        ]

    lines += [
        "",
        "## Não competidores (Responsável pela Equipe)",
        "",
        *_group_table(totals.non_competitors, "github").splitlines(),
    ]
    if totals.non_competitors.total_no_shirt:
        lines += [
            "",
            "Solicitações sem camiseta ignoradas no total por tamanho: "
            f"{totals.non_competitors.total_no_shirt}.",
        ]

    lines += [
        "",
        "## Resumo geral por tamanho e tipo",
        "",
        *_summary_table(totals, "github").splitlines(),
    ]

    if totals.duplicates_skipped:
        lines += [
            "",
            "Entradas ignoradas por CPF duplicado (mesma pessoa em múltiplas equipes): "
            f"{totals.duplicates_skipped}.",
        ]

    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    totals = load_totals(Path(args.input))

    print(build_terminal_tables(totals))
    if totals.competitors.total_no_shirt:
        print(
            "\nCompetidores sem camiseta ignorados no total por tamanho: "
            f"{totals.competitors.total_no_shirt}"
        )
    if totals.non_competitors.total_no_shirt:
        print(
            "Não competidores sem camiseta ignorados no total por tamanho: "
            f"{totals.non_competitors.total_no_shirt}"
        )
    if totals.duplicates_skipped:
        print(
            "Entradas ignoradas por CPF duplicado (mesma pessoa em múltiplas equipes): "
            f"{totals.duplicates_skipped}"
        )

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(render_markdown(totals), encoding="utf-8")
        print(f"\nMarkdown salvo em {output_path}")


if __name__ == "__main__":
    main()
