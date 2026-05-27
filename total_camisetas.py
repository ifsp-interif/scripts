#!/usr/bin/env python3
"""
Lê equipes_interif.csv e exibe o total de camisetas por tamanho em cada campus.

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
_CPF_COLUMNS: tuple[str, ...] = (
    "CPF do Responsável pela Equipe",
    "CPF Participante 1",
    "CPF Participante 2",
    "CPF Participante 3",
)


@dataclass
class ShirtTotals:
    by_campus: dict[str, Counter[str]]
    total: Counter[str]
    no_shirt_by_campus: Counter[str]
    total_no_shirt: int
    shirt_columns: list[int]
    duplicates_skipped: int = field(default=0)


def _digits(value: str) -> str:
    """Extrai apenas os dígitos de um CPF."""
    return re.sub(r"\D", "", value.strip())


def _build_cpf_shirt_pairs(headers: list[str]) -> list[tuple[int, int]]:
    """
    Para cada coluna de CPF conhecida presente no cabeçalho, localiza a coluna
    'Tamanho da camiseta' mais próxima que apareça *depois* dela.

    Retorna lista de (índice_cpf, índice_camiseta).
    Se nenhum par for encontrado, retorna lista vazia (fallback sem deduplicação).
    """
    shirt_indices = [
        i for i, h in enumerate(headers)
        if h.strip().lower() == "tamanho da camiseta"
    ]

    pairs: list[tuple[int, int]] = []
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
            pairs.append((cpf_idx, candidate))
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
    by_campus: dict[str, Counter[str]] = defaultdict(Counter)
    total: Counter[str] = Counter()
    no_shirt_by_campus: Counter[str] = Counter()
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

        # Tenta parear colunas de CPF com colunas de camiseta.
        cpf_shirt_pairs = _build_cpf_shirt_pairs(headers)

        if cpf_shirt_pairs:
            # Modo com deduplicação por CPF
            shirt_columns = [s for _, s in cpf_shirt_pairs]
            seen_cpfs: set[str] = set()

            for row in reader:
                if len(row) <= campus_idx:
                    continue
                campus = row[campus_idx].strip()
                if not campus:
                    continue

                for cpf_idx, shirt_idx in cpf_shirt_pairs:
                    if shirt_idx >= len(row):
                        continue

                    raw_size = row[shirt_idx].strip() if shirt_idx < len(row) else ""
                    if not raw_size:
                        continue

                    # Deduplicação: ignora se CPF já foi contado
                    cpf_digits = _digits(row[cpf_idx]) if cpf_idx < len(row) else ""
                    if cpf_digits and cpf_digits in seen_cpfs:
                        duplicates_skipped += 1
                        continue

                    if is_no_shirt(raw_size):
                        no_shirt_by_campus[campus] += 1
                    else:
                        size = normalize_size(raw_size)
                        by_campus[campus][size] += 1
                        total[size] += 1

                    if cpf_digits:
                        seen_cpfs.add(cpf_digits)

        else:
            # Fallback: nenhuma coluna de CPF reconhecida → sem deduplicação
            shirt_columns = [
                idx
                for idx, header in enumerate(headers)
                if header.strip().lower() == "tamanho da camiseta"
            ]
            if not shirt_columns:
                raise ValueError("Nenhuma coluna 'Tamanho da camiseta' encontrada.")

            for row in reader:
                if len(row) <= campus_idx:
                    continue
                campus = row[campus_idx].strip()
                if not campus:
                    continue

                for idx in shirt_columns:
                    if idx >= len(row):
                        continue
                    raw_size = row[idx].strip()
                    if not raw_size:
                        continue
                    if is_no_shirt(raw_size):
                        no_shirt_by_campus[campus] += 1
                        continue
                    size = normalize_size(raw_size)
                    by_campus[campus][size] += 1
                    total[size] += 1

    return ShirtTotals(
        by_campus=dict(by_campus),
        total=total,
        no_shirt_by_campus=no_shirt_by_campus,
        total_no_shirt=sum(no_shirt_by_campus.values()),
        shirt_columns=shirt_columns,
        duplicates_skipped=duplicates_skipped,
    )


def build_terminal_table(totals: ShirtTotals) -> str:
    sizes = sort_sizes(set(totals.total))
    headers = ["Campus", *sizes, "Total"]
    rows: list[list[str | int]] = []
    for campus in sorted(totals.by_campus):
        campus_counts = totals.by_campus[campus]
        row_total = sum(campus_counts.values())
        rows.append([
            campus,
            *(campus_counts.get(size, 0) for size in sizes),
            row_total,
        ])

    rows.append([
        "Total",
        *(totals.total.get(size, 0) for size in sizes),
        sum(totals.total.values()),
    ])
    return tabulate(rows, headers=headers, tablefmt="simple")


def render_markdown(totals: ShirtTotals) -> str:
    sizes = sort_sizes(set(totals.total))
    headers = ["Campus", *sizes, "Total"]
    lines = [
        "# Camisetas por campus",
        "",
        f"Colunas de camiseta consideradas: {len(totals.shirt_columns)}",
        "",
    ]

    rows: list[list[str | int]] = []
    for campus in sorted(totals.by_campus):
        campus_counts = totals.by_campus[campus]
        row_total = sum(campus_counts.values())
        rows.append([
            campus,
            *(campus_counts.get(size, 0) for size in sizes),
            row_total,
        ])

    rows.append([
        "Total",
        *(totals.total.get(size, 0) for size in sizes),
        sum(totals.total.values()),
    ])
    lines.extend(tabulate(rows, headers=headers, tablefmt="github").splitlines())

    if totals.total_no_shirt:
        lines.extend(
            [
                "",
                f"Solicitações sem camiseta ignoradas no total por tamanho: {totals.total_no_shirt}.",
            ]
        )
    if totals.duplicates_skipped:
        lines.extend(
            [
                "",
                f"Entradas ignoradas por CPF duplicado (mesma pessoa em múltiplas equipes): {totals.duplicates_skipped}.",
            ]
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    totals = load_totals(Path(args.input))

    print("Camisetas por campus")
    print(build_terminal_table(totals))
    if totals.total_no_shirt:
        print(f"\nSolicitações sem camiseta ignoradas no total por tamanho: {totals.total_no_shirt}")
    if totals.duplicates_skipped:
        print(f"Entradas ignoradas por CPF duplicado (mesma pessoa em múltiplas equipes): {totals.duplicates_skipped}")

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(render_markdown(totals), encoding="utf-8")
        print(f"\nMarkdown salvo em {output_path}")


if __name__ == "__main__":
    main()
