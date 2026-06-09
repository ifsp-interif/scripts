#!/usr/bin/env python3
import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path


def mask_cpf(raw: str) -> str:
    d = re.sub(r"\D", "", raw)
    if len(d) == 11:
        return f"***.***.{d[6:9]}-{d[9:]}"
    return raw


def fmt_datetime(raw: str) -> str:
    raw = raw.strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass
    return raw


def pessoa(nome: str, cpf: str) -> str:
    nome = nome.strip()
    cpf = cpf.strip()
    if not nome and not cpf:
        return "—"
    cpf_fmt = mask_cpf(cpf) if cpf else ""
    if nome and cpf_fmt:
        return f"{nome} ({cpf_fmt})"
    return nome or cpf_fmt


def build_html(rows: list[dict]) -> str:
    headers = [
        "Campus",
        "Equipe",
        "Inscrição",
        "Coach",
        "Participante 1",
        "Participante 2",
        "Participante 3",
    ]
    lines = ["<table>", "<tr>"]
    for h in headers:
        lines.append(f"<th>{h}</th>")
    lines.append("</tr>")

    for r in rows:
        lines.append("<tr>")
        lines.append(f"<td>{r['Campus'].strip()}</td>")
        lines.append(f"<td>{r['Nome da Equipe'].strip()}</td>")
        lines.append(f"<td>{fmt_datetime(r['Carimbo de data/hora'])}</td>")
        lines.append(f"<td>{pessoa(r['Nome do Responsável pela Equipe'], r['CPF do Responsável pela Equipe'])}</td>")
        lines.append(f"<td>{pessoa(r['Nome Participante 1'], r['CPF Participante 1'])}</td>")
        lines.append(f"<td>{pessoa(r['Nome Participante 2'], r['CPF Participante 2'])}</td>")
        lines.append(f"<td>{pessoa(r['Nome Participante 3'], r['CPF Participante 3'])}</td>")
        lines.append("</tr>")

    lines.append("</table>")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera tabela HTML das equipes inscritas no InterIF")
    parser.add_argument("-i", "--input", default="equipes_interif.csv", help="CSV de entrada (default: equipes_interif.csv)")
    parser.add_argument("-o", "--output", default="equipes.html", help="Arquivo HTML de saída (default: equipes.html)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Erro: arquivo '{input_path}' não encontrado.", file=sys.stderr)
        sys.exit(1)

    with open(input_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if r.get("Nome da Equipe", "").strip()]

    rows.sort(key=lambda r: (r["Campus"].strip(), r["Nome da Equipe"].strip()))

    html = build_html(rows)
    Path(args.output).write_text(html, encoding="utf-8")
    print(f"{len(rows)} equipes exportadas para '{args.output}'.")


if __name__ == "__main__":
    main()
