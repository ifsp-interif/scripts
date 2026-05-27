#!/usr/bin/env python3
"""
Envia as credenciais de acesso do BOCA por email, lendo username/senha
diretamente de usuarios.txt (fonte da verdade) e endereços do CSV de equipes.

Destinatários:
  • Coordenador de campus — lista de times e senhas agrupada por técnico
  • Cada técnico responsável — sua(s) equipe(s) e senha(s)
  • Participantes indicados — login e senha da própria equipe
  • EMAIL_INTERIF (config.py) — resumo geral

Uso:
    uv run python enviar_credenciais.py [--usuarios USUARIOS_TXT]
                                        [--csv CSV] [--campi CAMPI]
                                        [--dry-run]
"""

import argparse
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from tabulate import tabulate

from config import CRED_SUBJECT_PREFIX as EMAIL_SUBJECT_PREFIX
from config import EMAIL_INTERIF, TITULO_EVENTO
from interif_core import (
    CAMPI_FILE,
    CSV_FILE,
    CredencialEquipe,
    enriquecer,
    load_campi,
    load_teams,
    parse_usuarios,
)

_HERE           = Path(__file__).parent
USUARIOS_FILE   = _HERE / "output" / "usuarios.txt"

# ── Envio de emails ───────────────────────────────────────────────────────────

def _send(
    to: str,
    subject: str,
    body: str,
    *,
    cc: str | None = None,
    dry_run: bool,
) -> None:
    """Wrapper sobre `gws gmail +send`. Em dry-run, exibe o email no terminal sem enviar."""
    dest = to + (f" (cc: {cc})" if cc else "")
    if dry_run:
        print(f"  -> Para: {dest}")
        print(f"     Assunto: {subject}")
        print(body)
        return
    print(f"  -> Enviando para {dest} ...")
    cmd = ["gws", "gmail", "+send", "--to", to, "--subject", subject, "--body", body]
    if cc:
        cmd += ["--cc", cc]
    try:
        subprocess.run(cmd, check=True)
        print("    OK")
    except subprocess.CalledProcessError as exc:
        print(f"    Erro: {exc}")


def enviar_emails_coordenadores(
    credenciais: list[CredencialEquipe],
    dry_run: bool,
) -> int:
    """
    Envia um email por campus ao coordenador listando times e senhas,
    agrupados por técnico responsável.
    """
    print("\n── Coordenadores de campus")

    # campus → {coord_nome, coord_email, por_tecnico: {resp_email → {nome, equipes}}}
    por_campus: dict[str, dict] = {}
    for cred in credenciais:
        if not cred.coord_email:
            continue
        if cred.campus not in por_campus:
            por_campus[cred.campus] = {
                "coord_nome":  cred.coord_nome,
                "coord_email": cred.coord_email,
                "por_tecnico": defaultdict(lambda: {"resp_nome": "", "equipes": []}),
            }
        tec = por_campus[cred.campus]["por_tecnico"][cred.resp_email]
        tec["resp_nome"] = cred.resp_nome
        tec["equipes"].append(cred)

    count = 0
    for campus, data in por_campus.items():
        primeiro = data["coord_nome"].strip().split()[0] if data["coord_nome"].strip() else "Coordenador(a)"
        linhas = [
            f"Olá, {primeiro}!\n\n",
            f"Seguem as credenciais de acesso das equipes do campus {campus}:\n",
        ]
        for tec in data["por_tecnico"].values():
            linhas.append(f"\nTécnico: {tec['resp_nome']}\n")
            for cred in tec["equipes"]:
                linhas.append(f"  - {cred.nome_equipe}: {cred.username} / {cred.password}\n")
        linhas.append(f"\nAtenciosamente,\nOrganização {TITULO_EVENTO}")

        _send(
            to=data["coord_email"],
            subject=f"{EMAIL_SUBJECT_PREFIX} — Campus {campus}",
            body="".join(linhas),
            dry_run=dry_run,
        )
        count += 1

    return count


def enviar_emails_tecnicos(
    credenciais: list[CredencialEquipe],
    dry_run: bool,
) -> int:
    """
    Envia um email consolidado por técnico responsável com todas as suas equipes.
    """
    print("\n── Técnicos responsáveis")

    por_tecnico: dict[str, dict] = {}
    for cred in credenciais:
        if not cred.resp_email:
            continue
        if cred.resp_email not in por_tecnico:
            por_tecnico[cred.resp_email] = {"resp_nome": cred.resp_nome, "equipes": []}
        por_tecnico[cred.resp_email]["equipes"].append(cred)

    count = 0
    for email, data in por_tecnico.items():
        nome = data["resp_nome"].strip().split()[0] if data["resp_nome"].strip() else "Professor(a)"
        linhas = [
            f"Olá, {nome}!\n\n",
            "Seguem as credenciais de acesso das equipes sob sua responsabilidade:\n\n",
        ]
        for cred in data["equipes"]:
            linhas.append(f"{cred.nome_equipe}: {cred.username} / {cred.password}\n")
        linhas.append(f"\nAtenciosamente,\nOrganização {TITULO_EVENTO}")

        _send(
            to=email,
            subject=EMAIL_SUBJECT_PREFIX,
            body="".join(linhas),
            dry_run=dry_run,
        )
        count += 1

    return count


def enviar_emails_participantes(
    credenciais: list[CredencialEquipe],
    dry_run: bool,
) -> int:
    """
    Para cada equipe cujos participantes optaram por receber credenciais,
    envia um único email (--to primeiro, --cc demais).
    """
    print("\n── Participantes indicados")

    count = 0
    for cred in credenciais:
        if not cred.emails_cred:
            continue

        body = (
            f"Prezado(a) participante,\n\n"
            f"Segue o acesso da equipe {cred.nome_equipe} para o {TITULO_EVENTO}:\n\n"
            f"Login: {cred.username}\n"
            f"Senha: {cred.password}\n\n"
            f"Atenciosamente,\nOrganização {TITULO_EVENTO}"
        )

        to = cred.emails_cred[0]
        cc = ",".join(cred.emails_cred[1:]) if len(cred.emails_cred) > 1 else None

        _send(
            to=to,
            subject=f"{EMAIL_SUBJECT_PREFIX} — Equipe {cred.nome_equipe}",
            body=body,
            cc=cc,
            dry_run=dry_run,
        )
        count += 1

    return count


def enviar_resumo(
    credenciais: list[CredencialEquipe],
    n_coord: int,
    n_tec: int,
    n_part: int,
    dry_run: bool,
) -> None:
    """Envia email de resumo para EMAIL_INTERIF (definido em config.py)."""
    print("\n── Resumo para a organização")

    por_campus: dict[str, int] = {}
    for cred in credenciais:
        por_campus[cred.campus] = por_campus.get(cred.campus, 0) + 1

    linhas = [
        f"Resumo de envio de credenciais — {TITULO_EVENTO}\n\n",
        "Emails enviados:\n",
        f"  Coordenadores de campus: {n_coord}\n",
        f"  Técnicos responsáveis:   {n_tec}\n",
        f"  Participantes:           {n_part}\n\n",
        "Equipes por campus:\n",
    ]
    for campus, n in sorted(por_campus.items()):
        linhas.append(f"  {campus}: {n} equipe(s)\n")
    linhas.append(f"\nTotal: {len(credenciais)} equipe(s)\n")

    _send(
        to=EMAIL_INTERIF,
        subject=f"Resumo de envio de credenciais — {TITULO_EVENTO}",
        body="".join(linhas),
        dry_run=dry_run,
    )


# ── Exibição ──────────────────────────────────────────────────────────────────

def render_summary(credenciais: list[CredencialEquipe], n_emails: int, dry_run: bool) -> None:
    por_campus: dict[str, int] = {}
    for cred in credenciais:
        por_campus[cred.campus] = por_campus.get(cred.campus, 0) + 1

    rows: list[list[str | int]] = [
        ["Equipes", len(credenciais)],
        ["Campus", len(por_campus)],
    ]
    if dry_run:
        rows.append(["Emails", f"dry-run ({n_emails} simulado(s))"])
    else:
        rows.append(["Emails", f"{n_emails} enviado(s)"])

    print("Resumo")
    print(tabulate(rows, tablefmt="simple"))


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Envia credenciais de acesso BOCA por email. "
            "Lê username/senha de usuarios.txt e endereços do CSV de equipes."
        )
    )
    parser.add_argument(
        "--usuarios",
        default=str(USUARIOS_FILE),
        metavar="ARQUIVO",
        help=f"Caminho para usuarios.txt (padrão: {USUARIOS_FILE})",
    )
    parser.add_argument(
        "--csv",
        default=str(CSV_FILE),
        metavar="ARQUIVO",
        help=f"Caminho do CSV de equipes (padrão: {CSV_FILE.name})",
    )
    parser.add_argument(
        "--campi",
        default=str(CAMPI_FILE),
        metavar="ARQUIVO",
        help=f"Mapeamento campus→sigla (padrão: {CAMPI_FILE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula o envio sem disparar emails reais",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    usuarios_path = Path(args.usuarios)
    csv_path      = Path(args.csv)
    campi_path    = Path(args.campi)

    # Verifica arquivos de entrada
    for p in (usuarios_path, csv_path, campi_path):
        if not p.exists():
            print(f"Erro: arquivo não encontrado: {p}", file=sys.stderr)
            sys.exit(1)

    print("Envio de credenciais - InterIF")
    print(f"Usuários: {usuarios_path.resolve()}")
    print(f"CSV:      {csv_path.resolve()}")
    print(f"Campi:    {campi_path.resolve()}")
    print(f"Modo:     {'dry-run' if args.dry_run else 'envio real'}")
    print()

    campi     = load_campi(campi_path)
    teams_csv = load_teams(csv_path)
    usuarios  = parse_usuarios(usuarios_path)

    print(f"{len(usuarios)} equipe(s) em usuarios.txt | {len(teams_csv)} linha(s) no CSV.")

    credenciais = enriquecer(usuarios, teams_csv, campi, emit=print)

    n_coord = enviar_emails_coordenadores(credenciais, args.dry_run)
    n_tec   = enviar_emails_tecnicos(credenciais, args.dry_run)
    n_part  = enviar_emails_participantes(credenciais, args.dry_run)
    enviar_resumo(credenciais, n_coord, n_tec, n_part, args.dry_run)
    total_emails = n_coord + n_tec + n_part + 1

    print()
    render_summary(credenciais, total_emails, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
