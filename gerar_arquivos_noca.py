#!/usr/bin/env python3
"""
Lê equipes_interif.csv e gera o arquivo de importação em lote para o NOCA:
  • usuarios_noca.csv  — lista de usuários (CSV) pronta para upload no NOCA
  • usuarios_noca.json — mesma lista em formato JSON (com --formato json)

Cada campus vira um site no NOCA; o campo ``site`` de cada linha aciona a
criação automática do site correspondente durante o import em lote.

Funções geradas
---------------
  teams  — um por equipe inscrita (email: participante 1)
  staff  — um por campus, username staff{sigla} (email: coordenador do campus)
  judge  — um por técnico/responsável, deduplicado por CPF (username: judge{n})
  user   — scoreif (placar)

Colunas de saída (CSV / JSON)
------------------------------
  username  fullname  role  password  email  site  location

Uso:
    uv run python gerar_arquivos_noca.py [CSV] [-o DIR] [--campi CAMPI]
                                         [--output-file ARQUIVO]
                                         [--formato {csv,json}]
                                         [--slug SLUG]
                                         [--sigla] [--dry-run]
"""

import argparse
import csv
import io
import json
import sys
from datetime import datetime
from pathlib import Path

from tabulate import tabulate

from config import TITULO_EVENTO
from interif_core import (
    CAMPI_FILE,
    CSV_FILE,
    CredencialEquipe,
    gerar_credenciais,
    load_campi,
    load_teams,
    validate,
)

# ── Constantes de saída ───────────────────────────────────────────────────────

_CSV_HEADERS = ["username", "fullname", "role", "password", "email", "site", "location"]
_DEFAULT_OUTPUT_CSV = "usuarios_noca.csv"
_DEFAULT_OUTPUT_JSON = "usuarios_noca.json"


# ── Construtores de linhas ────────────────────────────────────────────────────


def _build_team_rows(
    credenciais: list[CredencialEquipe],
    *,
    usar_sigla_site: bool,
) -> list[dict]:
    """Devolve uma linha por equipe para o arquivo NOCA.

    email → primeiro participante da equipe (se disponível).
    """
    rows: list[dict] = []
    for cred in credenciais:
        site_name = cred.sigla if usar_sigla_site else cred.campus
        part1_email = cred.participantes[0]["email"] if cred.participantes else ""
        rows.append(
            {
                "username": cred.username,
                "fullname": cred.nome_equipe,
                "role": "team",
                "password": cred.password,
                "email": part1_email,
                "site": site_name,
                "location": "",
            }
        )
    return rows


def _build_staff_rows(
    info_campus: list[dict],
    credenciais: list[CredencialEquipe],
    ano: int,
    *,
    usar_sigla_site: bool,
) -> list[dict]:
    """Devolve uma linha de staff por campus para o arquivo NOCA.

    email → coordenador local do campus.
    """
    # Monta índices campus → label e campus → coord_email
    label_por_campus: dict[str, str] = {}
    coord_email_por_campus: dict[str, str] = {}
    for cred in credenciais:
        label_por_campus.setdefault(cred.campus, cred.label)
        coord_email_por_campus.setdefault(cred.campus, cred.coord_email)

    rows: list[dict] = []
    for info in info_campus:
        campus = info["campus"]
        sigla = info["sigla"]
        prefixo = info["prefixo"]
        label = label_por_campus.get(campus, sigla)
        site_name = sigla if usar_sigla_site else campus
        rows.append(
            {
                "username": f"staff{prefixo}",
                "fullname": f"Staff - {label}",
                "role": "staff",
                "password": f"staff@{prefixo}{ano}",
                "email": coord_email_por_campus.get(campus, ""),
                "site": site_name,
                "location": "",
            }
        )
    return rows


def _build_judge_rows(teams: list[dict], ano: int) -> list[dict]:
    """Devolve uma linha de judge por técnico (Responsável), deduplicada por CPF.

    Técnicos sem CPF são deduplicados pelo email; sem email, pelo nome.
    Ordem de aparecimento no CSV é preservada.
    username → judge{n} (sequencial, 1-based).
    """
    seen: set[str] = set()
    tecnicos: list[dict] = []

    for team in teams:
        nome = team.get("resp_nome", "").strip()
        cpf = team.get("resp_cpf", "").strip()
        email = team.get("resp_email", "").strip()
        if not nome:
            continue
        # Chave de deduplicação: CPF > email > nome
        chave = cpf or email or nome
        if chave in seen:
            continue
        seen.add(chave)
        tecnicos.append({"nome": nome, "email": email})

    rows: list[dict] = []
    for n, tec in enumerate(tecnicos, start=1):
        rows.append(
            {
                "username": f"judge{n}",
                "fullname": tec["nome"],
                "role": "judge",
                "password": f"judgeif@{ano}",
                "email": tec["email"],
                "site": "",
                "location": "",
            }
        )
    return rows


def _build_score_row(ano: int) -> dict:
    """Devolve a linha do usuário de placar para o arquivo NOCA (role: user)."""
    return {
        "username": "scoreif",
        "fullname": f"Placar - Maratona InterIF {ano}",
        "role": "user",
        "password": f"scoreif@{ano}",
        "email": "",
        "site": "",
        "location": "",
    }


# ── Serialização ──────────────────────────────────────────────────────────────


def build_csv(rows: list[dict]) -> str:
    """Serializa as linhas como CSV compatível com o NOCA (UTF-8)."""
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=_CSV_HEADERS,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        # Garante que colunas vazias saiam como string vazia, não ausentes
        writer.writerow({h: row.get(h, "") for h in _CSV_HEADERS})
    return buf.getvalue()


def build_json(rows: list[dict], slug: str | None) -> str:
    """Serializa as linhas como JSON compatível com o NOCA."""
    # Remove colunas vazias para não poluir o JSON
    users = [{k: v for k, v in row.items() if v} for row in rows]
    payload: dict = {"users": users}
    if slug:
        payload = {"contest-slug": slug, **payload}
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


# ── Exibição ──────────────────────────────────────────────────────────────────


def render_table(info_campus: list[dict]) -> None:
    """Imprime a tabela de campus/equipes."""
    rows = [[info["campus"], info["sigla"], info["n_equipes"]] for info in info_campus]
    print(tabulate(rows, headers=["Campus", "Sigla", "Nº Equipes"], tablefmt="simple"))


def render_summary(
    info_campus: list[dict],
    all_rows: list[dict],
    destino: str,
    *,
    dry_run: bool,
    formato: str,
) -> None:
    """Imprime o resumo final da geração."""
    n_equipes = sum(i["n_equipes"] for i in info_campus)
    n_campus = len(info_campus)
    n_staff = n_campus
    n_judges = sum(1 for r in all_rows if r.get("role") == "judge")
    n_total = len(all_rows)

    rows: list[list] = [
        ["Equipes (team)", n_equipes],
        ["Campus (staff)", n_staff],
        ["Técnicos (judge)", n_judges],
        ["Placar (user)", 1],
        ["Total de linhas", n_total],
        ["Formato", formato.upper()],
    ]
    if dry_run:
        rows.append(["Modo", "dry-run (nenhum arquivo escrito)"])
    else:
        rows.append(["Arquivo", destino])

    print("Resumo")
    print(tabulate(rows, tablefmt="simple"))


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Gera o arquivo de importação em lote para o NOCA "
            "(usuarios_noca.csv ou usuarios_noca.json) "
            "a partir do equipes_interif.csv. "
            "Cada campus vira um site no NOCA."
        )
    )
    parser.add_argument(
        "csv_file",
        nargs="?",
        default=str(CSV_FILE),
        metavar="CSV",
        help=f"Caminho do CSV de equipes (padrão: {CSV_FILE.name})",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        metavar="ARQUIVO",
        help=(
            "Nome do arquivo de saída "
            f"(padrão: {_DEFAULT_OUTPUT_CSV} / {_DEFAULT_OUTPUT_JSON} conforme --formato)"
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        default="output",
        metavar="DIR",
        help="Diretório de saída (padrão: output/); criado automaticamente se não existir",
    )
    parser.add_argument(
        "--campi",
        default=str(CAMPI_FILE),
        metavar="ARQUIVO",
        help=f"Mapeamento campus→sigla (padrão: {CAMPI_FILE})",
    )
    parser.add_argument(
        "--formato",
        choices=["csv", "json"],
        default="csv",
        help="Formato de saída: csv (padrão) ou json",
    )
    parser.add_argument(
        "--slug",
        default=None,
        metavar="SLUG",
        help=(
            "Slug do contest no NOCA — incorporado ao JSON como 'contest-slug' "
            "para validação no upload (só relevante com --formato json)"
        ),
    )
    parser.add_argument(
        "--sigla",
        action="store_true",
        help=(
            "Usa a sigla do campus como nome do site e no fullname "
            "(ex: 'SPO' em vez de 'São Paulo'); "
            "por padrão usa o nome completo do campus"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Exibe o que seria gerado sem escrever arquivos",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    csv_path = Path(args.csv_file)
    campi_path = Path(args.campi)
    output_dir = Path(args.output)
    ano = datetime.now().year
    formato = args.formato

    # Nome do arquivo de saída
    default_filename = _DEFAULT_OUTPUT_JSON if formato == "json" else _DEFAULT_OUTPUT_CSV
    output_filename = args.output_file or default_filename

    # Verifica arquivos de entrada
    for p in (csv_path, campi_path):
        if not p.exists():
            print(f"Erro: arquivo não encontrado: {p}", file=sys.stderr)
            sys.exit(1)

    print(f"Gerador de arquivos NOCA - {TITULO_EVENTO}")
    print(f"CSV:    {csv_path.resolve()}")
    print(f"Campi:  {campi_path.resolve()}")
    print(f"Saída:  {output_dir.resolve()}")
    print()

    campi = load_campi(campi_path)
    teams = load_teams(csv_path)

    print(f"{len(teams)} equipe(s) carregada(s).\n")

    erros = validate(teams, campi)
    if erros:
        print("Erro: inconsistências nos dados:", file=sys.stderr)
        for erro in erros:
            print(f"  - {erro}", file=sys.stderr)
        print("\nCorrija os problemas acima e tente novamente.", file=sys.stderr)
        sys.exit(1)

    credenciais, info_campus = gerar_credenciais(teams, campi, usar_sigla=args.sigla)

    team_rows = _build_team_rows(credenciais, usar_sigla_site=args.sigla)
    staff_rows = _build_staff_rows(info_campus, credenciais, ano, usar_sigla_site=args.sigla)
    judge_rows = _build_judge_rows(teams, ano)
    score_row = _build_score_row(ano)

    all_rows: list[dict] = team_rows + staff_rows + judge_rows + [score_row]

    conteudo = build_json(all_rows, slug=args.slug) if formato == "json" else build_csv(all_rows)

    render_table(info_campus)
    print()

    destino = str(output_dir / output_filename)

    if args.dry_run:
        sep = "─" * 60
        print(sep)
        print(f"── {output_filename} ──")
        print(sep)
        print(conteudo)
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / output_filename).write_text(conteudo, encoding="utf-8", newline="\n")

    render_summary(
        info_campus,
        all_rows,
        destino,
        dry_run=args.dry_run,
        formato=formato,
    )

    if not args.dry_run:
        print(f"\nOK: arquivo gerado com sucesso → {destino}")


if __name__ == "__main__":
    main()
