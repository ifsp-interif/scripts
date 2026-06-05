#!/usr/bin/env python3
"""
Detecta participantes inscritos em mais de uma equipe, usando email e CPF como
critérios de identificação, e notifica todos os envolvidos por email.

Uso:
    uv run python duplicatas_participantes.py [ARQUIVO] [--notificar [--dry-run]]
"""

import argparse
import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from tabulate import tabulate

from config import DUPLICATA_BODY, DUPLICATA_SUBJECT, EMAIL_INTERIF, TITULO_EVENTO
from email_utils import send_email

CSV_FILE = Path(__file__).parent / "equipes_interif.csv"

_CPF_RE = re.compile(r"\b(\d{3}[.\-]?\d{3}[.\-]?\d{3}[.\-]?\d{2})\b")

# ── Tipos ─────────────────────────────────────────────────────────────────────


@dataclass
class Ocorrencia:
    """Registro de um participante em uma equipe específica."""

    nome: str
    email: str
    cpf: str  # dígitos brutos (11 chars) ou "" se ausente
    papel: str  # "Coach" ou "Participante N"
    equipe: str
    campus: str
    coord_email: str
    coach_nome: str
    coach_email: str


@dataclass
class Conflito:
    """Participante encontrado em múltiplas equipes."""

    nome: str
    criterio: str  # "e-mail", "CPF" ou "e-mail e CPF"
    chave_email: str  # email normalizado que causou o conflito (pode ser "")
    chave_cpf: str  # CPF (dígitos) que causou o conflito (pode ser "")
    ocorrencias: list[Ocorrencia] = field(default_factory=list)

    @property
    def primeiro_nome(self) -> str:
        return self.nome.strip().split()[0] if self.nome.strip() else self.nome

    @property
    def cpf_fmt(self) -> str:
        d = self.chave_cpf
        if len(d) == 11:
            return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
        return d


# ── Helpers ───────────────────────────────────────────────────────────────────


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value.strip())


def _norm_email(email: str) -> str:
    return email.strip().lower()


def _cpf_from_raw(raw: str) -> str:
    """Extrai dígitos de um CPF; retorna "" se não encontrar 11 dígitos."""
    m = _CPF_RE.search(raw)
    if not m:
        return ""
    d = _digits(m.group(1))
    return d if len(d) == 11 else ""


# ── Leitura do CSV ────────────────────────────────────────────────────────────


def load_ocorrencias(csv_path: Path) -> list[Ocorrencia]:
    """Extrai todos os participantes (coach + até 3 alunos) de cada equipe."""
    ocorrencias: list[Ocorrencia] = []

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            equipe = row.get("Nome da Equipe", "").strip()
            campus = row.get("Campus", "").strip()
            if not equipe or not campus:
                continue

            coord_email = _norm_email(row.get("Email do Coordenador do Campus", ""))
            coach_nome = row.get("Nome do Responsável pela Equipe", "").strip()
            coach_email = _norm_email(row.get("Email do Responsável pela Equipe", ""))

            # Participantes 1–3  (coach pode estar em múltiplas equipes — não verificado)
            for i in range(1, 4):
                nome = row.get(f"Nome Participante {i}", "").strip()
                email = _norm_email(row.get(f"Email Participante {i}", ""))
                cpf = _cpf_from_raw(row.get(f"CPF Participante {i}", ""))
                if not nome and not email:
                    continue
                if nome in ("--", "-"):
                    continue
                ocorrencias.append(
                    Ocorrencia(
                        nome=nome,
                        email=email,
                        cpf=cpf,
                        papel=f"Participante {i}",
                        equipe=equipe,
                        campus=campus,
                        coord_email=coord_email,
                        coach_nome=coach_nome,
                        coach_email=coach_email,
                    )
                )

    return ocorrencias


# ── Detecção de conflitos ─────────────────────────────────────────────────────


def _conflitos_por_chave(
    ocorrencias: list[Ocorrencia],
    *,
    por_email: bool,
) -> dict[str, list[Ocorrencia]]:
    """
    Agrupa ocorrências pela chave (email ou CPF) e retorna apenas os grupos com
    mais de uma equipe distinta.
    """
    index: dict[str, list[Ocorrencia]] = defaultdict(list)
    for oc in ocorrencias:
        chave = oc.email if por_email else oc.cpf
        if not chave:
            continue
        index[chave].append(oc)

    return {
        chave: ocs
        for chave, ocs in index.items()
        if len({oc.equipe for oc in ocs}) > 1
    }


def detectar_conflitos(ocorrencias: list[Ocorrencia]) -> list[Conflito]:
    """
    Detecta participantes presentes em mais de uma equipe por email ou CPF.
    Mescla os dois critérios: se o mesmo participante for encontrado pelos dois,
    gera um único Conflito com criterio='e-mail e CPF'.
    """
    por_email = _conflitos_por_chave(ocorrencias, por_email=True)
    por_cpf = _conflitos_por_chave(ocorrencias, por_email=False)

    conflitos: dict[str, Conflito] = {}

    for email, ocs in por_email.items():
        nome = next((oc.nome for oc in ocs if oc.nome), email)
        conflitos[email] = Conflito(
            nome=nome,
            criterio="e-mail",
            chave_email=email,
            chave_cpf="",
            ocorrencias=ocs,
        )

    for cpf, ocs in por_cpf.items():
        nome = next((oc.nome for oc in ocs if oc.nome), cpf)
        # Verifica se já existe conflito por email para este cpf
        email_existente = next((oc.email for oc in ocs if oc.email in conflitos), None)
        if email_existente:
            c = conflitos[email_existente]
            c.chave_cpf = cpf
            c.criterio = "e-mail e CPF"
            # Adiciona ocorrências não duplicadas
            equipes_existentes = {oc.equipe for oc in c.ocorrencias}
            for oc in ocs:
                if oc.equipe not in equipes_existentes:
                    c.ocorrencias.append(oc)
                    equipes_existentes.add(oc.equipe)
        else:
            # Conflito detectado apenas por CPF; usa chave sintética para não colidir
            conflitos[f"cpf:{cpf}"] = Conflito(
                nome=nome,
                criterio="CPF",
                chave_email="",
                chave_cpf=cpf,
                ocorrencias=ocs,
            )

    return sorted(conflitos.values(), key=lambda c: (c.ocorrencias[0].campus, c.nome))


# ── Formatação ────────────────────────────────────────────────────────────────


def _detalhe_equipes(conflito: Conflito) -> str:
    linhas: list[str] = []
    for oc in conflito.ocorrencias:
        linhas.append(
            f"  - Campus : {oc.campus}\n"
            f"    Equipe : {oc.equipe}\n"
            f"    Papel  : {oc.papel}\n"
            f"    Coach  : {oc.coach_nome} <{oc.coach_email}>"
        )
    return "\n\n".join(linhas)


def render_table(conflitos: list[Conflito]) -> None:
    rows: list[list[str]] = []
    for c in conflitos:
        equipes = ", ".join(oc.equipe for oc in c.ocorrencias)
        ident = c.chave_email or c.cpf_fmt
        rows.append([c.nome, ident, c.criterio, equipes])

    print(
        tabulate(
            rows,
            headers=["Participante", "Identificador", "Critério", "Equipes"],
            tablefmt="simple",
        )
    )


# ── Envio de notificações ─────────────────────────────────────────────────────


def _destinatarios(conflito: Conflito) -> tuple[str, str]:
    """
    Retorna (to, cc):
      to = EMAIL_INTERIF
      cc = aluno, coaches de todas as equipes, coordenadores locais (sem duplicatas)
    """
    cc_set: dict[str, None] = {}  # preserva ordem, elimina duplicatas

    if conflito.chave_email:
        cc_set[conflito.chave_email] = None

    for oc in conflito.ocorrencias:
        if oc.coach_email:
            cc_set[oc.coach_email] = None
        if oc.coord_email:
            cc_set[oc.coord_email] = None

    # Remove o interif do CC (já é o TO)
    cc_set.pop(EMAIL_INTERIF, None)

    return EMAIL_INTERIF, ",".join(cc_set)


def notificar(conflitos: list[Conflito], dry_run: bool) -> None:
    print(f"\n=== Notificações de participante em múltiplas equipes ({len(conflitos)}) ===\n")

    for c in conflitos:
        detalhe = _detalhe_equipes(c)
        criterio_desc = c.criterio
        if c.chave_email and c.chave_cpf:
            criterio_desc = f"e-mail ({c.chave_email}) e CPF ({c.cpf_fmt})"
        elif c.chave_email:
            criterio_desc = f"e-mail ({c.chave_email})"
        else:
            criterio_desc = f"CPF ({c.cpf_fmt})"

        body = DUPLICATA_BODY.format(
            nome=c.nome,
            criterio=criterio_desc,
            equipes_detalhe=detalhe,
        )
        to, cc = _destinatarios(c)
        send_email(to, DUPLICATA_SUBJECT, body, cc=cc or None, dry_run=dry_run)


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Detecta participantes inscritos em mais de uma equipe "
            f"(verifica por e-mail e por CPF) no {TITULO_EVENTO}."
        )
    )
    parser.add_argument(
        "csv_file",
        nargs="?",
        default=str(CSV_FILE),
        metavar="ARQUIVO",
        help=f"Caminho do CSV de entrada (padrão: {CSV_FILE.name})",
    )
    parser.add_argument(
        "--notificar",
        "-n",
        action="store_true",
        help=(
            "Envia email para interif, aluno, coaches e coordenadores de cada conflito"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra preview dos emails no terminal sem chamar o gws",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    csv_path = Path(args.csv_file)

    if not csv_path.exists():
        print(f"Erro: arquivo não encontrado: {csv_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Verificador de duplicatas — {TITULO_EVENTO}")
    print(f"Arquivo: {csv_path.resolve()}\n")

    ocorrencias = load_ocorrencias(csv_path)
    conflitos = detectar_conflitos(ocorrencias)

    n_equipes = len({oc.equipe for oc in ocorrencias})
    print(f"{n_equipes} equipe(s) carregada(s) · {len(ocorrencias)} registro(s) de participantes.\n")

    if not conflitos:
        print("Nenhum participante encontrado em mais de uma equipe.")
        return

    print(f"{len(conflitos)} conflito(s) detectado(s):\n")
    render_table(conflitos)

    if args.notificar:
        notificar(conflitos, dry_run=args.dry_run)
    else:
        print(
            "\nDica: use --notificar (--dry-run para simular) para enviar as notificações."
        )


if __name__ == "__main__":
    main()
