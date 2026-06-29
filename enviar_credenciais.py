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
                                        [-1 | -2] [--csv CSV] [--campi CAMPI]
                                        [--campus SIGLA]
                                        [--so-coordenadores] [--so-responsaveis]
                                        [--so-participantes]
                                        [--dry-run]

As flags --so-* são combináveis e restringem o envio aos grupos escolhidos
(pulando o email de resumo). Sem nenhuma delas, envia para todos os grupos.
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

from tabulate import tabulate

from config import (
    CRED_BODY_TEMPLATE,
    EMAIL_INTERIF,
    STAFF_BODY_TEMPLATE,
    STAFF_SUBJECT,
    TITULO_EVENTO,
)
from config import (
    CRED_SUBJECT_PREFIX as EMAIL_SUBJECT_PREFIX,
)
from email_utils import send_email
from interif_core import (
    CAMPI_FILE,
    CSV_FILE,
    CredencialEquipe,
    enriquecer,
    filtrar_por_sigla,
    load_campi,
    load_teams,
    parse_staff_e_score,
    parse_usuarios,
)

_HERE = Path(__file__).parent
USUARIOS_FILE = _HERE / "output" / "usuarios.txt"


def _enderecos_ja_enviados(path: Path) -> set[str]:
    """
    Lê um log de execução anterior (stdout do script / formato gws) e devolve o
    conjunto de endereços que obtiveram 'OK: enviado'. Usado para retomar um envio
    interrompido sem reenviar para quem já recebeu.
    """
    ok: set[str] = set()
    ultimo: str | None = None
    for linha in path.read_text(encoding="utf-8").splitlines():
        m = re.search(r"Enviando para (\S+) \.\.\.", linha)
        if m:
            ultimo = m.group(1)
        elif "OK: enviado" in linha and ultimo:
            ok.add(ultimo)
            ultimo = None
    return ok


# ── Envio de emails ───────────────────────────────────────────────────────────


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
                "coord_nome": cred.coord_nome,
                "coord_email": cred.coord_email,
                "por_tecnico": defaultdict(lambda: {"resp_nome": "", "equipes": []}),
            }
        tec = por_campus[cred.campus]["por_tecnico"][cred.resp_email]
        tec["resp_nome"] = cred.resp_nome
        tec["equipes"].append(cred)

    count = 0
    for campus, data in por_campus.items():
        primeiro = (
            data["coord_nome"].strip().split()[0]
            if data["coord_nome"].strip()
            else "Coordenador(a)"
        )
        linhas = [
            f"Olá, {primeiro}!\n\n",
            f"Seguem as credenciais de acesso das equipes do campus {campus}:\n",
        ]
        for tec in data["por_tecnico"].values():
            linhas.append(f"\nTécnico: {tec['resp_nome']}\n")
            for cred in tec["equipes"]:
                linhas.append(f"  - {cred.nome_equipe}: {cred.username} / {cred.password}\n")
        linhas.append(f"\nAtenciosamente,\nOrganização {TITULO_EVENTO}")

        send_email(
            data["coord_email"],
            f"{EMAIL_SUBJECT_PREFIX} — Campus {campus}",
            "".join(linhas),
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

        send_email(email, EMAIL_SUBJECT_PREFIX, "".join(linhas), dry_run=dry_run)
        count += 1

    return count


def enviar_emails_participantes(
    credenciais: list[CredencialEquipe],
    dry_run: bool,
    ja_enviados: set[str] | None = None,
) -> int:
    """
    Para cada equipe cujos participantes optaram por receber credenciais,
    envia um único email (--to primeiro, --cc demais).

    Equipes cujo destinatário primário já consta em `ja_enviados` são puladas
    (retomada de um envio interrompido). Uma falha em uma equipe é registrada e
    não interrompe o lote; o resumo das falhas é impresso ao final.
    """
    print("\n── Participantes indicados")
    ja_enviados = ja_enviados or set()

    count = 0
    pulados = 0
    falhas: list[tuple[str, str, str]] = []  # (equipe, to, motivo)
    for cred in credenciais:
        if not cred.emails_cred:
            continue

        to = cred.emails_cred[0]
        if to in ja_enviados:
            pulados += 1
            continue

        body = CRED_BODY_TEMPLATE.format(
            nome_equipe=cred.nome_equipe,
            username=cred.username,
            password=cred.password,
        )

        cc = ",".join(cred.emails_cred[1:]) if len(cred.emails_cred) > 1 else None

        try:
            send_email(
                to,
                f"{EMAIL_SUBJECT_PREFIX} — Equipe {cred.nome_equipe}",
                body,
                cc=cc,
                dry_run=dry_run,
            )
            count += 1
        except Exception as exc:  # noqa: BLE001 — registra e segue o lote
            falhas.append((cred.nome_equipe, to, str(exc).splitlines()[-1]))

    if pulados:
        print(f"  ({pulados} equipe(s) puladas — já enviadas)")

    if falhas:
        print(f"\n  ⚠ {len(falhas)} equipe(s) falharam:")
        for equipe, to, motivo in falhas:
            print(f"    - {equipe} ({to}): {motivo}")

    return count


def _formatar_credenciais(users: list[dict]) -> str:
    return "".join(f"Login: {u['username']}\nSenha: {u['password']}\n\n" for u in users)


def enviar_emails_staff(
    credenciais: list[CredencialEquipe],
    staff_por_sigla: dict[str, list[dict]],
    score_users: list[dict],
    dry_run: bool,
) -> int:
    """
    Envia um email por campus ao coordenador com as credenciais dos usuários
    de staff daquele campus e de todos os usuários de placar (score).
    """
    print("\n── Credenciais de staff e placar para coordenadores")

    if not score_users:
        print("  Aviso: nenhum usuário score encontrado em usuarios.txt")

    linhas_score = _formatar_credenciais(score_users) if score_users else "  (nenhum)\n\n"

    # Deduplica por campus usando o primeiro CredencialEquipe de cada sigla
    por_sigla: dict[str, CredencialEquipe] = {}
    for cred in credenciais:
        if cred.sigla not in por_sigla:
            por_sigla[cred.sigla] = cred

    count = 0
    for sigla, cred in sorted(por_sigla.items()):
        if not cred.coord_email:
            print(f"  Aviso: campus {sigla} sem email de coordenador — pulado")
            continue

        staff_campus = staff_por_sigla.get(sigla, [])
        if not staff_campus:
            print(f"  Aviso: campus {sigla} sem usuário staff em usuarios.txt — email enviado mesmo assim")

        linhas_staff = _formatar_credenciais(staff_campus) if staff_campus else "  (nenhum)\n\n"

        body = STAFF_BODY_TEMPLATE.format(
            nome=cred.primeiro_nome_coord,
            campus=cred.campus,
            linhas_staff=linhas_staff,
            linhas_score=linhas_score,
        )
        send_email(cred.coord_email, STAFF_SUBJECT, body, dry_run=dry_run)
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

    send_email(
        EMAIL_INTERIF,
        f"Resumo de envio de credenciais — {TITULO_EVENTO}",
        "".join(linhas),
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
    fase_group = parser.add_mutually_exclusive_group()
    fase_group.add_argument(
        "-1",
        dest="fase",
        action="store_const",
        const=1,
        default=1,
        help="Fluxo de envio da 1ª fase (padrão)",
    )
    fase_group.add_argument(
        "-2",
        dest="fase",
        action="store_const",
        const=2,
        help="Fluxo de envio da 2ª fase; não envia staff, judge nem score",
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
        "--campus",
        default=None,
        metavar="SIGLA",
        help="Processa apenas o campus informado (sigla, ex.: SPO). Padrão: todos.",
    )
    parser.add_argument(
        "--enviar-staff",
        action="store_true",
        help=(
            "Envia credenciais de staff e placar aos coordenadores de campus. "
            "Pode ser combinado com --so-* ou usado isoladamente."
        ),
    )
    parser.add_argument(
        "--so-coordenadores",
        action="store_true",
        help="Envia apenas aos coordenadores de campus (combinável com as demais --so-*)",
    )
    parser.add_argument(
        "--so-responsaveis",
        action="store_true",
        help="Envia apenas aos responsáveis pelas equipes (combinável com as demais --so-*)",
    )
    parser.add_argument(
        "--so-participantes",
        action="store_true",
        help="Envia apenas aos participantes (combinável com as demais --so-*)",
    )
    parser.add_argument(
        "--pular-enviados",
        default=None,
        metavar="LOG",
        help=(
            "Log de uma execução anterior; equipes cujo destinatário já obteve "
            "'OK: enviado' são puladas (retomada de envio interrompido)"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula o envio sem disparar emails reais",
    )
    return parser.parse_args()


def validar_opcoes(args: argparse.Namespace) -> None:
    if args.enviar_staff and (args.so_coordenadores or args.so_responsaveis or args.so_participantes):
        raise ValueError("--enviar-staff não pode ser combinado com --so-*.")

    if args.fase == 2 and args.enviar_staff:
        raise ValueError(
            "na fase 2, credenciais de staff, judge e score ficam em usuarios.txt, "
            "mas não devem ser enviadas."
        )

    if args.fase == 2 and args.so_coordenadores:
        raise ValueError("na fase 2, as credenciais não devem ser enviadas aos coordenadores locais.")


def grupos_envio(args: argparse.Namespace) -> tuple[bool, bool, bool, bool]:
    """Retorna (coordenadores, responsáveis, participantes, resumo)."""
    seletivo = args.so_coordenadores or args.so_responsaveis or args.so_participantes

    if args.fase == 2:
        if seletivo:
            return False, args.so_responsaveis, args.so_participantes, False
        return False, True, True, False

    if seletivo:
        return args.so_coordenadores, args.so_responsaveis, args.so_participantes, False

    return True, True, True, True


def main() -> None:
    args = parse_args()
    try:
        validar_opcoes(args)
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        sys.exit(1)

    usuarios_path = Path(args.usuarios)
    csv_path = Path(args.csv)
    campi_path = Path(args.campi)

    # Verifica arquivos de entrada
    for p in (usuarios_path, csv_path, campi_path):
        if not p.exists():
            print(f"Erro: arquivo não encontrado: {p}", file=sys.stderr)
            sys.exit(1)

    print("Envio de credenciais - InterIF")
    print(f"Usuários: {usuarios_path.resolve()}")
    print(f"CSV:      {csv_path.resolve()}")
    print(f"Campi:    {campi_path.resolve()}")
    print(f"Fase:     {args.fase}")
    print(f"Modo:     {'dry-run' if args.dry_run else 'envio real'}")
    print()

    campi = load_campi(campi_path)
    teams_csv = load_teams(csv_path)
    usuarios = parse_usuarios(usuarios_path)

    print(f"{len(usuarios)} equipe(s) em usuarios.txt | {len(teams_csv)} linha(s) no CSV.")

    credenciais = enriquecer(usuarios, teams_csv, campi, emit=print)

    # Filtro opcional por campus (sigla)
    if args.campus:
        try:
            credenciais = filtrar_por_sigla(credenciais, args.campus, campi)
        except ValueError as exc:
            print(f"Erro: {exc}", file=sys.stderr)
            sys.exit(1)
        if not credenciais:
            print(f"Nenhuma equipe encontrada para o campus {args.campus.upper()!r}.")
            sys.exit(0)
        print(f"Filtrando apenas o campus {args.campus.upper()!r}: {len(credenciais)} equipe(s).")

    ja_enviados: set[str] = set()
    if args.pular_enviados:
        log_path = Path(args.pular_enviados)
        if not log_path.exists():
            print(f"Erro: log não encontrado: {log_path}", file=sys.stderr)
            sys.exit(1)
        ja_enviados = _enderecos_ja_enviados(log_path)
        print(f"{len(ja_enviados)} destinatário(s) já enviados serão pulados (de {log_path}).")

    if args.enviar_staff:
        staff_por_sigla, score_users = parse_staff_e_score(usuarios_path)
        n_staff = enviar_emails_staff(credenciais, staff_por_sigla, score_users, args.dry_run)
        print()
        render_summary(credenciais, n_staff, dry_run=args.dry_run)
        return

    n_coord = n_tec = n_part = 0
    enviar_coord, enviar_resp, enviar_part, enviar_email_resumo = grupos_envio(args)

    if enviar_coord:
        n_coord = enviar_emails_coordenadores(credenciais, args.dry_run)
    if enviar_resp:
        n_tec = enviar_emails_tecnicos(credenciais, args.dry_run)
    if enviar_part:
        n_part = enviar_emails_participantes(credenciais, args.dry_run, ja_enviados)
    if enviar_email_resumo:
        enviar_resumo(credenciais, n_coord, n_tec, n_part, args.dry_run)

    total_emails = n_coord + n_tec + n_part + (1 if enviar_email_resumo else 0)

    print()
    render_summary(credenciais, total_emails, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
