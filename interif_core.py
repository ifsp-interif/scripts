"""
Núcleo compartilhado dos scripts InterIF.

Fornece tipos, constantes, carregamento de dados e geração de credenciais BOCA.
Sem dependências pesadas (só stdlib) — pode ser importado por qualquer script.
"""

import csv
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from config import TITULO_EVENTO  # noqa: F401  (re-exportado para conveniência)

# ── Caminhos padrão ───────────────────────────────────────────────────────────

_HERE = Path(__file__).parent
CSV_FILE = _HERE / "equipes_interif.csv"
CAMPI_FILE = _HERE / "assets" / "ifsp_campi.csv"

# ── Geração de senhas ─────────────────────────────────────────────────────────

# Alfabeto sem caracteres ambíguos (0/O, 1/I/l)
PASSWORD_ALPHABET = "ABCDEFGHJKMNPRSTUVWXYZabcdefghkmnpqrstuvwxyz23456789"
PASSWORD_LENGTH = 6

# ── Numeração BOCA ────────────────────────────────────────────────────────────

USERSITENUMBER = 1
TEAM_BLOCK_SIZE = 50
MAX_CAMPUS = 60
TEAM_USERNUMBER_START = 1001  # times: 1001–4000 (60 × 50)
STAFF_USERNUMBER_START = 5001  # staff: 5001–5060 (um por campus)
JUDGE_USERNUMBER = 6001
SCORE_USERNUMBER = 6002


# ── Tipos ─────────────────────────────────────────────────────────────────────


@dataclass
class CredencialEquipe:
    """Credenciais e metadados de uma equipe — usados tanto para gerar arquivos
    BOCA quanto para enviar emails de acesso."""

    campus: str
    sigla: str
    label: str  # sigla ou nome completo conforme --sigla
    nome_equipe: str
    username: str
    password: str
    coord_nome: str
    coord_email: str
    resp_nome: str
    resp_email: str
    participantes: list[dict] = field(default_factory=list)  # [{nome, email}, ...]
    emails_cred: list[str] = field(default_factory=list)  # destinatários extras

    @property
    def primeiro_nome_resp(self) -> str:
        return self.resp_nome.strip().split()[0] if self.resp_nome.strip() else "Professor(a)"

    @property
    def primeiro_nome_coord(self) -> str:
        return self.coord_nome.strip().split()[0] if self.coord_nome.strip() else "Coordenador(a)"


# ── Helpers internos ──────────────────────────────────────────────────────────


def _usernumber_blocos() -> list[int]:
    """Gera a lista de inícios de bloco: [1001, 1051, 1101, …]."""
    return [TEAM_USERNUMBER_START + i * TEAM_BLOCK_SIZE for i in range(MAX_CAMPUS)]


def _emails_cred_para(team: dict) -> list[str]:
    """
    Analisa a coluna 'Quem mais deve receber as credenciais de acesso?' e
    devolve a lista de e-mails dos participantes indicados (sem duplicatas).
    Valores esperados: tokens separados por vírgula contendo '1', '2' ou '3'.
    """
    raw = team.get("cred_para", "").strip()
    if not raw:
        return []
    vistos: set[str] = set()
    emails: list[str] = []
    for token in raw.split(","):
        token = token.strip()
        if "1" in token:
            e = team.get("part_1_email", "").strip()
        elif "2" in token:
            e = team.get("part_2_email", "").strip()
        elif "3" in token:
            e = team.get("part_3_email", "").strip()
        else:
            continue
        if e and e not in vistos:
            vistos.add(e)
            emails.append(e)
    return emails


def _participantes_de(team: dict) -> list[dict]:
    """
    Participantes válidos da equipe, na ordem do CSV.
    Cada item: {nome, email, prontuario, cpf}.  Ignora slots vazios ou '--'.
    """
    parts: list[dict] = []
    for i in range(1, 4):
        nome = team.get(f"part_{i}_nome", "").strip()
        if not nome or nome == "--":
            continue
        parts.append(
            {
                "nome": team[f"part_{i}_nome"],
                "email": team[f"part_{i}_email"],
                "prontuario": team.get(f"part_{i}_prontuario", "").strip(),
                "cpf": team.get(f"part_{i}_cpf", "").strip(),
            }
        )
    return parts


# ── Leitura de dados ──────────────────────────────────────────────────────────


def load_campi(path: Path) -> dict[str, str]:
    """
    Lê ifsp_campi.csv e devolve {nome_cidade: sigla}.
    Normaliza removendo o prefixo 'Campus ' da coluna 'campus'.
    """
    mapping: dict[str, str] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            nome = row["campus"].strip().removeprefix("Campus ").strip()
            mapping[nome] = row["sigla"].strip()
    return mapping


def load_teams(path: Path) -> list[dict]:
    """
    Lê equipes_interif.csv e devolve lista de dicts com todos os campos
    relevantes para geração de arquivos e envio de emails.
    Filtra linhas sem nome de equipe ou campus.

    Lê por posição (csv.reader) em vez de csv.DictReader porque a coluna
    'Prontuário' aparece três vezes no CSV (uma por participante, sempre logo
    após o respectivo 'Nome Participante N') — DictReader colapsaria todas numa
    só, mantendo apenas a última.
    """
    teams: list[dict] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)

        def col(nome: str) -> int:
            """Índice da primeira ocorrência da coluna `nome`."""
            return header.index(nome)

        idx = {
            "nome_equipe": col("Nome da Equipe"),
            "campus": col("Campus"),
            "coord_nome": col("Nome do Coordenador do Campus"),
            "coord_email": col("Email do Coordenador do Campus"),
            "resp_nome": col("Nome do Responsável pela Equipe"),
            "resp_cpf": col("CPF do Responsável pela Equipe"),
            "resp_email": col("Email do Responsável pela Equipe"),
            "resp_tamanho_camiseta": col("Email do Responsável pela Equipe") + 1,
            "cred_para": col("Quem mais deve receber as credenciais de acesso?"),
        }
        # Participantes: nome, prontuário, CPF, email e tamanho da camiseta
        # (colunas em posições fixas relativas ao nome, já que "Tamanho da
        # camiseta" se repete uma vez por participante no CSV).
        idx_part = {
            i: {
                "nome": col(f"Nome Participante {i}"),
                "prontuario": col(f"Nome Participante {i}") + 1,
                "cpf": col(f"CPF Participante {i}"),
                "email": col(f"Email Participante {i}"),
                "tamanho_camiseta": col(f"Nome Participante {i}") + 6,
            }
            for i in (1, 2, 3)
        }

        def get(row: list[str], i: int) -> str:
            return row[i].strip() if i < len(row) else ""

        for row in reader:
            nome = get(row, idx["nome_equipe"])
            campus = get(row, idx["campus"])
            if not nome or not campus:
                continue
            team = {
                "nome_equipe": nome,
                "campus": campus,
                "coord_nome": get(row, idx["coord_nome"]),
                "coord_email": get(row, idx["coord_email"]).lower(),
                "resp_nome": get(row, idx["resp_nome"]),
                "resp_cpf": get(row, idx["resp_cpf"]),
                "resp_email": get(row, idx["resp_email"]).lower(),
                "resp_tamanho_camiseta": get(row, idx["resp_tamanho_camiseta"]),
                "cred_para": get(row, idx["cred_para"]),
            }
            for i, cols in idx_part.items():
                team[f"part_{i}_nome"] = get(row, cols["nome"])
                team[f"part_{i}_prontuario"] = get(row, cols["prontuario"])
                team[f"part_{i}_cpf"] = get(row, cols["cpf"])
                team[f"part_{i}_email"] = get(row, cols["email"]).lower()
                team[f"part_{i}_tamanho_camiseta"] = get(row, cols["tamanho_camiseta"])
            teams.append(team)
    return teams


# ── Validações ────────────────────────────────────────────────────────────────


def validate(teams: list[dict], campi: dict[str, str]) -> list[str]:
    """
    Verifica consistência dos dados e devolve lista de mensagens de erro.
    Retorna lista vazia se tudo estiver correto.
    """
    erros: list[str] = []
    campus_set = {t["campus"] for t in teams}

    sem_sigla = sorted(c for c in campus_set if c not in campi)
    for c in sem_sigla:
        erros.append(f"Campus sem entrada em assets/ifsp_campi.csv: {c!r}")

    n_campus = len(campus_set)
    if n_campus > MAX_CAMPUS:
        erros.append(f"{n_campus} campus encontrados, mas o limite é {MAX_CAMPUS} (MAX_CAMPUS).")

    return erros


# ── Filtro por campus ─────────────────────────────────────────────────────────


def filtrar_por_sigla(
    credenciais: list["CredencialEquipe"],
    sigla: str,
    campi: dict[str, str],
) -> list["CredencialEquipe"]:
    """
    Filtra credenciais por campus, comparando a sigla (case-insensitive).
    Levanta ValueError se a sigla não existir no mapeamento de campi —
    distingue 'sigla inválida' de 'campus sem equipes' (lista vazia).
    """
    alvo = sigla.strip().upper()
    if alvo not in {s.upper() for s in campi.values()}:
        raise ValueError(f"sigla de campus desconhecida: {sigla!r}")
    return [c for c in credenciais if c.sigla.upper() == alvo]


# ── Geração de credenciais ────────────────────────────────────────────────────


def _agrupar_por_campus(teams: list[dict]) -> dict[str, list[dict]]:
    """
    Agrupa dicts de equipe por campus preservando a ordem de primeiro
    aparecimento de cada campus — independente da ordenação do CSV.
    """
    grupos: dict[str, list[dict]] = {}
    for team in teams:
        grupos.setdefault(team["campus"], []).append(team)
    return grupos


def gerar_credenciais(
    teams: list[dict],
    campi: dict[str, str],
    *,
    usar_sigla: bool = False,
) -> tuple[list[CredencialEquipe], list[dict]]:
    """
    Atribui usernames e senhas aleatórias a cada equipe e devolve:
      - lista de CredencialEquipe (usada para gerar arquivos e para emails)
      - info_campus: [{campus, sigla, prefixo, n_equipes, bloco_inicio, bloco_fim}, …]

    Agrupa internamente por campus — não depende da ordenação do CSV.
    Cada senha é gerada com secrets.choice sobre PASSWORD_ALPHABET (6 caracteres).
    """
    blocos = _usernumber_blocos()
    credenciais: list[CredencialEquipe] = []
    info_campus: list[dict] = []

    grupos = _agrupar_por_campus(teams)

    for bloco_idx, (campus, equipes) in enumerate(grupos.items()):
        sigla = campi[campus]
        prefixo = sigla.lower()
        label = sigla if usar_sigla else campus
        usernumber_base = blocos[bloco_idx]

        for n, team in enumerate(equipes, start=1):
            participantes = _participantes_de(team)

            credenciais.append(
                CredencialEquipe(
                    campus=campus,
                    sigla=sigla,
                    label=label,
                    nome_equipe=team["nome_equipe"],
                    username=f"team{prefixo}{n}",
                    password="".join(
                        secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH)
                    ),
                    coord_nome=team["coord_nome"],
                    coord_email=team["coord_email"],
                    resp_nome=team["resp_nome"],
                    resp_email=team["resp_email"],
                    participantes=participantes,
                    emails_cred=_emails_cred_para(team),
                )
            )

        info_campus.append(
            {
                "campus": campus,
                "sigla": sigla,
                "prefixo": prefixo,
                "n_equipes": len(equipes),
                "bloco_inicio": usernumber_base,
                "bloco_fim": usernumber_base + len(equipes) - 1,
            }
        )

    return credenciais, info_campus


# ── Leitura de usuarios.txt e enriquecimento ──────────────────────────────────


def parse_usuarios(path: Path) -> list[dict]:
    """
    Lê usuarios.txt e devolve apenas os registros usertype = team.
    Cada registro: {username, password, fullname}.
    """
    usuarios: list[dict] = []
    atual: dict[str, str] = {}

    with open(path, encoding="utf-8") as f:
        for linha in f:
            linha = linha.rstrip("\n")
            if "=" not in linha:
                # Linha em branco ou cabeçalho — finaliza registro atual
                if atual.get("usertype") == "team":
                    usuarios.append(
                        {
                            "username": atual.get("username", ""),
                            "password": atual.get("userpassword", ""),
                            "fullname": atual.get("userfullname", ""),
                        }
                    )
                atual = {}
                continue
            chave, _, valor = linha.partition("=")
            atual[chave.strip()] = valor.strip()

    # Último registro (arquivo pode não terminar com linha em branco)
    if atual.get("usertype") == "team":
        usuarios.append(
            {
                "username": atual.get("username", ""),
                "password": atual.get("userpassword", ""),
                "fullname": atual.get("userfullname", ""),
            }
        )

    return usuarios


_STAFF_SIGLA_RE = re.compile(r"^staff\d*([a-z]+)$", re.IGNORECASE)


def parse_staff_e_score(path: Path) -> tuple[dict[str, list[dict]], list[dict]]:
    """
    Lê usuarios.txt e devolve:
      - staff_por_sigla: {SIGLA: [{username, password}, ...]} para usertype=staff.
        Extrai a sigla do username pelo padrão staff[dígitos?][sigla]
        (ex.: 'staffarq' → 'ARQ', 'staff2spo' → 'SPO').
        Pode haver múltiplos usuários staff por campus.
      - score_users: [{username, password}, ...] para todos os usertype=score.
        Todos os campi recebem a lista completa.
    """
    staff: dict[str, list[dict]] = {}
    score_users: list[dict] = []
    atual: dict[str, str] = {}

    def _commit(rec: dict[str, str]) -> None:
        utype = rec.get("usertype", "")
        uname = rec.get("username", "")
        entry = {"username": uname, "password": rec.get("userpassword", "")}
        if utype == "staff":
            m = _STAFF_SIGLA_RE.match(uname)
            if m:
                sigla = m.group(1).upper()
                staff.setdefault(sigla, []).append(entry)
        elif utype == "score":
            score_users.append(entry)

    with open(path, encoding="utf-8") as f:
        for linha in f:
            linha = linha.rstrip("\n")
            if "=" not in linha:
                if atual:
                    _commit(atual)
                atual = {}
                continue
            chave, _, valor = linha.partition("=")
            atual[chave.strip()] = valor.strip()

    if atual:
        _commit(atual)

    return staff, score_users


_FULLNAME_RE = re.compile(r"^\[IFSP\s*-\s*[^\]]+\]\s*(.+)$")


def _extrair_nome_equipe(fullname: str) -> str:
    """
    Parseia '[IFSP - X] Nome da Equipe' → 'Nome da Equipe'.
    Retorna a string original se não casar com o padrão.
    """
    m = _FULLNAME_RE.match(fullname)
    return m.group(1).strip() if m else fullname.strip()


def enriquecer(
    usuarios: list[dict],
    teams_csv: list[dict],
    campi: dict[str, str],
    *,
    emit=None,
) -> list[CredencialEquipe]:
    """
    Junta credenciais de usuarios.txt com dados de email do CSV pelo nome da equipe.
    Username e senha vêm sempre de usuarios.txt; campos de contato vêm do CSV.
    Equipes sem correspondência no CSV geram aviso (se console fornecido) e ficam
    com emails vazios.
    """
    # Índice nome_equipe → linha do CSV
    by_name: dict[str, dict] = {t["nome_equipe"]: t for t in teams_csv}

    credenciais: list[CredencialEquipe] = []

    for u in usuarios:
        nome_equipe = _extrair_nome_equipe(u["fullname"])
        team = by_name.get(nome_equipe)

        if team is None:
            message = (
                f"Aviso: equipe {nome_equipe!r} não encontrada no CSV — "
                "campos de email ficarão vazios."
            )
            if emit is not None:
                emit(message)
            campus_raw = ""
            sigla = ""
        else:
            campus_raw = team["campus"]
            sigla = campi.get(campus_raw, "")

        participantes: list[dict] = []
        emails_cred: list[str] = []
        if team:
            participantes = _participantes_de(team)
            emails_cred = _emails_cred_para(team)

        credenciais.append(
            CredencialEquipe(
                campus=campus_raw,
                sigla=sigla,
                label=campus_raw,
                nome_equipe=nome_equipe,
                username=u["username"],
                password=u["password"],
                coord_nome=team["coord_nome"] if team else "",
                coord_email=team["coord_email"] if team else "",
                resp_nome=team["resp_nome"] if team else "",
                resp_email=team["resp_email"] if team else "",
                participantes=participantes,
                emails_cred=emails_cred,
            )
        )

    return credenciais


def credenciais_de_csv(
    teams_csv: list[dict],
    campi: dict[str, str],
) -> list[CredencialEquipe]:
    """
    Constrói CredencialEquipe diretamente do CSV de inscrições, sem depender de
    usuarios.txt.  Usado pela lista de presença, que não usa username/senha — o
    CSV de inscrições já tem tudo (equipe, participantes com prontuário/CPF,
    coordenador e responsável).  Preserva a ordem do CSV.
    """
    credenciais: list[CredencialEquipe] = []
    for team in teams_csv:
        campus_raw = team["campus"]
        credenciais.append(
            CredencialEquipe(
                campus=campus_raw,
                sigla=campi.get(campus_raw, ""),
                label=campus_raw,
                nome_equipe=team["nome_equipe"],
                username="",
                password="",
                coord_nome=team["coord_nome"],
                coord_email=team["coord_email"],
                resp_nome=team["resp_nome"],
                resp_email=team["resp_email"],
                participantes=_participantes_de(team),
                emails_cred=_emails_cred_para(team),
            )
        )
    return credenciais
