#!/usr/bin/env python3
"""
Padroniza os nomes de cursos cadastrados na planilha de equipes.

Primeira passada — gera o mapeamento automático:
    uv run python lista_cursos.py --gerar-mapa

Edite o arquivo gerado (cursos_mapa.csv) e então aplique:

Segunda passada — aplica as correções ao CSV de equipes:
    uv run python lista_cursos.py --aplicar
    uv run python lista_cursos.py --aplicar --dry-run
"""

import argparse
import csv
import sys
from pathlib import Path

from rapidfuzz import fuzz, process

CSV_FILE = Path(__file__).parent / "equipes_interif.csv"
MAPA_FILE = Path(__file__).parent / "cursos_mapa.csv"

CURSO_COL = "Nome do curso"
SIMILARIDADE_MINIMA = 80  # threshold para agrupar nomes (0-100)


# ── Passada 1: gerar mapeamento ───────────────────────────────────────────────


def _canonical(grupo: list[str]) -> str:
    """Escolhe o nome canônico de um grupo: o mais frequente; em empate, o mais longo."""
    return max(grupo, key=lambda s: (grupo.count(s), len(s)))


def gerar_mapa(csv_path: Path, mapa_path: Path) -> None:
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r.get("Nome da Equipe", "").strip()]

    todos = [r.get(CURSO_COL, "").strip() for r in rows]
    unicos = sorted({c for c in todos if c})

    # Agrupamento guloso por similaridade
    grupos: list[list[str]] = []
    alocados: set[str] = set()

    for nome in unicos:
        if nome in alocados:
            continue
        grupo = [nome]
        alocados.add(nome)
        candidatos = [u for u in unicos if u not in alocados]
        matches = process.extract(nome, candidatos, scorer=fuzz.token_sort_ratio, limit=None)
        for match_nome, score, _ in matches:
            if score >= SIMILARIDADE_MINIMA:
                grupo.append(match_nome)
                alocados.add(match_nome)
        grupos.append(grupo)

    # Monta o mapa: original → canônico sugerido
    mapa: list[tuple[str, str]] = []
    for grupo in grupos:
        canonico = _canonical(grupo)
        for nome in sorted(grupo):
            mapa.append((nome, canonico))

    mapa.sort(key=lambda t: (t[1].lower(), t[0].lower()))

    with open(mapa_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["original", "canonico"])
        writer.writerows(mapa)

    n_grupos = len(grupos)
    n_nomes = len(mapa)
    n_substituicoes = sum(1 for orig, can in mapa if orig != can)
    print(f"{n_nomes} nome(s) único(s) agrupado(s) em {n_grupos} curso(s).")
    print(f"{n_substituicoes} substituição(ões) sugerida(s).")
    print(f"\nArquivo gerado: {mapa_path}")
    print("Revise e edite o arquivo antes de rodar --aplicar.")


# ── Passada 2: aplicar mapeamento ─────────────────────────────────────────────


def aplicar_mapa(csv_path: Path, mapa_path: Path, dry_run: bool) -> None:
    if not mapa_path.exists():
        print(f"Erro: arquivo de mapa não encontrado: {mapa_path}", file=sys.stderr)
        print("Execute --gerar-mapa primeiro.")
        sys.exit(1)

    with open(mapa_path, newline="", encoding="utf-8-sig") as f:
        mapa = {r["original"].strip(): r["canonico"].strip() for r in csv.DictReader(f)}

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    if CURSO_COL not in fieldnames:
        print(f"Erro: coluna '{CURSO_COL}' não encontrada em {csv_path}", file=sys.stderr)
        sys.exit(1)

    alteracoes = 0
    for row in rows:
        original = row[CURSO_COL].strip()
        canonico = mapa.get(original, original)
        if canonico != original:
            if dry_run:
                print(f"  {original!r:60s} → {canonico!r}")
            row[CURSO_COL] = canonico
            alteracoes += 1

    print(f"{alteracoes} linha(s) seriam alterada(s)." if dry_run else f"{alteracoes} linha(s) alterada(s).")

    if dry_run:
        print("\nDry-run: nenhuma alteração gravada.")
        return

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Arquivo atualizado: {csv_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--gerar-mapa",
        action="store_true",
        help=f"Gera {MAPA_FILE.name} com o mapeamento automático de nomes similares",
    )
    group.add_argument(
        "--aplicar",
        action="store_true",
        help=f"Aplica o mapeamento de {MAPA_FILE.name} ao CSV de equipes",
    )
    parser.add_argument("--csv", default=str(CSV_FILE), metavar="ARQUIVO")
    parser.add_argument("--mapa", default=str(MAPA_FILE), metavar="ARQUIVO")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="(com --aplicar) mostra as substituições sem gravar",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    csv_path = Path(args.csv)
    mapa_path = Path(args.mapa)

    if not csv_path.exists():
        print(f"Erro: arquivo não encontrado: {csv_path}", file=sys.stderr)
        sys.exit(1)

    if args.gerar_mapa:
        gerar_mapa(csv_path, mapa_path)
    else:
        aplicar_mapa(csv_path, mapa_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
