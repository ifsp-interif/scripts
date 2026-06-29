#!/usr/bin/env python3
import argparse
import csv
import re
import sys
from pathlib import Path


ORDEM_CRITERIOS = ["Critério I", "Critério II", "Critério III", "Critério IV"]


def criterio_key(raw: str) -> tuple[int, str]:
    raw = raw.strip()
    try:
        return (ORDEM_CRITERIOS.index(raw), raw)
    except ValueError:
        return (len(ORDEM_CRITERIOS), raw)


def classificacao_key(raw: str) -> tuple[int, str]:
    raw = raw.strip()
    m = re.search(r"\d+", raw)
    return (int(m.group()) if m else 10**9, raw)


def mask_name(name: str) -> str:
    parts = name.split()
    if len(parts) <= 1:
        return name
    return parts[0] + " " + " ".join(f"{p[0]}." for p in parts[1:])


def participantes(r: dict) -> str:
    nomes = []
    for col in ("Nome Participante 1", "Nome Participante 2", "Nome Participante 3"):
        nome = r.get(col, "").strip()
        if nome:
            nomes.append(mask_name(nome))
    return "<br>".join(nomes) if nomes else "—"


def build_html(rows: list[dict]) -> str:
    headers = [
        "Critério",
        "Nome da equipe",
        "Campus",
        "Participantes",
        "Classificação na primeira fase",
    ]
    lines = ["<table>", "<tr>"]
    for h in headers:
        lines.append(f"<th>{h}</th>")
    lines.append("</tr>")

    for r in rows:
        lines.append("<tr>")
        lines.append(f"<td>{r.get('Critério', '').strip()}</td>")
        lines.append(f"<td>{r.get('Nome da Equipe', '').strip()}</td>")
        lines.append(f"<td>{r.get('Campus', '').strip()}</td>")
        lines.append(f"<td>{participantes(r)}</td>")
        lines.append(f"<td>{r.get('Classificação', '').strip()}</td>")
        lines.append("</tr>")

    lines.append("</table>")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera tabela HTML das equipes classificadas para a fase final do InterIF")
    parser.add_argument("-i", "--input", default="equipes_final.csv", help="CSV de entrada (default: equipes_final.csv)")
    parser.add_argument("-o", "--output", default="equipes_final.html", help="Arquivo HTML de saída (default: equipes_final.html)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Erro: arquivo '{input_path}' não encontrado.", file=sys.stderr)
        sys.exit(1)

    with open(input_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if r.get("Nome da Equipe", "").strip()]

    rows.sort(key=lambda r: (criterio_key(r.get("Critério", "")), classificacao_key(r.get("Classificação", ""))))

    html = build_html(rows)
    Path(args.output).write_text(html, encoding="utf-8")
    print(f"{len(rows)} equipes exportadas para '{args.output}'.")


if __name__ == "__main__":
    main()
