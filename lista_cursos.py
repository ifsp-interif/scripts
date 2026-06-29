#!/usr/bin/env python3
"""
Padroniza os nomes de cursos cadastrados na planilha de equipes.

Enriquece com o curso oficial via matriculados.csv:
    uv run python lista_cursos.py
    uv run python lista_cursos.py --dry-run
"""

import argparse
import csv
import sys
from pathlib import Path

CSV_FILE = Path(__file__).parent / "equipes_interif.csv"
MATRICULADOS_FILE = Path(__file__).parent / "matriculados.csv"


# ── Enriquecer com curso oficial ──────────────────────────────────────────────


def _extrair_nome_curso(curso_raw: str) -> str:
    """'BRI.TCN.SIN.2012 - TECNOLOGIA EM SISTEMAS PARA INTERNET (Campus Birigui)'
    → 'TECNOLOGIA EM SISTEMAS PARA INTERNET'"""
    partes = curso_raw.split(" - ", 1)
    if len(partes) < 2:
        return curso_raw.strip()
    nome = partes[1]
    # remove sufixo " (Campus ...)" se presente
    idx_campus = nome.find(" (Campus")
    if idx_campus != -1:
        nome = nome[:idx_campus]
    return nome.strip().capitalize()


def enriquecer_cursos(csv_path: Path, matriculados_path: Path, dry_run: bool) -> None:
    if not matriculados_path.exists():
        print(f"Erro: arquivo não encontrado: {matriculados_path}", file=sys.stderr)
        sys.exit(1)

    # Monta lookup matrícula.upper() → nome oficial do curso
    lookup: dict[str, str] = {}
    with open(matriculados_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            matricula = row.get("Matrícula", "").strip().upper()
            curso_raw = row.get("Curso", "").strip()
            if matricula and curso_raw:
                lookup[matricula] = _extrair_nome_curso(curso_raw)

    # Lê equipes_interif.csv de forma posicional (colunas com nomes duplicados)
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = [list(r) for r in reader]

    # Descobre índices de cada ocorrência de "Prontuário" e "Nome do curso"
    idx_pront = [i for i, h in enumerate(header) if h.strip() == "Prontuário"]
    idx_curso = [i for i, h in enumerate(header) if h.strip() == "Nome do curso"]

    if not idx_pront or not idx_curso:
        print("Erro: colunas 'Prontuário' ou 'Nome do curso' não encontradas.", file=sys.stderr)
        sys.exit(1)

    pares = list(zip(idx_pront, idx_curso, strict=False))

    alteracoes = 0
    nao_encontrados: list[str] = []

    for row in rows:
        for ip, ic in pares:
            pront = row[ip].strip().upper() if ip < len(row) else ""
            if not pront:
                continue
            oficial = lookup.get(pront)
            atual = row[ic].strip() if ic < len(row) else ""
            if oficial is None:
                nao_encontrados.append(pront)
                continue
            if oficial != atual:
                if dry_run:
                    print(f"  {pront}: {atual!r:50s} → {oficial!r}")
                row[ic] = oficial
                alteracoes += 1

    msg = "seriam alterada(s)" if dry_run else "alterada(s)"
    print(f"{alteracoes} ocorrência(s) {msg}.")

    nao_encontrados_unicos = sorted(set(nao_encontrados))
    if nao_encontrados_unicos:
        print(f"{len(nao_encontrados_unicos)} prontuário(s) não encontrado(s) em {matriculados_path.name}:")
        for p in nao_encontrados_unicos:
            print(f"  {p}")

    if dry_run:
        print("\nDry-run: nenhuma alteração gravada.")
        return

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

    print(f"Arquivo atualizado: {csv_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--enriquecer",
        action="store_true",
        help="Mantido por compatibilidade; o enriquecimento agora é o fluxo padrão",
    )
    parser.add_argument("--csv", default=str(CSV_FILE), metavar="ARQUIVO")
    parser.add_argument("--matriculados", default=str(MATRICULADOS_FILE), metavar="ARQUIVO")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra as substituições sem gravar",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    csv_path = Path(args.csv)
    matriculados_path = Path(args.matriculados)

    if not csv_path.exists():
        print(f"Erro: arquivo não encontrado: {csv_path}", file=sys.stderr)
        sys.exit(1)

    enriquecer_cursos(csv_path, matriculados_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
