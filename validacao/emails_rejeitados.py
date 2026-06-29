#!/usr/bin/env python3
"""
Coleta os bounces (Notificações de falha de entrega) na caixa do Gmail e cruza
os endereços rejeitados com os contatos de equipes_interif.csv.

Cada notificação do Gmail (`mailer-daemon`, "Delivery Status Notification (Failure)")
traz o endereço que não existe no cabeçalho `X-Failed-Recipients` — normalmente um
erro `550 5.1.1 ... does not exist`. O script junta esses endereços, mapeia cada um
para o contato correspondente no CSV (coordenador, responsável ou participante) e
gera um relatório dos e-mails problemáticos.

Requer o `gws` autenticado (mesmo padrão dos demais scripts InterIF).

Uso:
    uv run python emails_rejeitados.py
    uv run python emails_rejeitados.py -i equipes_interif.csv -o emails_rejeitados.csv
    uv run python emails_rejeitados.py --query "from:mailer-daemon newer_than:30d"
"""

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tabulate import tabulate

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from interif_core import CSV_FILE, load_teams  # noqa: E402

_OUTPUT_CSV = ROOT_DIR / "emails_rejeitados.csv"

# Notificações de falha do Gmail (mailer-daemon).
_QUERY_PADRAO = "from:mailer-daemon subject:(Delivery Status Notification Failure)"

_PAPEIS = [
    ("Coordenador", "coord_nome", "coord_email"),
    ("Responsável", "resp_nome", "resp_email"),
    ("Participante 1", "part_1_nome", "part_1_email"),
    ("Participante 2", "part_2_nome", "part_2_email"),
    ("Participante 3", "part_3_nome", "part_3_email"),
]


@dataclass
class Rejeitado:
    campus: str
    equipe: str
    papel: str
    nome: str
    email: str
    data_bounce: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lista e-mails rejeitados (bounces) e o contato correspondente no CSV."
    )
    parser.add_argument(
        "--input",
        "-i",
        metavar="ARQUIVO",
        default=str(CSV_FILE),
        help=f"CSV de equipes inscritas (padrão: {CSV_FILE.name})",
    )
    parser.add_argument(
        "--output",
        "-o",
        metavar="ARQUIVO",
        default=str(_OUTPUT_CSV),
        help=f"CSV de saída com os e-mails rejeitados (padrão: {_OUTPUT_CSV.name})",
    )
    parser.add_argument(
        "--query",
        "-q",
        metavar="QUERY",
        default=_QUERY_PADRAO,
        help="Filtro de busca do Gmail para as notificações de falha",
    )
    return parser.parse_args()


# ── Gmail via gws ─────────────────────────────────────────────────────────────


def _gws_json(args: list[str]) -> dict:
    """Executa um comando gws e devolve o JSON do stdout."""
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return json.loads(result.stdout or "{}")


def listar_bounces(query: str) -> list[str]:
    """Devolve os IDs de todas as mensagens de falha (com paginação)."""
    ids: list[str] = []
    page_token: str | None = None
    while True:
        params = {"userId": "me", "q": query, "maxResults": 500}
        if page_token:
            params["pageToken"] = page_token
        data = _gws_json(
            [
                "gws", "gmail", "users", "messages", "list",
                "--params", json.dumps(params),
                "--format", "json",
            ]
        )
        ids.extend(m["id"] for m in data.get("messages", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return ids


def destinatarios_rejeitados(msg_id: str) -> tuple[list[str], str]:
    """Extrai (emails rejeitados, data) de uma notificação de falha."""
    data = _gws_json(
        [
            "gws", "gmail", "users", "messages", "get",
            "--params", json.dumps(
                {
                    "userId": "me",
                    "id": msg_id,
                    "format": "metadata",
                    "metadataHeaders": ["X-Failed-Recipients", "Date"],
                }
            ),
            "--format", "json",
        ]
    )
    headers = {
        h["name"].lower(): h["value"] for h in data.get("payload", {}).get("headers", [])
    }
    raw = headers.get("x-failed-recipients", "")
    emails = [e.strip().lower() for e in raw.split(",") if e.strip()]
    return emails, headers.get("date", "")


# ── Cruzamento com o CSV ──────────────────────────────────────────────────────


def indexar_contatos(teams: list[dict]) -> dict[str, list[tuple[str, str, str, str]]]:
    """email → [(campus, equipe, papel, nome), ...] a partir das equipes."""
    idx: dict[str, list[tuple[str, str, str, str]]] = {}
    for t in teams:
        for papel, campo_nome, campo_email in _PAPEIS:
            email = t.get(campo_email, "").strip().lower()
            if email:
                idx.setdefault(email, []).append(
                    (t["campus"], t["nome_equipe"], papel, t.get(campo_nome, "").strip())
                )
    return idx


def render_report(
    rejeitados: list[Rejeitado], fora_do_csv: list[tuple[str, str]], input_path: Path
) -> str:
    lines = [
        "E-mails rejeitados (bounces) — InterIF",
        f"Arquivo equipes: {input_path.resolve()}",
        f"Endereços rejeitados mapeados no CSV: {len(rejeitados)}",
        f"Endereços rejeitados fora do CSV:     {len(fora_do_csv)}",
        "",
    ]

    rejeitados.sort(key=lambda r: (r.campus.lower(), r.equipe.lower(), r.papel))
    rows: list[list[str]] = []
    prev_campus = None
    for r in rejeitados:
        campus_cell = ""
        if r.campus != prev_campus:
            campus_cell = r.campus
            prev_campus = r.campus
        rows.append([campus_cell, r.equipe, r.papel, r.nome, r.email])

    if rows:
        headers = ["Campus", "Equipe", "Papel", "Nome", "E-mail rejeitado"]
        lines.append(tabulate(rows, headers=headers, tablefmt="simple"))
    else:
        lines.append("(nenhum endereço rejeitado mapeado no CSV)")

    if fora_do_csv:
        lines.append("")
        lines.append("Endereços rejeitados que NÃO estão no CSV (verifique manualmente):")
        for email, _data in sorted(fora_do_csv):
            lines.append(f"  {email}")

    return "\n".join(lines)


def salvar_csv(
    rejeitados: list[Rejeitado], fora_do_csv: list[tuple[str, str]], out_path: Path
) -> None:
    campos = ["campus", "equipe", "papel", "nome", "email", "data_bounce", "no_csv"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        for r in rejeitados:
            writer.writerow(
                {
                    "campus": r.campus,
                    "equipe": r.equipe,
                    "papel": r.papel,
                    "nome": r.nome,
                    "email": r.email,
                    "data_bounce": r.data_bounce,
                    "no_csv": "",
                }
            )
        for email, data in sorted(fora_do_csv):
            writer.writerow(
                {
                    "campus": "",
                    "equipe": "",
                    "papel": "",
                    "nome": "",
                    "email": email,
                    "data_bounce": data,
                    "no_csv": "sim",
                }
            )


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Erro: arquivo não encontrado: {input_path}", file=sys.stderr)
        sys.exit(1)

    teams = load_teams(input_path)
    idx = indexar_contatos(teams)

    print(f"Buscando notificações de falha ({args.query!r})...", file=sys.stderr)
    try:
        ids = listar_bounces(args.query)
    except subprocess.CalledProcessError as exc:
        print(f"Erro ao consultar o Gmail: {(exc.stderr or '').strip()}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(ids)} notificações encontradas", file=sys.stderr)

    # email → data do bounce (primeira ocorrência mantida)
    falhos: dict[str, str] = {}
    sem_header = 0
    for i, mid in enumerate(ids, 1):
        try:
            emails, data = destinatarios_rejeitados(mid)
        except subprocess.CalledProcessError:
            print(f"  Aviso: falha ao ler mensagem {mid}", file=sys.stderr)
            continue
        if not emails:
            sem_header += 1
        for e in emails:
            falhos.setdefault(e, data)
        print(f"  [{i}/{len(ids)}]", end="\r", file=sys.stderr)
    print(file=sys.stderr)

    rejeitados: list[Rejeitado] = []
    fora_do_csv: list[tuple[str, str]] = []
    for email, data in falhos.items():
        matches = idx.get(email)
        if not matches:
            fora_do_csv.append((email, data))
            continue
        for campus, equipe, papel, nome in matches:
            rejeitados.append(Rejeitado(campus, equipe, papel, nome, email, data))

    report = render_report(rejeitados, fora_do_csv, input_path)
    print()
    print(report)

    salvar_csv(rejeitados, fora_do_csv, output_path)
    print(f"\nCSV salvo em {output_path}")

    if sem_header:
        print(
            f"(Aviso: {sem_header} notificação(ões) sem X-Failed-Recipients — "
            "possivelmente outro tipo de falha.)",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
