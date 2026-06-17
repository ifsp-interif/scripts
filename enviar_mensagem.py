#!/usr/bin/env python3
"""
Mala direta com template Jinja2 para coordenadores de campus, coaches e/ou participantes.

Uso básico:
    enviar_mensagem.py TEMPLATE --assunto "Olá, {{ campus }}!" --coordenadores [--dry-run]

Variáveis disponíveis no template:
    nome               Primeiro nome do destinatário
    campus             Campus do destinatário
    evento             Nome do evento (config.TITULO_EVENTO)
    email_organizacao  Email da organização (config.EMAIL_INTERIF)
    total_equipes      Número de equipes no contexto
    total_participantes Número total de participantes no contexto
    coord_nome         Nome completo do coordenador (--coordenadores); "" nos demais modos
    coach              Nome do coach (--coaches e --participantes); "" em --coordenadores
    equipe             Nome da equipe (--participantes); "" nos demais modos
    equipes            Lista de equipes (dicts com nome/campus/coach/participantes/totais)
    participantes      Lista de dicts {nome, email} dos participantes do contexto
"""

import argparse
import signal
import sys
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, StrictUndefined, TemplateError

from config import EMAIL_INTERIF, TITULO_EVENTO
from email_utils import send_email
from interif_core import CSV_FILE, load_teams

# ── Helpers ───────────────────────────────────────────────────────────────────


def first_name(full: str) -> str:
    return full.strip().split()[0] if full.strip() else full


def build_team_ctx(t: dict) -> dict:
    """Converte um dict bruto de equipe no dict de contexto Jinja2."""
    participantes = [
        {"nome": t[f"part_{i}_nome"], "email": t[f"part_{i}_email"]}
        for i in range(1, 4)
        if t.get(f"part_{i}_nome", "").strip()
    ]
    return {
        "nome": t["nome_equipe"],
        "campus": t["campus"],
        "coach": t["resp_nome"],
        "coach_email": t["resp_email"],
        "participantes": participantes,
        "total_participantes": len(participantes),
    }


def _all_participantes(equipes_ctx: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for eq in equipes_ctx:
        for p in eq["participantes"]:
            key = p["email"] or p["nome"]
            if key and key not in seen:
                seen.add(key)
                result.append(p)
    return result


# ── Agrupamento ───────────────────────────────────────────────────────────────


def group_for_coord(teams: list[dict]) -> dict[str, dict]:
    """Agrupa equipes por coordenador de campus (keyed by coord_email)."""
    grupos: dict[str, dict] = defaultdict(lambda: {"coord_nome": "", "campus": "", "equipes": []})
    for t in teams:
        g = grupos[t["coord_email"]]
        g["coord_nome"] = t["coord_nome"]
        g["campus"] = t["campus"]
        g["equipes"].append(build_team_ctx(t))
    return dict(grupos)


def group_for_coach(teams: list[dict]) -> dict[str, dict]:
    """Agrupa equipes por coach/responsável (keyed by resp_email)."""
    grupos: dict[str, dict] = defaultdict(lambda: {"coach": "", "campus": "", "equipes": []})
    for t in teams:
        g = grupos[t["resp_email"]]
        g["coach"] = t["resp_nome"]
        # campus: usa o primeiro campus registrado para o coach
        if not g["campus"]:
            g["campus"] = t["campus"]
        g["equipes"].append(build_team_ctx(t))
    return dict(grupos)


def iter_participantes(teams: list[dict]):
    """Gera (email, ctx) para cada participante individual."""
    for t in teams:
        eq_ctx = build_team_ctx(t)
        for i in range(1, 4):
            nome = t.get(f"part_{i}_nome", "").strip()
            email = t.get(f"part_{i}_email", "").strip()
            if not nome:
                continue
            ctx = {
                "nome": first_name(nome),
                "campus": t["campus"],
                "evento": TITULO_EVENTO,
                "email_organizacao": EMAIL_INTERIF,
                "coord_nome": t.get("coord_nome", ""),
                "coach": t["resp_nome"],
                "equipe": t["nome_equipe"],
                "equipes": [eq_ctx],
                "participantes": eq_ctx["participantes"],
                "total_equipes": 1,
                "total_participantes": eq_ctx["total_participantes"],
            }
            yield email, ctx


# ── Renderização ──────────────────────────────────────────────────────────────


def make_env() -> Environment:
    return Environment(undefined=StrictUndefined, keep_trailing_newline=True)


def render(tmpl, subj_tmpl, ctx: dict) -> tuple[str, str]:
    """Renderiza template e assunto; retorna (assunto, corpo)."""
    return subj_tmpl.render(ctx), tmpl.render(ctx)


# ── Envio por grupo ───────────────────────────────────────────────────────────


def send_coord_group(
    grupos: dict[str, dict],
    tmpl,
    subj_tmpl,
    cc: str | None,
    dry_run: bool,
    attach: Path | None = None,
) -> tuple[int, int]:
    print("\n=== Emails para coordenadores de campus ===")
    sent = skipped = 0
    for email, data in grupos.items():
        if not email:
            print(f"  Aviso: coordenador do campus {data['campus']!r} sem email — ignorado")
            skipped += 1
            continue
        equipes = data["equipes"]
        all_parts = _all_participantes(equipes)
        ctx = {
            "nome": first_name(data["coord_nome"]),
            "campus": data["campus"],
            "evento": TITULO_EVENTO,
            "email_organizacao": EMAIL_INTERIF,
            "coord_nome": data["coord_nome"],
            "coach": "",
            "equipe": "",
            "equipes": equipes,
            "participantes": all_parts,
            "total_equipes": len(equipes),
            "total_participantes": len(all_parts),
        }
        try:
            assunto, corpo = render(tmpl, subj_tmpl, ctx)
        except TemplateError as exc:
            print(f"  Erro ao renderizar template para {email}: {exc}", file=sys.stderr)
            skipped += 1
            continue
        send_email(email, assunto, corpo, cc=cc, attach=attach, dry_run=dry_run)
        sent += 1
    return sent, skipped


def send_coach_group(
    grupos: dict[str, dict],
    tmpl,
    subj_tmpl,
    cc: str | None,
    dry_run: bool,
    attach: Path | None = None,
) -> tuple[int, int]:
    print("\n=== Emails para coaches (responsáveis) ===")
    sent = skipped = 0
    for email, data in grupos.items():
        if not email:
            print(f"  Aviso: coach {data['coach']!r} sem email — ignorado")
            skipped += 1
            continue
        equipes = data["equipes"]
        all_parts = _all_participantes(equipes)
        ctx = {
            "nome": first_name(data["coach"]),
            "campus": data["campus"],
            "evento": TITULO_EVENTO,
            "email_organizacao": EMAIL_INTERIF,
            "coord_nome": "",
            "coach": data["coach"],
            "equipe": "",
            "equipes": equipes,
            "participantes": all_parts,
            "total_equipes": len(equipes),
            "total_participantes": len(all_parts),
        }
        try:
            assunto, corpo = render(tmpl, subj_tmpl, ctx)
        except TemplateError as exc:
            print(f"  Erro ao renderizar template para {email}: {exc}", file=sys.stderr)
            skipped += 1
            continue
        send_email(email, assunto, corpo, cc=cc, attach=attach, dry_run=dry_run)
        sent += 1
    return sent, skipped


def send_participantes_group(
    teams: list[dict],
    tmpl,
    subj_tmpl,
    cc: str | None,
    dry_run: bool,
    *,
    por_equipe: bool = False,
    attach: Path | None = None,
) -> tuple[int, int]:
    if por_equipe:
        return _send_participantes_por_equipe(teams, tmpl, subj_tmpl, cc, dry_run, attach=attach)
    print("\n=== Emails para participantes (individual) ===")
    sent = skipped = 0
    for email, ctx in iter_participantes(teams):
        if not email:
            print(f"  Aviso: participante {ctx['nome']!r} (equipe {ctx['equipe']!r}) sem email — ignorado")
            skipped += 1
            continue
        try:
            assunto, corpo = render(tmpl, subj_tmpl, ctx)
        except TemplateError as exc:
            print(f"  Erro ao renderizar template para {email}: {exc}", file=sys.stderr)
            skipped += 1
            continue
        send_email(email, assunto, corpo, cc=cc, attach=attach, dry_run=dry_run)
        sent += 1
    return sent, skipped


def _send_participantes_por_equipe(
    teams: list[dict],
    tmpl,
    subj_tmpl,
    cc: str | None,
    dry_run: bool,
    attach: Path | None = None,
) -> tuple[int, int]:
    print("\n=== Emails para participantes (por equipe) ===")
    sent = skipped = 0
    for t in teams:
        eq_ctx = build_team_ctx(t)
        emails = [p["email"] for p in eq_ctx["participantes"] if p["email"]]
        if not emails:
            print(f"  Aviso: equipe {t['nome_equipe']!r} sem emails de participantes — ignorada")
            skipped += 1
            continue
        ctx = {
            "nome": t["nome_equipe"],
            "campus": t["campus"],
            "evento": TITULO_EVENTO,
            "email_organizacao": EMAIL_INTERIF,
            "coord_nome": t.get("coord_nome", ""),
            "coach": t["resp_nome"],
            "equipe": t["nome_equipe"],
            "equipes": [eq_ctx],
            "participantes": eq_ctx["participantes"],
            "total_equipes": 1,
            "total_participantes": eq_ctx["total_participantes"],
        }
        try:
            assunto, corpo = render(tmpl, subj_tmpl, ctx)
        except TemplateError as exc:
            print(f"  Erro ao renderizar template para equipe {t['nome_equipe']!r}: {exc}", file=sys.stderr)
            skipped += 1
            continue
        # primeiro participante em "to"; demais em cc junto com o cc externo
        to = emails[0]
        equipe_cc = ", ".join(emails[1:]) if len(emails) > 1 else None
        combined_cc = ", ".join(filter(None, [equipe_cc, cc])) or None
        send_email(to, assunto, corpo, cc=combined_cc, attach=attach, dry_run=dry_run)
        sent += 1
    return sent, skipped


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mala direta com template Jinja2 para coordenadores, coaches e/ou participantes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "template",
        metavar="TEMPLATE",
        help="Caminho do arquivo de template Jinja2",
    )
    parser.add_argument(
        "--assunto",
        required=True,
        metavar="TEXTO",
        help="Assunto do email (suporta Jinja2, ex: 'Equipes de {{ campus }}')",
    )
    parser.add_argument(
        "--coordenadores",
        action="store_true",
        help="Envia um email por coordenador de campus",
    )
    parser.add_argument(
        "--coaches",
        action="store_true",
        help="Envia um email por coach (responsável pela equipe)",
    )
    parser.add_argument(
        "--participantes",
        action="store_true",
        help="Envia um email por participante individual",
    )
    parser.add_argument(
        "--por-equipe",
        action="store_true",
        help=(
            "Usado com --participantes: envia um email por equipe "
            "(primeiro participante em 'para', demais em cópia)"
        ),
    )
    parser.add_argument(
        "--csv",
        default=str(CSV_FILE),
        metavar="ARQUIVO",
        help=f"Caminho do CSV de equipes (padrão: {CSV_FILE.name})",
    )
    parser.add_argument(
        "--cc",
        metavar="EMAIL",
        help="CC opcional para todos os envios",
    )
    parser.add_argument(
        "--anexo",
        metavar="ARQUIVO",
        help="Caminho de um arquivo a ser anexado a todos os envios",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula o envio sem disparar emails",
    )
    return parser.parse_args()


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    # Encerra silenciosamente se a saída for cortada por um pager (ex.: | bat, | less, | head).
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    args = parse_args()

    if not (args.coordenadores or args.coaches or args.participantes):
        print(
            "Erro: especifique pelo menos uma audiência: --coordenadores, --coaches ou --participantes.",
            file=sys.stderr,
        )
        sys.exit(1)

    template_path = Path(args.template)
    if not template_path.exists():
        print(f"Erro: arquivo de template não encontrado: {template_path}", file=sys.stderr)
        sys.exit(1)

    anexo: Path | None = None
    if args.anexo:
        anexo = Path(args.anexo)
        if not anexo.is_file():
            print(f"Erro: arquivo de anexo não encontrado: {anexo}", file=sys.stderr)
            sys.exit(1)

    env = make_env()
    try:
        tmpl = env.from_string(template_path.read_text(encoding="utf-8"))
        subj_tmpl = env.from_string(args.assunto)
    except TemplateError as exc:
        print(f"Erro ao compilar template: {exc}", file=sys.stderr)
        sys.exit(1)

    teams = load_teams(Path(args.csv))
    print(f"Carregadas {len(teams)} equipe(s) de '{args.csv}'.")

    totais: list[str] = []

    if args.coordenadores:
        grupos = group_for_coord(teams)
        s, sk = send_coord_group(grupos, tmpl, subj_tmpl, args.cc, args.dry_run, attach=anexo)
        totais.append(f"{s} coordenador(es) ({sk} ignorado(s))")

    if args.coaches:
        grupos = group_for_coach(teams)
        s, sk = send_coach_group(grupos, tmpl, subj_tmpl, args.cc, args.dry_run, attach=anexo)
        totais.append(f"{s} coach(es) ({sk} ignorado(s))")

    if args.participantes:
        s, sk = send_participantes_group(
            teams, tmpl, subj_tmpl, args.cc, args.dry_run, por_equipe=args.por_equipe, attach=anexo
        )
        modo = "equipe(s)" if args.por_equipe else "participante(s)"
        totais.append(f"{s} {modo} ({sk} ignorado(s))")

    print("\nPronto! Emails enviados para: " + ", ".join(totais) + ".")


if __name__ == "__main__":
    main()
