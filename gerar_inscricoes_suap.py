#!/usr/bin/env python3
"""
Gera arquivo XLSX para importação de inscrições no SUAP.

Lê equipes_interif.csv e produz uma planilha sem cabeçalho com as colunas:
CPF, Nome, Título, Nacionalidade, E-mail, Perfil e Participação.

Responsáveis pelas equipes entram como Servidor / Mediador.
Participantes das equipes entram como Aluno / Participante.
Coordenadores locais ficam de fora.
Responsáveis duplicados (mesmo CPF em mais de uma equipe) são deduplicados.

Uso:
    uv run python gerar_inscricoes_suap.py [-i equipes_interif.csv] [-o inscricoes_suap.xlsx]
                                           [-c SIGLA]
"""

import argparse
import sys
from pathlib import Path

import openpyxl

from interif_core import CAMPI_FILE, CSV_FILE, load_campi, load_teams

_HERE = Path(__file__).parent
DEFAULT_OUTPUT = _HERE / "inscricoes_suap.xlsx"


def _participantes_validos(team: dict) -> list[dict]:
    parts: list[dict] = []
    for i in range(1, 4):
        nome = team.get(f"part_{i}_nome", "").strip()
        if not nome or nome == "--":
            continue
        parts.append(
            {
                "cpf": team.get(f"part_{i}_cpf", "").strip(),
                "nome": nome,
                "email": team.get(f"part_{i}_email", "").strip(),
            }
        )
    return parts


def build_rows(
    teams: list[dict],
    *,
    incluir_responsaveis: bool = True,
    incluir_participantes: bool = True,
) -> list[tuple]:
    rows: list[tuple] = []
    vistos_resp: set[str] = set()

    for team in teams:
        resp_cpf = team.get("resp_cpf", "").strip()
        resp_email = team.get("resp_email", "").strip()
        coord_email = team.get("coord_email", "").strip()
        if incluir_responsaveis and resp_cpf and resp_cpf not in vistos_resp and resp_email != coord_email:
            vistos_resp.add(resp_cpf)
            rows.append(
                (
                    resp_cpf,
                    team.get("resp_nome", "").strip().upper(),
                    "",
                    "Brasileira",
                    resp_email,
                    "Servidor",
                    "Mediador",
                )
            )

        for p in (_participantes_validos(team) if incluir_participantes else []):
            rows.append(
                (
                    p["cpf"],
                    p["nome"].upper(),
                    "",
                    "Brasileira",
                    p["email"],
                    "Aluno",
                    "Participante",
                )
            )

    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gera XLSX de inscrições para importação no SUAP."
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=CSV_FILE,
        metavar="CSV",
        help=f"CSV de equipes (padrão: {CSV_FILE})",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        metavar="XLSX",
        help=f"arquivo de saída (padrão: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "-c",
        "--campus",
        metavar="SIGLA",
        help="filtra inscrições pelo campus (ex.: ARQ, SPO); sem filtro gera todos",
    )
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument(
        "--so-participantes",
        action="store_true",
        help="gera apenas participantes das equipes (exclui responsáveis)",
    )
    grupo.add_argument(
        "--so-responsaveis",
        action="store_true",
        help="gera apenas responsáveis pelas equipes (exclui participantes)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.input.exists():
        print(f"Erro: arquivo não encontrado: {args.input}", file=sys.stderr)
        sys.exit(1)

    teams = load_teams(args.input)

    if args.campus:
        campi = load_campi(CAMPI_FILE)
        sigla_alvo = args.campus.strip().upper()
        siglas_validas = {s.upper() for s in campi.values()}
        if sigla_alvo not in siglas_validas:
            print(f"Erro: sigla de campus desconhecida: {args.campus!r}", file=sys.stderr)
            sys.exit(1)
        teams = [t for t in teams if campi.get(t["campus"], "").upper() == sigla_alvo]
        if not teams:
            print(f"Aviso: nenhuma equipe encontrada para o campus {args.campus!r}.", file=sys.stderr)

    rows = build_rows(
        teams,
        incluir_responsaveis=not args.so_participantes,
        incluir_participantes=not args.so_responsaveis,
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    for row_idx, row in enumerate(rows, start=1):
        for col_idx, value in enumerate(row, start=1):
            ws.cell(row=row_idx, column=col_idx, value=value)

    wb.save(args.output)
    print(f"{len(rows)} inscrições gravadas em {args.output}")


if __name__ == "__main__":
    main()
