#!/usr/bin/env python3
"""
Lê equipes_interif.csv e gera os quatro arquivos de configuração do BOCA:
  • usuarios.txt        — cadastro de usuários (times, staff, juízes, placar)
  • INTERIF.toml        — configuração de sedes para o animator
  • score.sep           — definição de blocos de placar
  • secret_interif.toml — segredos por sede

Uso:
    uv run python gerar_arquivos_boca.py [CSV] [-u USUARIOS] [-a TOML]
                                         [-s SCORE] [--secrets SECRET]
                                         [-o DIR] [--campi CAMPI]
                                         [--sigla] [--dry-run]
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from tabulate import tabulate

from config import SALT, SECRET_GERAL, TITULO_EVENTO
from interif_core import (
    CAMPI_FILE,
    CSV_FILE,
    JUDGE_USERNUMBER,
    SCORE_USERNUMBER,
    STAFF_USERNUMBER_START,
    USERSITENUMBER,
    CredencialEquipe,
    _usernumber_blocos,
    gerar_credenciais,
    load_campi,
    load_teams,
    validate,
)

# ── Construtores de conteúdo ──────────────────────────────────────────────────


def build_usuarios(
    credenciais: list[CredencialEquipe],
    info_campus: list[dict],
    ano: int,
) -> str:
    """Constrói o conteúdo de usuarios.txt a partir das credenciais já geradas."""
    blocos = _usernumber_blocos()
    linhas: list[str] = ["[user]\n"]
    staff_counter = STAFF_USERNUMBER_START

    # Índice rápido campus → lista de credenciais (preserva ordem)
    cred_por_campus: dict[str, list[CredencialEquipe]] = {}
    for cred in credenciais:
        cred_por_campus.setdefault(cred.campus, []).append(cred)

    for bloco_idx, info in enumerate(info_campus):
        campus = info["campus"]
        prefixo = info["prefixo"]
        usernumber_base = blocos[bloco_idx]
        equipes = cred_por_campus[campus]
        label = equipes[0].label  # sigla ou nome completo conforme --sigla

        for n, cred in enumerate(equipes, start=1):
            usernumber = usernumber_base + n - 1
            linhas.append(f"usernumber = {usernumber}\n")
            linhas.append(f"usersitenumber = {USERSITENUMBER}\n")
            linhas.append(f"username = {cred.username}\n")
            linhas.append(f"userpassword = {cred.password}\n")
            linhas.append("usertype = team\n")
            linhas.append(f"userfullname = [IFSP - {label}] {cred.nome_equipe}\n")
            linhas.append("userenabled = t\n")
            linhas.append("usermultilogin = f\n\n")

        linhas.append(f"usernumber = {staff_counter}\n")
        linhas.append(f"usersitenumber = {USERSITENUMBER}\n")
        linhas.append(f"username = staff{prefixo}\n")
        linhas.append(f"userpassword = staff@{prefixo}{ano}\n")
        linhas.append("usertype = staff\n")
        linhas.append(f"userfullname = [IFSP - {label}] Staff - {label}\n")
        linhas.append("userenabled = t\n")
        linhas.append("usermultilogin = t\n\n")
        staff_counter += 1

    # Usuários especiais
    linhas.append(f"usernumber = {JUDGE_USERNUMBER}\n")
    linhas.append(f"usersitenumber = {USERSITENUMBER}\n")
    linhas.append("username = judgeif\n")
    linhas.append(f"userpassword = judgeif@{ano}\n")
    linhas.append("usertype = judge\n")
    linhas.append(f"userfullname = [IFSP] Juízes - Maratona InterIF {ano}\n")
    linhas.append("userenabled = t\n")
    linhas.append("usermultilogin = t\n\n")

    linhas.append(f"usernumber = {SCORE_USERNUMBER}\n")
    linhas.append(f"usersitenumber = {USERSITENUMBER}\n")
    linhas.append("username = scoreif\n")
    linhas.append(f"userpassword = scoreif@{ano}\n")
    linhas.append("usertype = score\n")
    linhas.append(f"userfullname = [IFSP] Placar - Maratona InterIF {ano}\n")
    linhas.append("userenabled = t\n")
    linhas.append("usermultilogin = t\n\n")

    return "".join(linhas)


def build_toml(info_campus: list[dict]) -> str:
    """Constrói o conteúdo de INTERIF.toml."""
    linhas: list[str] = []

    linhas.append("[titulo]\n")
    linhas.append(f'name = "{TITULO_EVENTO}"\n')
    linhas.append('codes = [""]\n')
    linhas.append("vagas = 3\n")
    linhas.append("ouro = 1\n")
    linhas.append("prata = 2\n")
    linhas.append("bronze = 3\n\n")

    linhas.append("[[sedes]]\n")
    linhas.append('name = "Geral"\n')
    linhas.append('codes = [""]\n')
    linhas.append("vagas = 3\n")
    linhas.append("ouro = 1\n")
    linhas.append("prata = 2\n")
    linhas.append("bronze = 3\n\n")

    for info in info_campus:
        linhas.append("[[sedes]]\n")
        linhas.append(f'name = "{info["sigla"]}"\n')
        linhas.append(f'codes = ["team{info["prefixo"]}"]\n')
        linhas.append("premiacao = false\n")
        linhas.append("vagas = 0\n\n")

    return "".join(linhas)


def build_score(info_campus: list[dict]) -> str:
    """Constrói o conteúdo de score.sep."""
    blocos = _usernumber_blocos()
    geral_inicio = blocos[0]
    geral_fim = info_campus[-1]["bloco_fim"] if info_campus else geral_inicio

    linhas: list[str] = []
    linhas.append(f"GERAL {geral_inicio}/{geral_fim}/1 # /^team/ /^score/ /^judge/ /^admin/\n")

    for info in info_campus:
        prefixo = info["prefixo"]
        linhas.append(
            f"{info['sigla']} {info['bloco_inicio']}/{info['bloco_fim']}/1 "
            f"# /^team{prefixo}/ /^score/ /^staff{prefixo}/\n"
        )

    return "".join(linhas)


def build_secrets(info_campus: list[dict]) -> str:
    """Constrói o conteúdo de secret_interif.toml."""
    linhas: list[str] = []
    linhas.append(f'salt = "{SALT}"\n\n')

    linhas.append("[[secrets]]\n")
    linhas.append('name = "Geral"\n')
    linhas.append(f'secret = "{SECRET_GERAL}"\n\n')

    for info in info_campus:
        linhas.append("[[secrets]]\n")
        linhas.append(f'name = "{info["sigla"]}"\n')
        linhas.append(f'secret = "{info["prefixo"]}_abc"\n\n')

    return "".join(linhas)


# ── Exibição ──────────────────────────────────────────────────────────────────


def render_table(info_campus: list[dict]) -> None:
    rows = [
        [
            info["campus"],
            info["sigla"],
            info["n_equipes"],
            f"{info['bloco_inicio']}–{info['bloco_fim']}",
        ]
        for info in info_campus
    ]
    print(
        tabulate(
            rows, headers=["Campus", "Sigla", "Nº Equipes", "Bloco usernumber"], tablefmt="simple"
        )
    )


def render_summary(
    info_campus: list[dict],
    destinos: dict[str, str],
    dry_run: bool,
) -> None:
    n_equipes = sum(i["n_equipes"] for i in info_campus)
    n_campus = len(info_campus)

    rows: list[list[str | int]] = [
        ["Equipes", n_equipes],
        ["Campus", n_campus],
    ]

    if dry_run:
        rows.append(["Modo", "dry-run (nenhum arquivo escrito)"])
    else:
        for label, path in destinos.items():
            rows.append([label, path])

    print("Resumo")
    print(tabulate(rows, tablefmt="simple"))


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Gera os arquivos de configuração do BOCA "
            "(usuarios.txt, INTERIF.toml, score.sep, secret_interif.toml) "
            "a partir do equipes_interif.csv."
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
        "-u",
        "--user-output",
        default="usuarios.txt",
        metavar="ARQUIVO",
        help="Arquivo de saída de usuários (padrão: usuarios.txt)",
    )
    parser.add_argument(
        "-a",
        "--animator",
        default="INTERIF.toml",
        metavar="ARQUIVO",
        help="Arquivo de saída do animator (padrão: INTERIF.toml)",
    )
    parser.add_argument(
        "-s",
        "--score",
        default="score.sep",
        metavar="ARQUIVO",
        help="Arquivo de saída do score (padrão: score.sep)",
    )
    parser.add_argument(
        "--secrets",
        default="secret_interif.toml",
        metavar="ARQUIVO",
        help="Arquivo de saída de segredos (padrão: secret_interif.toml)",
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
        "--sigla",
        action="store_true",
        help=(
            "Usa a sigla do campus no userfullname "
            "(ex: '[IFSP - SPO]' em vez de '[IFSP - São Paulo]')"
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

    # Verifica arquivos de entrada
    for p in (csv_path, campi_path):
        if not p.exists():
            print(f"Erro: arquivo não encontrado: {p}", file=sys.stderr)
            sys.exit(1)

    print("Gerador de arquivos BOCA - InterIF")
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

    usuarios_txt = build_usuarios(credenciais, info_campus, ano)
    toml_txt = build_toml(info_campus)
    score_txt = build_score(info_campus)
    secrets_txt = build_secrets(info_campus)

    render_table(info_campus)
    print()

    destinos = {
        "Usuários": str(output_dir / args.user_output),
        "Animator": str(output_dir / args.animator),
        "Score": str(output_dir / args.score),
        "Secrets": str(output_dir / args.secrets),
    }

    if args.dry_run:
        _sep = "─" * 60
        for label, conteudo in [
            ("usuarios.txt", usuarios_txt),
            ("INTERIF.toml", toml_txt),
            ("score.sep", score_txt),
            ("secret_interif.toml", secrets_txt),
        ]:
            print(_sep)
            print(f"── {label} ──")
            print(_sep)
            print(conteudo)
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        saidas = [
            (output_dir / args.user_output, usuarios_txt),
            (output_dir / args.animator, toml_txt),
            (output_dir / args.score, score_txt),
            (output_dir / args.secrets, secrets_txt),
        ]
        for caminho, conteudo in saidas:
            caminho.write_text(conteudo, encoding="utf-8", newline="\n")

    render_summary(info_campus, destinos, dry_run=args.dry_run)

    if not args.dry_run:
        print("\nOK: 4 arquivo(s) gerado(s) com sucesso.")


if __name__ == "__main__":
    main()
