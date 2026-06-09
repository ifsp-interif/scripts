#!/usr/bin/env python3
"""
Padroniza os nomes de cursos cadastrados na planilha de equipes.

Primeira passada — gera o mapeamento automático:
    uv run python lista_cursos.py --gerar-mapa

Edite o arquivo gerado (cursos_mapa.csv) e então aplique:

Segunda passada — aplica as correções ao CSV de equipes:
    uv run python lista_cursos.py --aplicar
    uv run python lista_cursos.py --aplicar --dry-run

Terceira opção — enriquece com o curso oficial via matriculados.csv:
    uv run python lista_cursos.py --enriquecer
    uv run python lista_cursos.py --enriquecer --dry-run
"""

import argparse
import csv
import sys
from pathlib import Path

from rapidfuzz import fuzz, process

CSV_FILE = Path(__file__).parent / "equipes_interif.csv"
MAPA_FILE = Path(__file__).parent / "cursos_mapa.csv"
MATRICULADOS_FILE = Path(__file__).parent / "matriculados.csv"

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


# ── Passada 3: enriquecer com curso oficial ───────────────────────────────────


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

    # Mapa de normalização de capitalização: lower → forma canônica do lookup
    norm_map: dict[str, str] = {nome.lower(): nome for nome in set(lookup.values())}

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

    pares = list(zip(idx_pront, idx_curso))

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
                # Prontuário não encontrado: normaliza capitalização se possível
                canonical = norm_map.get(atual.lower())
                if canonical and canonical != atual:
                    if dry_run:
                        print(f"  {pront}: {atual!r:50s} → {canonical!r} [norm]")
                    row[ic] = canonical
                    alteracoes += 1
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
    group.add_argument(
        "--enriquecer",
        action="store_true",
        help=f"Substitui 'Nome do curso' pelo curso oficial de {MATRICULADOS_FILE.name}",
    )
    parser.add_argument("--csv", default=str(CSV_FILE), metavar="ARQUIVO")
    parser.add_argument("--mapa", default=str(MAPA_FILE), metavar="ARQUIVO")
    parser.add_argument("--matriculados", default=str(MATRICULADOS_FILE), metavar="ARQUIVO")
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
    matriculados_path = Path(args.matriculados)

    if not csv_path.exists():
        print(f"Erro: arquivo não encontrado: {csv_path}", file=sys.stderr)
        sys.exit(1)

    if args.gerar_mapa:
        gerar_mapa(csv_path, mapa_path)
    elif args.enriquecer:
        enriquecer_cursos(csv_path, matriculados_path, dry_run=args.dry_run)
    else:
        aplicar_mapa(csv_path, mapa_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
