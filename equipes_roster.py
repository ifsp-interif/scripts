"""
Esquema do roster de equipes do InterIF (equipes_interif.csv).

Centraliza a leitura das planilhas Google e a montagem das linhas no formato
canônico de equipes_interif.csv — colunas-chave renomeadas para os nomes usados
pelos scripts a jusante e duas colunas de coordenador inseridas logo após o
Campus.

Compartilhado por:
  - equipes_interif.py        — gera o equipes_interif.csv completo.
  - classificacao_interif.py  — reproduz a mesma estrutura no recorte de
                                equipes classificadas (equipes_interif_final.csv).
"""

import json
import subprocess

SHEET_NAME = "Respostas ao formulário 1"

# ── Layout das colunas da planilha de equipes (0-based, sem o cabeçalho) ──────
# Ajuste estas constantes se as colunas da planilha forem reordenadas.

CAMPUS_COL = 3  # Campus
TEAM_NAME_COL = 2  # Nome da Equipe

# Colunas-chave renomeadas para os nomes canônicos usados pelos scripts a
# jusante. Todas as demais colunas mantêm o cabeçalho original da planilha.
TEAM_KEY_COLUMNS: dict[int, str] = {
    2: "Nome da Equipe",
    3: "Campus",
    6: "Nome do Responsável pela Equipe",
    7: "CPF do Responsável pela Equipe",
    8: "Email do Responsável pela Equipe",
    11: "Nome Participante 1",
    13: "CPF Participante 1",
    14: "Email Participante 1",
    18: "Nome Participante 2",
    20: "CPF Participante 2",
    21: "Email Participante 2",
    25: "Nome Participante 3",
    27: "CPF Participante 3",
    28: "Email Participante 3",
}

# Colunas de coordenador inseridas logo após o Campus.
COORD_INSERT_POS = CAMPUS_COL + 1  # → índice 4 na saída
COORD_HEADERS = ["Nome do Coordenador do Campus", "Email do Coordenador do Campus"]


# ── Leitura das planilhas ─────────────────────────────────────────────────────


def read_sheet(
    spreadsheet_id: str, sheet_name: str = SHEET_NAME
) -> tuple[list[str], list[list[str]]]:
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
    # Preenche linhas curtas para que o acesso por índice seja seguro.
    rows = [r + [""] * (len(headers) - len(r)) for r in rows]
    return headers, rows


def get(row: list[str], idx: int) -> str:
    return row[idx].strip() if idx < len(row) else ""


# ── Montagem do roster ────────────────────────────────────────────────────────


def build_coord_map(campi_rows: list[list[str]]) -> dict[str, tuple[str, str, str]]:
    """Mapeia campus normalizado → (campus original, nome do coord, email do coord)."""
    coord_map: dict[str, tuple[str, str, str]] = {}
    for row in campi_rows:
        campus = get(row, 3)
        if campus:
            coord_map[campus.lower()] = (campus, get(row, 2), get(row, 4))
    return coord_map


def build_output_headers(team_headers: list[str]) -> list[str]:
    """Cabeçalhos canônicos: renomeia as colunas-chave e insere as de coordenador."""
    renamed = [TEAM_KEY_COLUMNS.get(i, h) for i, h in enumerate(team_headers)]
    return renamed[:COORD_INSERT_POS] + COORD_HEADERS + renamed[COORD_INSERT_POS:]


def build_team_row(
    row: list[str],
    team_headers: list[str],
    coord_map: dict[str, tuple[str, str, str]],
) -> list[str]:
    """Monta uma linha no formato equipes_interif.csv a partir de uma linha bruta."""
    campus = get(row, CAMPUS_COL)
    _, coord_nome, coord_email = coord_map.get(campus.lower(), ("", "", ""))
    values = [get(row, i) for i in range(len(team_headers))]
    return values[:COORD_INSERT_POS] + [coord_nome, coord_email] + values[COORD_INSERT_POS:]
