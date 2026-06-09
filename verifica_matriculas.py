#!/usr/bin/env python3
"""
Verifica se os participantes das equipes InterIF estão matriculados no IFSP.

Uso:
    uv run python verifica_matriculas.py --graduacao alunos_grad.csv --medio alunos_medio.csv
    uv run python verifica_matriculas.py --graduacao alunos_grad.csv --medio alunos_medio.csv \\
        -i equipes_interif.csv -m matriculados.csv -o alunos_irregulares.txt
"""

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

from tabulate import tabulate

_EQUIPES_CSV = Path(__file__).parent / "equipes_interif.csv"
_MATRICULADOS_CSV = Path(__file__).parent / "matriculados.csv"
_OUTPUT_TXT = Path(__file__).parent / "alunos_irregulares.txt"

# Índices fixos no equipes_interif.csv (verificados no cabeçalho)
_CAMPUS_IDX = 3
_PARTICIPANTS = [
    (13, 14),  # (nome_idx, prontuario_idx) — Participante 1
    (20, 21),  # Participante 2
    (27, 28),  # Participante 3
]
_MIN_COLS = 29  # mínimo de colunas esperado

_SITUACAO_COL = "Situação"
_MATRICULA_COL = "Matrícula"

ALUNOS_HEADER = [
    "#",
    "Nome",
    "Matrícula",
    "Curso",
    "Campus",
    "Polo",
    "Situação",
    "E-mail Acadêmico",
    "E-mail Pessoal",
    "Ano/Periodo Letivo",
]


@dataclass(frozen=True)
class Aluno:
    campus: str
    nome: str
    prontuario: str
    situacao: str  # "Regular" ou "Irregular"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verifica situação de matrícula dos participantes InterIF."
    )
    parser.add_argument(
        "--graduacao",
        metavar="ARQUIVO",
        required=True,
        help="CSV de alunos da graduação",
    )
    parser.add_argument(
        "--medio",
        metavar="ARQUIVO",
        required=True,
        help="CSV de alunos do ensino médio",
    )
    parser.add_argument(
        "--matriculados",
        "-m",
        metavar="ARQUIVO",
        default=str(_MATRICULADOS_CSV),
        help=f"Onde salvar o CSV filtrado de matriculados (padrão: {_MATRICULADOS_CSV.name})",
    )
    parser.add_argument(
        "--input",
        "-i",
        metavar="ARQUIVO",
        default=str(_EQUIPES_CSV),
        help=f"CSV de equipes inscritas (padrão: {_EQUIPES_CSV.name})",
    )
    parser.add_argument(
        "--output",
        "-o",
        metavar="ARQUIVO",
        default=str(_OUTPUT_TXT),
        help=f"Relatório de saída (padrão: {_OUTPUT_TXT.name})",
    )
    parser.add_argument(
        "--irregulares",
        action="store_true",
        help="Lista apenas os participantes com situação Irregular",
    )
    return parser.parse_args()


def load_matriculados(grad_path: Path, medio_path: Path, out_path: Path) -> set[str]:
    matriculas: set[str] = set()
    rows_out: list[dict] = []

    for label, path in [("Graduação", grad_path), ("Ensino médio", medio_path)]:
        count = 0
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get(_SITUACAO_COL, "").strip().lower().startswith("matrícula") or row.get(
                    _SITUACAO_COL, ""
                ).strip().lower().startswith("matriculado"):
                    matricula = row.get(_MATRICULA_COL, "").strip()
                    if matricula:
                        matriculas.add(matricula.upper())
                    rows_out.append(row)
                    count += 1
        print(f"  {label}: {count} matriculados")

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ALUNOS_HEADER, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows_out)

    print(f"  Total: {len(matriculas)} matrículas únicas → {out_path}")
    return matriculas


def _validate_equipes_header(header: list[str], path: Path) -> None:
    if len(header) < _MIN_COLS:
        raise ValueError(
            f"{path}: cabeçalho com {len(header)} colunas; esperado ao menos {_MIN_COLS}"
        )
    for nome_idx, pron_idx in _PARTICIPANTS:
        if header[pron_idx] != "Prontuário":
            raise ValueError(
                f"{path}: coluna {pron_idx} esperada 'Prontuário', encontrada '{header[pron_idx]}'"
            )


def load_participantes(equipes_path: Path) -> list[tuple[str, str, str]]:
    participantes: list[tuple[str, str, str]] = []
    with open(equipes_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        _validate_equipes_header(header, equipes_path)

        for row in reader:
            if len(row) <= _CAMPUS_IDX:
                continue
            campus = row[_CAMPUS_IDX].strip()
            for nome_idx, pron_idx in _PARTICIPANTS:
                if pron_idx >= len(row):
                    continue
                nome = row[nome_idx].strip()
                prontuario = row[pron_idx].strip()
                if nome and prontuario:
                    participantes.append((campus, nome, prontuario))

    return participantes


def render_report(
    alunos: list[Aluno], equipes_path: Path, *, apenas_irregulares: bool = False
) -> str:
    regulares = sum(1 for a in alunos if a.situacao == "Regular")
    irregulares = len(alunos) - regulares

    lines = [
        "Situação dos participantes — InterIF",
        f"Arquivo equipes: {equipes_path.resolve()}",
        f"Total de participantes: {len(alunos)}",
        f"  Regulares:   {regulares}",
        f"  Irregulares: {irregulares}",
        "",
    ]

    exibidos = [a for a in alunos if not apenas_irregulares or a.situacao == "Irregular"]

    rows: list[list[str]] = []
    prev_campus = None
    for aluno in exibidos:
        campus_cell = ""
        if aluno.campus != prev_campus:
            campus_cell = aluno.campus
            prev_campus = aluno.campus
        rows.append([campus_cell, aluno.nome, aluno.prontuario, aluno.situacao])

    if rows:
        headers = ["Campus", "Nome", "Prontuário"] + ([] if apenas_irregulares else ["Situação"])
        table_rows = ([r[0], r[1], r[2]] if apenas_irregulares else r for r in rows)
        lines.append(tabulate(table_rows, headers=headers, tablefmt="simple"))
    else:
        lines.append("(nenhum participante encontrado)")

    return "\n".join(lines)


def main() -> None:
    args = parse_args()

    grad_path = Path(args.graduacao)
    medio_path = Path(args.medio)
    equipes_path = Path(args.input)
    matriculados_path = Path(args.matriculados)
    output_path = Path(args.output)

    for path in (grad_path, medio_path, equipes_path):
        if not path.exists():
            print(f"Erro: arquivo não encontrado: {path}", file=sys.stderr)
            sys.exit(1)

    print("Carregando matriculados...")
    try:
        matriculas = load_matriculados(grad_path, medio_path, matriculados_path)
    except (OSError, csv.Error) as exc:
        print(f"Erro ao ler CSVs de alunos: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\nCarregando participantes das equipes...")
    try:
        participantes = load_participantes(equipes_path)
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(participantes)} participantes encontrados")

    alunos = [
        Aluno(
            campus, nome, prontuario, "Regular" if prontuario.upper() in matriculas else "Irregular"
        )
        for campus, nome, prontuario in participantes
    ]
    alunos.sort(key=lambda a: (a.campus.lower(), a.nome.lower()))

    report = render_report(alunos, equipes_path, apenas_irregulares=args.irregulares)
    print()
    print(report)

    output_path.write_text(report, encoding="utf-8")
    print(f"\nRelatório salvo em {output_path}")


if __name__ == "__main__":
    main()
