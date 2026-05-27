#!/usr/bin/env python3
"""
Lê o arquivo equipes_interif.csv, extrai e valida CPFs de responsáveis e
participantes, e exibe uma lista ordenada por campus no formato:

    Campus | Pessoa (Coach / Aluno) | CPF | Situação

Uso:
    uv run python cpf_check.py [ARQUIVO] [--invalidos] [--notificar [--dry-run]] [--output SAIDA.csv]
"""

import argparse
import csv
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cpf as cpflib
from tabulate import tabulate

from config import EMAIL_INTERIF as INTERIF_EMAIL
from config import NOTIFY_BODY, NOTIFY_SUBJECT

CSV_FILE = Path(__file__).parent / "equipes_interif.csv"

# Mapeamento: coluna de CPF → (coluna de nome, coluna de email, papel)
_CPF_COL_MAP: dict[str, tuple[str, str, str]] = {
    "CPF do Responsável pela Equipe": (
        "Nome do Responsável pela Equipe",
        "Email do Responsável pela Equipe",
        "Coach",
    ),
    "CPF Participante 1": ("Nome Participante 1", "Email Participante 1", "Aluno"),
    "CPF Participante 2": ("Nome Participante 2", "Email Participante 2", "Aluno"),
    "CPF Participante 3": ("Nome Participante 3", "Email Participante 3", "Aluno"),
}

# Fallback: regex para detectar CPFs em qualquer campo
_CPF_RE = re.compile(r"\b(\d{3}[.\-]?\d{3}[.\-]?\d{3}[.\-]?\d{2})\b")

# ── Tipos ─────────────────────────────────────────────────────────────────────

@dataclass
class CpfEntry:
    campus:      str
    nome:        str
    email:       str   # endereço da pessoa; pode ser vazio no fallback regex
    papel:       str   # "Coach" ou "Aluno"
    cpf:         str   # dígitos brutos (11 chars)
    valido:      bool
    coord_email: str = field(default="")  # coordenador local do campus

    @property
    def cpf_fmt(self) -> str:
        d = self.cpf
        if len(d) == 11:
            return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
        return d

    @property
    def situacao(self) -> str:
        return "VÁLIDO" if self.valido else "INVÁLIDO"

    @property
    def primeiro_nome(self) -> str:
        return self.nome.strip().split()[0] if self.nome.strip() else self.nome


# ── Helpers ───────────────────────────────────────────────────────────────────

def _digits(value: str) -> str:
    """Extrai apenas os dígitos de um CPF."""
    return re.sub(r"\D", "", value.strip())


def _validate(raw: str) -> bool:
    try:
        return cpflib.validate(_digits(raw))
    except Exception:
        return False


# ── Leitura do CSV ────────────────────────────────────────────────────────────

def load_rows(csv_path: Path) -> tuple[list[str], list[dict]]:
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        rows = [r for r in reader if r.get("Nome da Equipe", "").strip()]
    return headers, rows


# ── Extração de entradas de CPF ───────────────────────────────────────────────

def _extract_mapped(row: dict, present_cpf_cols: list[str]) -> list[CpfEntry]:
    """Extrai CPFs usando o mapeamento coluna → nome + email + papel."""
    entries: list[CpfEntry] = []
    campus = row.get("Campus", "").strip()

    for cpf_col in present_cpf_cols:
        mapping = _CPF_COL_MAP.get(cpf_col)
        if mapping is None:
            continue
        nome_col, email_col, papel = mapping

        cpf_raw = row.get(cpf_col, "").strip()
        if not cpf_raw or not _CPF_RE.search(cpf_raw):
            continue

        digits = _digits(cpf_raw)
        if len(digits) != 11:
            continue

        nome        = row.get(nome_col,  "—").strip() or "—"
        email       = row.get(email_col, "").strip().lower()
        coord_email = row.get("Email do Coordenador do Campus", "").strip().lower()
        entries.append(CpfEntry(
            campus=campus,
            nome=nome,
            email=email,
            papel=papel,
            cpf=digits,
            valido=_validate(digits),
            coord_email=coord_email,
        ))
    return entries


def _extract_regex(row: dict) -> list[CpfEntry]:
    """Fallback: varre todos os campos buscando padrões CPF."""
    entries: list[CpfEntry] = []
    campus = row.get("Campus", "").strip()

    for col, val in row.items():
        if not val:
            continue
        for match in _CPF_RE.finditer(val):
            digits = _digits(match.group(1))
            if len(digits) != 11:
                continue
            entries.append(CpfEntry(
                campus=campus,
                nome=col,   # sem nome real disponível, usa o nome da coluna
                email="",
                papel="—",
                cpf=digits,
                valido=_validate(digits),
            ))
    return entries


def build_entries(headers: list[str], rows: list[dict]) -> tuple[list[CpfEntry], bool]:
    """
    Retorna (lista_de_entradas, usou_mapeamento).
    Ordena por campus → papel (Coach antes de Aluno) → nome.
    Deduplicação por CPF: mantém a primeira ocorrência.
    """
    known_cpf_cols = [c for c in _CPF_COL_MAP if c in headers]
    use_map = bool(known_cpf_cols)

    all_entries: list[CpfEntry] = []
    for row in rows:
        if use_map:
            all_entries.extend(_extract_mapped(row, known_cpf_cols))
        else:
            all_entries.extend(_extract_regex(row))

    papel_order = {"Coach": 0, "Aluno": 1}
    all_entries.sort(key=lambda e: (
        e.campus.lower(),
        papel_order.get(e.papel, 9),
        e.nome.lower(),
    ))

    seen: set[str] = set()
    unique: list[CpfEntry] = []
    for e in all_entries:
        if e.cpf not in seen:
            seen.add(e.cpf)
            unique.append(e)

    return unique, use_map


# ── Envio de notificações ─────────────────────────────────────────────────────

def notify_invalid(entries: list[CpfEntry], dry_run: bool) -> None:
    """Envia email para cada pessoa com CPF inválido que tenha endereço disponível."""
    invalids = [e for e in entries if not e.valido]

    sem_email = [e for e in invalids if not e.email]
    com_email  = [e for e in invalids if e.email]

    print(f"\nNotificações de CPF inválido ({len(invalids)} entrada(s)):\n")

    for entry in com_email:
        body = NOTIFY_BODY.format(
            nome=entry.primeiro_nome,
            cpf=entry.cpf_fmt,
            interif_email=INTERIF_EMAIL,
        )
        # Monta lista de CCs sem duplicatas, preservando a ordem
        cc_list = dict.fromkeys(
            e for e in [INTERIF_EMAIL, entry.coord_email] if e
        )
        cc_str = ",".join(cc_list)

        dest = f"{entry.email} (cc: {cc_str})"
        if dry_run:
            print(f"  -> Para: {dest}")
            print(f"     Assunto: {NOTIFY_SUBJECT}")
            print(body)
            continue

        print(f"  -> Enviando para {dest} ...")
        cmd = [
            "gws", "gmail", "+send",
            "--to",      entry.email,
            "--cc",      cc_str,
            "--subject", NOTIFY_SUBJECT,
            "--body",    body,
        ]
        try:
            subprocess.run(cmd, check=True)
            print("    OK: enviado")
        except subprocess.CalledProcessError as exc:
            print(f"    Erro ao enviar: {exc}")

    if sem_email:
        print()
        print("Aviso: as seguintes entradas não possuem email e não foram notificadas:")
        for e in sem_email:
            print(f"  - {e.nome} ({e.campus}) — CPF {e.cpf_fmt}")


# ── Exibição ──────────────────────────────────────────────────────────────────

def render_table(entries: list[CpfEntry]) -> None:
    rows: list[list[str]] = []
    prev_campus = None
    for e in entries:
        campus_cell = ""
        if e.campus != prev_campus:
            campus_cell = e.campus
            prev_campus = e.campus

        rows.append([campus_cell, e.nome, e.papel, e.cpf_fmt, e.situacao])

    print(tabulate(rows, headers=["Campus", "Pessoa", "Papel", "CPF", "Situação"], tablefmt="simple"))


def render_summary(entries: list[CpfEntry]) -> None:
    total     = len(entries)
    validos   = sum(1 for e in entries if e.valido)
    invalidos = total - validos

    print("Resumo")
    print(tabulate(
        [
            ["Total de CPFs", total],
            ["Válidos", validos],
            ["Inválidos", invalidos],
        ],
        tablefmt="simple",
    ))


# ── Exportação CSV ────────────────────────────────────────────────────────────

def export_csv(entries: list[CpfEntry], dest: Path) -> None:
    with open(dest, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Campus", "Pessoa", "Papel", "CPF", "Situação"])
        for e in entries:
            writer.writerow([e.campus, e.nome, e.papel, e.cpf_fmt, e.situacao])
    print(f"\nExportado para {dest} ({len(entries)} linhas).")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valida CPFs do arquivo equipes_interif.csv, listados por campus."
    )
    parser.add_argument(
        "csv_file",
        nargs="?",
        default=str(CSV_FILE),
        metavar="ARQUIVO",
        help=f"Caminho do CSV de entrada (padrão: {CSV_FILE.name})",
    )
    parser.add_argument(
        "--invalidos", "-i",
        action="store_true",
        help="Exibe apenas os CPFs inválidos",
    )
    parser.add_argument(
        "--notificar", "-n",
        action="store_true",
        help=(
            "Envia email para cada pessoa com CPF inválido pedindo correção "
            f"(cc: {INTERIF_EMAIL})"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra um preview dos emails no terminal sem chamar o gws",
    )
    parser.add_argument(
        "--output", "-o",
        metavar="SAIDA.csv",
        help="Exporta o resultado também como arquivo CSV",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    csv_path = Path(args.csv_file)

    if not csv_path.exists():
        print(f"Erro: arquivo não encontrado: {csv_path}", file=sys.stderr)
        sys.exit(1)

    print("Validador de CPF - InterIF")
    print(f"Arquivo: {csv_path.resolve()}")
    print()

    headers, rows = load_rows(csv_path)
    entries, used_map = build_entries(headers, rows)

    modo = (
        "colunas CPF do cabeçalho"
        if used_map
        else "varredura regex (nenhuma coluna CPF encontrada)"
    )
    filtro = " · filtro: apenas inválidos" if args.invalidos else ""
    print(
        f"{len(rows)} equipe(s) carregada(s) · modo: {modo} · "
        f"{len(entries)} CPF(s) encontrado(s).{filtro}\n"
    )

    if not entries:
        print(
            "Aviso: nenhum CPF encontrado no arquivo.\n"
            'Certifique-se de que o cabeçalho contém a palavra "CPF"\n'
            "ou que os campos contêm sequências de 11 dígitos."
        )
        return

    display_entries = [e for e in entries if not e.valido] if args.invalidos else entries
    render_table(display_entries)
    print()
    render_summary(display_entries)

    if args.output:
        export_csv(display_entries, Path(args.output))

    if args.notificar:
        notify_invalid(entries, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
