#!/usr/bin/env python3
"""
Versão da classificação que usa o placar final (PDF do BOCA) como fonte da
ordenação das equipes, em vez da planilha do Google.

A coluna "Name" do placar tem o formato "[IFSP - <sigla>] <nome da equipe>" e as
linhas já vêm ordenadas pela classificação (coluna "#"). Os nomes dos
participantes, a contagem de mulheres e a marcação de ensino médio integrado são
buscados em equipes_interif.csv casando por campus (derivado da sigla) e nome da
equipe.

Aplica os mesmos critérios (incisos I–IV) de classificacao_interif.py.
"""

import argparse
import csv
import re
import sys
import unicodedata
from pathlib import Path

import pdfplumber

from classificacao_interif import (
    FINAL_OUTPUT_FILE,
    OUTPUT_FILE,
    Team,
    _active_participants,
    _parse_women_count,
    _parse_yes,
    escrever_resultado,
    selecionar,
)
from interif_core import CAMPI_FILE, load_campi

# Cabeçalhos canônicos em equipes_interif.csv
TEAM_NAME_HEADER = "Nome da Equipe"
CAMPUS_HEADER = "Campus"
WOMEN_HEADER = "Quantas mulheres na equipe?"
HIGH_SCHOOL_HEADER = "Composta apenas por alunos do ensino médio?"
PARTICIPANT_HEADERS = ["Nome Participante 1", "Nome Participante 2", "Nome Participante 3"]

# "[IFSP - SLT] nunca foi sort()"
_NAME_RE = re.compile(r"^\[IFSP\s*-\s*([A-Za-z]+)\]\s*(.+)$", re.DOTALL)

# Colunas do placar BOCA exportado em PDF
_SCOREBOARD_COLS = 14
_RANK_COL = 0
_NAME_COL = 2


# ── Normalização ──────────────────────────────────────────────────────────────


def _key(value: str) -> str:
    """
    Chave de casamento robusta: mantém apenas caracteres alfanuméricos (após NFC
    e casefold), descartando espaços, pontuação, barras e emojis. Absorve
    artefatos da exportação do BOCA — '\\\\' vs '\\', 'code- arq' vs 'code-arq',
    seletores de variação de emoji (U+FE0F) etc.
    """
    nfc = unicodedata.normalize("NFC", value).casefold()
    return "".join(c for c in nfc if c.isalnum())


# ── Leitura do PDF ────────────────────────────────────────────────────────────


def parse_scoreboard(pdf_path: Path) -> list[tuple[int, str, str]]:
    """
    Lê o placar BOCA e devolve [(rank, sigla, nome_equipe), ...] ordenado por rank.
    Cada página tem uma tabela de 14 colunas; só a primeira repete o cabeçalho.
    """
    entries: list[tuple[int, str, str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if not table or len(table[0]) != _SCOREBOARD_COLS:
                    continue
                for row in table:
                    rank_raw = (row[_RANK_COL] or "").strip()
                    if not rank_raw.isdigit():
                        continue
                    name_cell = (row[_NAME_COL] or "").replace("\n", " ").strip()
                    m = _NAME_RE.match(name_cell)
                    if not m:
                        print(
                            f"Aviso: linha do placar não reconhecida: {name_cell!r}",
                            file=sys.stderr,
                        )
                        continue
                    sigla = m.group(1).upper()
                    nome = " ".join(m.group(2).split())
                    entries.append((int(rank_raw), sigla, nome))

    entries.sort(key=lambda e: e[0])
    return entries


# ── Leitura do CSV de equipes ─────────────────────────────────────────────────


def load_equipes(
    csv_path: Path,
) -> tuple[dict[tuple[str, str], dict], dict[str, list[dict]], list[str]]:
    """
    Lê equipes_interif.csv e devolve dois índices para casamento, mais o
    cabeçalho original:
      - by_campus_name: {(campus_key, nome_key): dados}
      - by_name: {nome_key: [dados, ...]} (para fallback quando o campus diverge)
      - headers: cabeçalho do CSV, para reescrever o recorte de classificados.
    Cada `dados` traz campus original, nomes dos participantes, contagem de
    mulheres, marcação de ensino médio e a linha completa (source_row).

    Lê por posição (csv.reader) em vez de csv.DictReader porque o CSV tem
    cabeçalhos repetidos (ex.: 'Prontuário', 'Tamanho da camiseta') que o
    DictReader colapsaria — perdendo colunas ao reescrever a linha completa.
    """
    by_campus_name: dict[tuple[str, str], dict] = {}
    by_name: dict[str, list[dict]] = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = next(reader)
        ncols = len(headers)

        def col(name: str) -> int:
            return headers.index(name)

        i_nome = col(TEAM_NAME_HEADER)
        i_campus = col(CAMPUS_HEADER)
        i_women = col(WOMEN_HEADER)
        i_medio = col(HIGH_SCHOOL_HEADER)
        i_parts = [col(h) for h in PARTICIPANT_HEADERS]

        for raw in reader:
            row = raw + [""] * (ncols - len(raw))
            nome = row[i_nome].strip()
            campus = row[i_campus].strip()
            if not nome or not campus:
                continue
            part_nomes = [row[i].strip() for i in i_parts]
            dados = {
                "campus": campus,
                "nome": nome,
                "part_nomes": part_nomes,
                "mulheres": _parse_women_count(row[i_women]),
                "apenas_medio": _parse_yes(row[i_medio]),
                "participantes": _active_participants(part_nomes),
                "source_row": row,
            }
            nome_key = _key(nome)
            by_campus_name[(_key(campus), nome_key)] = dados
            by_name.setdefault(nome_key, []).append(dados)
    return by_campus_name, by_name, headers


# ── Junção placar + CSV ───────────────────────────────────────────────────────


def montar_equipes(
    scoreboard: list[tuple[int, str, str]],
    by_campus_name: dict[tuple[str, str], dict],
    by_name: dict[str, list[dict]],
    sigla_para_campus: dict[str, str],
) -> list[Team]:
    teams: list[Team] = []
    nao_encontradas: list[str] = []
    por_nome: list[str] = []  # casadas só pelo nome (campus do placar divergiu)

    for rank, sigla, nome in scoreboard:
        nome_key = _key(nome)
        campus = sigla_para_campus.get(sigla)

        dados = None
        if campus is not None:
            dados = by_campus_name.get((_key(campus), nome_key))

        if dados is None:
            # Fallback: casa só pelo nome, se houver candidato único.
            candidatos = by_name.get(nome_key, [])
            if len(candidatos) == 1:
                dados = candidatos[0]
                por_nome.append(f"[{sigla}] {nome} (rank {rank}) → {dados['campus']}")
            elif len(candidatos) > 1:
                nao_encontradas.append(f"[{sigla}] {nome} (rank {rank}) — nome ambíguo")
                continue
            else:
                nao_encontradas.append(f"[{sigla}] {nome} (rank {rank})")
                continue

        teams.append(
            Team(
                nome=dados["nome"],
                campus=dados["campus"],
                rank=rank,
                mulheres=dados["mulheres"],
                apenas_medio=dados["apenas_medio"],
                participantes=dados["participantes"],
                part_nomes=dados["part_nomes"],
                source_row=dados["source_row"],
            )
        )

    if por_nome:
        print(
            f"Info: {len(por_nome)} equipe(s) casada(s) só pelo nome "
            f"(campus do placar diferente do cadastro):",
            file=sys.stderr,
        )
        for s in por_nome:
            print(f"  - {s}", file=sys.stderr)
    if nao_encontradas:
        print(
            f"Aviso: {len(nao_encontradas)} equipe(s) do placar sem correspondência "
            f"em equipes_interif.csv:",
            file=sys.stderr,
        )
        for s in nao_encontradas:
            print(f"  - {s}", file=sys.stderr)

    return teams


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classifica equipes do InterIF a partir do placar final (PDF do BOCA)."
    )
    parser.add_argument("--input", "-i", required=True, metavar="PDF",
                        help="Placar final exportado do BOCA (PDF)")
    parser.add_argument("--equipes", "-e", required=True, metavar="CSV",
                        help="equipes_interif.csv (fonte dos participantes)")
    parser.add_argument("--output", "-o", metavar="ARQUIVO", default=str(OUTPUT_FILE),
                        help=f"Arquivo CSV de saída (padrão: {OUTPUT_FILE.name})")
    parser.add_argument("--final", "-f", metavar="ARQUIVO", default=str(FINAL_OUTPUT_FILE),
                        help="CSV com as equipes classificadas no formato de "
                             f"equipes_interif.csv (padrão: {FINAL_OUTPUT_FILE.name})")
    parser.add_argument("--geral", type=int, default=11, metavar="N",
                        help="Vagas pelo inciso II — classificação geral (padrão: 11)")
    parser.add_argument("--medio", type=int, default=3, metavar="N",
                        help="Vagas pelo inciso III — ensino médio integrado (padrão: 3)")
    parser.add_argument("--mulheres", type=int, default=4, metavar="N",
                        help="Vagas pelo inciso IV — exclusivamente mulheres (padrão: 4)")
    return parser.parse_args()


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    args = parse_args()

    pdf_path = Path(args.input)
    csv_path = Path(args.equipes)
    for p in (pdf_path, csv_path):
        if not p.exists():
            print(f"Erro: arquivo não encontrado: {p}", file=sys.stderr)
            sys.exit(1)

    print(f"Lendo placar {pdf_path.name}...")
    scoreboard = parse_scoreboard(pdf_path)
    print(f"  {len(scoreboard)} equipes no placar")

    print(f"Lendo {csv_path.name}...")
    by_campus_name, by_name, source_headers = load_equipes(csv_path)
    print(f"  {len(by_campus_name)} equipes no CSV")

    sigla_para_campus = {sigla: campus for campus, sigla in load_campi(CAMPI_FILE).items()}

    teams = montar_equipes(scoreboard, by_campus_name, by_name, sigla_para_campus)
    print(f"  {len(teams)} equipes casadas")

    classificados = selecionar(
        teams,
        n_geral=args.geral,
        n_medio=args.medio,
        n_mulheres=args.mulheres,
    )

    escrever_resultado(
        classificados,
        Path(args.output),
        source_headers=source_headers,
        final_path=Path(args.final),
    )


if __name__ == "__main__":
    main()
