# Quadro resumo de equipes especiais + extração de send_email

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar `--resumo` ao `lista_equipes_especiais.py` para gerar e enviar um quadro resumo por categoria/campus para `interif@ifsp.edu.br`, e extrair a lógica de envio de e-mail para `email_utils.py`, eliminando duplicação em cinco scripts.

**Architecture:** Novo módulo `email_utils.py` expõe uma única função `send_email` que unifica os três padrões existentes (simples, com CC, com anexo PDF). Os cinco scripts migrados importam essa função e eliminam suas implementações locais. O `lista_equipes_especiais.py` ganha `build_summary`, `render_summary`, `render_summary_markdown` e integração com `send_email`.

**Tech Stack:** Python 3.11+, pytest, subprocess (`gws gmail +send`), tabulate

---

## Mapa de arquivos

| Arquivo | Ação |
|---|---|
| `email_utils.py` | Criar |
| `tests/test_email_utils.py` | Criar |
| `tests/test_lista_equipes_especiais.py` | Criar |
| `pyproject.toml` | Modificar — adicionar `[tool.pytest.ini_options]` |
| `config.py` | Modificar — adicionar `SPECIAL_SUMMARY_SUBJECT` |
| `lista_equipes_especiais.py` | Modificar — `build_summary`, `render_summary`, `render_summary_markdown`, `--resumo`, `--dry-run` |
| `inscricoes_atuais.py` | Modificar — substituir `send_email` local + `DRY_RUN` global |
| `enviar_credenciais.py` | Modificar — substituir `_send` local |
| `gerar_placas.py` | Modificar — substituir `_send_pdf` local |
| `gerar_etiquetas.py` | Modificar — substituir `_send_pdf` local |

---

## Task 1: Infraestrutura de testes + `email_utils.py`

**Files:**
- Modify: `pyproject.toml`
- Create: `email_utils.py`
- Create: `tests/test_email_utils.py`

- [ ] **Passo 1: Habilitar descoberta de módulos pelo pytest**

Em `pyproject.toml`, adicionar após a seção `[tool.ruff.format]`:

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
```

- [ ] **Passo 2: Criar `tests/` e escrever os testes**

```bash
mkdir -p tests
```

Criar `tests/test_email_utils.py` com o conteúdo:

```python
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from email_utils import send_email


def test_dry_run_simple(capsys):
    send_email("a@b.com", "Assunto", "Corpo", dry_run=True)
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "a@b.com" in out
    assert "Assunto" in out
    assert "Corpo" in out
    assert "CC:" not in out
    assert "Anexo:" not in out


def test_dry_run_with_cc(capsys):
    send_email("a@b.com", "Assunto", "Corpo", cc="c@d.com", dry_run=True)
    out = capsys.readouterr().out
    assert "CC: c@d.com" in out


def test_dry_run_with_attach(capsys, tmp_path):
    attach = tmp_path / "arquivo.pdf"
    send_email("a@b.com", "Assunto", "Corpo", attach=attach, dry_run=True)
    out = capsys.readouterr().out
    assert "Anexo:" in out
    assert str(attach) in out


def test_dry_run_cc_and_attach_together(capsys, tmp_path):
    attach = tmp_path / "arquivo.pdf"
    send_email("a@b.com", "Assunto", "Corpo", cc="c@d.com", attach=attach, dry_run=True)
    out = capsys.readouterr().out
    assert "CC: c@d.com" in out
    assert "Anexo:" in out


def test_real_send_basic():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = ""
        send_email("a@b.com", "Assunto", "Corpo")
        mock_run.assert_called_once_with(
            ["gws", "gmail", "+send", "--to", "a@b.com", "--subject", "Assunto", "--body", "Corpo"],
            capture_output=True,
            text=True,
            check=True,
        )


def test_real_send_with_cc():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = ""
        send_email("a@b.com", "Assunto", "Corpo", cc="c@d.com")
        args_list = mock_run.call_args[0][0]
        assert "--cc" in args_list
        idx = args_list.index("--cc")
        assert args_list[idx + 1] == "c@d.com"


def test_real_send_with_attach(tmp_path):
    attach = tmp_path / "arquivo.pdf"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = ""
        send_email("a@b.com", "Assunto", "Corpo", attach=attach)
        args_list = mock_run.call_args[0][0]
        assert "--attach" in args_list
        idx = args_list.index("--attach")
        assert args_list[idx + 1] == str(attach)


def test_real_send_raises_on_failure():
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "gws", stderr="erro")
        with pytest.raises(subprocess.CalledProcessError):
            send_email("a@b.com", "Assunto", "Corpo")
```

- [ ] **Passo 3: Executar os testes — esperar FAIL (módulo inexistente)**

```bash
uv run pytest tests/test_email_utils.py -v
```

Esperado: `ModuleNotFoundError: No module named 'email_utils'`

- [ ] **Passo 4: Criar `email_utils.py`**

```python
"""Envio de e-mail via gws gmail +send — utilitário compartilhado pelos scripts InterIF."""

import subprocess
from pathlib import Path


def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    cc: str | None = None,
    attach: Path | None = None,
    dry_run: bool = False,
) -> None:
    """Envia um e-mail via `gws gmail +send`. Em dry_run, imprime em vez de enviar."""
    if dry_run:
        print(f"\n--- DRY-RUN: email para {to} ---")
        print(f"Assunto: {subject}")
        if cc:
            print(f"CC: {cc}")
        if attach:
            print(f"Anexo: {attach}")
        print()
        print(body)
        print("--- fim do email ---")
        return

    cmd = ["gws", "gmail", "+send", "--to", to, "--subject", subject, "--body", body]
    if cc:
        cmd += ["--cc", cc]
    if attach:
        cmd += ["--attach", str(attach)]

    print(f"  → Enviando para {to} ...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("    OK: enviado")
        if result.stdout.strip():
            print(result.stdout.strip())
    except subprocess.CalledProcessError as exc:
        print("    ERRO: envio falhou")
        if exc.stdout:
            print(exc.stdout.strip())
        if exc.stderr:
            print(exc.stderr.strip())
        raise
```

- [ ] **Passo 5: Executar os testes — esperar PASS**

```bash
uv run pytest tests/test_email_utils.py -v
```

Esperado: 8 testes passando (`PASSED`)

---

## Task 2: Nova constante em `config.py`

**Files:**
- Modify: `config.py`

- [ ] **Passo 1: Adicionar `SPECIAL_SUMMARY_SUBJECT` em `config.py`**

Logo após `SUMMARY_SUBJECT` (linha ~46), adicionar:

```python
SPECIAL_SUMMARY_SUBJECT = f"Quadro resumo de equipes especiais — {TITULO_EVENTO}"
```

---

## Task 3: `build_summary`, `render_summary` e `render_summary_markdown` em `lista_equipes_especiais.py`

**Files:**
- Modify: `lista_equipes_especiais.py`
- Create: `tests/test_lista_equipes_especiais.py`

- [ ] **Passo 1: Escrever os testes**

Criar `tests/test_lista_equipes_especiais.py`:

```python
from pathlib import Path

from lista_equipes_especiais import (
    Team,
    TeamGroups,
    build_summary,
    group_teams,
    render_summary,
    render_summary_markdown,
)


def _grupos_fixture() -> TeamGroups:
    teams = [
        Team(campus="Campinas",   nome="Alpha", mulheres=3,    apenas_ensino_medio=False),
        Team(campus="São Paulo",  nome="Beta",  mulheres=3,    apenas_ensino_medio=False),
        Team(campus="Campinas",   nome="Gamma", mulheres=1,    apenas_ensino_medio=True),
        Team(campus="Campinas",   nome="Delta", mulheres=None, apenas_ensino_medio=False),
        Team(campus="São Paulo",  nome="Épsilon", mulheres=None, apenas_ensino_medio=False),
    ]
    return group_teams(teams)


def test_build_summary_tres_mulheres():
    summary = build_summary(_grupos_fixture())
    assert summary["Exatamente três mulheres"] == {"Campinas": 1, "São Paulo": 1}


def test_build_summary_uma_mulher():
    summary = build_summary(_grupos_fixture())
    assert summary["Exatamente uma mulher"] == {"Campinas": 1}


def test_build_summary_categoria_vazia():
    summary = build_summary(_grupos_fixture())
    assert summary["Exatamente duas mulheres"] == {}


def test_build_summary_demais():
    summary = build_summary(_grupos_fixture())
    # Delta (Campinas, sem mulheres, não ensino médio) e Épsilon (São Paulo)
    assert summary["Demais equipes"] == {"Campinas": 1, "São Paulo": 1}


def test_render_summary_cabecalho(tmp_path):
    csv_path = tmp_path / "equipes.csv"
    csv_path.touch()
    result = render_summary(_grupos_fixture(), csv_path)
    assert "Quadro resumo — Equipes especiais" in result
    assert "Total de equipes: 5" in result


def test_render_summary_contagem_categoria(tmp_path):
    csv_path = tmp_path / "equipes.csv"
    csv_path.touch()
    result = render_summary(_grupos_fixture(), csv_path)
    assert "Exatamente três mulheres (2)" in result
    assert "Exatamente duas mulheres (0)" in result


def test_render_summary_detalhe_campus(tmp_path):
    csv_path = tmp_path / "equipes.csv"
    csv_path.touch()
    result = render_summary(_grupos_fixture(), csv_path)
    assert "  Campinas: 1" in result
    assert "  São Paulo: 1" in result


def test_render_summary_markdown_titulo(tmp_path):
    csv_path = tmp_path / "equipes.csv"
    csv_path.touch()
    result = render_summary_markdown(_grupos_fixture(), csv_path)
    assert "# Quadro resumo — Equipes especiais" in result
    assert "## Exatamente três mulheres (2)" in result
```

- [ ] **Passo 2: Executar os testes — esperar FAIL**

```bash
uv run pytest tests/test_lista_equipes_especiais.py -v
```

Esperado: `ImportError` (funções ainda não existem)

- [ ] **Passo 3: Implementar as três funções em `lista_equipes_especiais.py`**

Adicionar logo após a função `group_tables` (linha ~177):

```python
def build_summary(groups: TeamGroups) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for title, teams, _ in group_tables(groups):
        campus_counts: dict[str, int] = {}
        for team in teams:
            campus_counts[team.campus] = campus_counts.get(team.campus, 0) + 1
        summary[title] = campus_counts
    return summary


def render_summary(groups: TeamGroups, csv_path: Path) -> str:
    lines = [
        "Quadro resumo — Equipes especiais",
        f"Arquivo: {csv_path.resolve()}",
        f"Total de equipes: {groups.total_equipes}",
    ]
    for title, campus_counts in build_summary(groups).items():
        total_cat = sum(campus_counts.values())
        lines.append("")
        lines.append(f"{title} ({total_cat})")
        for campus in sorted(campus_counts):
            lines.append(f"  {campus}: {campus_counts[campus]}")
    return "\n".join(lines)


def render_summary_markdown(groups: TeamGroups, csv_path: Path) -> str:
    lines = [
        "# Quadro resumo — Equipes especiais",
        "",
        f"Arquivo: `{csv_path}`",
        f"Total de equipes: **{groups.total_equipes}**",
        "",
    ]
    for title, campus_counts in build_summary(groups).items():
        total_cat = sum(campus_counts.values())
        lines.append(f"## {title} ({total_cat})")
        lines.append("")
        if campus_counts:
            rows = [[campus, campus_counts[campus]] for campus in sorted(campus_counts)]
            lines.extend(tabulate(rows, headers=["Campus", "Equipes"], tablefmt="github").splitlines())
        else:
            lines.append("*(nenhuma equipe)*")
        lines.append("")
    return "\n".join(lines)
```

- [ ] **Passo 4: Executar os testes — esperar PASS**

```bash
uv run pytest tests/test_lista_equipes_especiais.py -v
```

Esperado: 9 testes passando

---

## Task 4: Adicionar `--resumo` e `--dry-run` a `lista_equipes_especiais.py`

**Files:**
- Modify: `lista_equipes_especiais.py`

- [ ] **Passo 1: Adicionar imports no topo do arquivo**

Após `from tabulate import tabulate`, adicionar:

```python
from config import EMAIL_INTERIF, SPECIAL_SUMMARY_SUBJECT
from email_utils import send_email
```

- [ ] **Passo 2: Atualizar `parse_args()`**

Substituir a função `parse_args` completa por:

```python
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lista equipes especiais a partir de equipes_interif.csv."
    )
    parser.add_argument(
        "--input",
        "-i",
        metavar="ARQUIVO",
        default=str(CSV_FILE),
        help=f"Caminho do CSV de entrada (padrão: {CSV_FILE.name})",
    )
    parser.add_argument(
        "--output",
        "-o",
        metavar="ARQUIVO.md",
        help="Salva as listas (ou o resumo, com --resumo) em um arquivo Markdown",
    )
    parser.add_argument(
        "--resumo",
        action="store_true",
        help="Gera e envia o quadro resumo para interif@ifsp.edu.br; não lista equipes individuais",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Com --resumo: imprime o e-mail sem enviá-lo",
    )
    return parser.parse_args()
```

- [ ] **Passo 3: Atualizar `main()`**

Substituir a função `main` completa por:

```python
def main() -> None:
    args = parse_args()
    csv_path = Path(args.input)

    if not csv_path.exists():
        print(f"Erro: arquivo não encontrado: {csv_path}", file=sys.stderr)
        sys.exit(1)

    try:
        teams = load_teams(csv_path)
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        sys.exit(1)

    groups = group_teams(teams)

    if args.resumo:
        body = render_summary(groups, csv_path)
        print(body)
        print()
        send_email(EMAIL_INTERIF, SPECIAL_SUMMARY_SUBJECT, body, dry_run=args.dry_run)
        if args.output:
            output_path = Path(args.output)
            output_path.write_text(render_summary_markdown(groups, csv_path), encoding="utf-8")
            print(f"\nMarkdown salvo em {output_path}")
        return

    render(groups, csv_path)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(render_markdown(groups, csv_path), encoding="utf-8")
        print(f"\nMarkdown salvo em {output_path}")
```

- [ ] **Passo 4: Verificar manualmente**

```bash
uv run python lista_equipes_especiais.py --resumo --dry-run
```

Esperado: imprime o quadro resumo no terminal seguido do bloco `--- DRY-RUN: email para interif@ifsp.edu.br ---`.

```bash
uv run python lista_equipes_especiais.py
```

Esperado: comportamento original inalterado (lista detalhada de equipes).

- [ ] **Passo 5: Executar toda a suite de testes**

```bash
uv run pytest tests/ -v
```

Esperado: todos os testes passando

---

## Task 5: Migrar `inscricoes_atuais.py`

**Files:**
- Modify: `inscricoes_atuais.py`

- [ ] **Passo 1: Substituir import e remover globals**

Remover a linha:
```python
import subprocess
```

Substituir o bloco:
```python
DRY_RUN = False   # True → não envia emails de verdade
```
por:
```python
from email_utils import send_email
```

- [ ] **Passo 2: Remover a função `send_email` local**

Remover completamente a função (linhas 41–64 aproximadamente):

```python
def send_email(to: str, subject: str, body: str) -> None:
    if DRY_RUN:
        ...
    cmd = ["gws", "gmail", "+send", "--to", to, "--subject", subject, "--body", body]
    ...
```

- [ ] **Passo 3: Adicionar `dry_run: bool` nas cinco funções de envio**

Substituir cada assinatura e call site conforme abaixo.

`send_coordinator_emails`:
```python
def send_coordinator_emails(por_campus: dict, dry_run: bool) -> int:
    print("\n=== Emails para coordenadores de campus ===")
    count = 0
    for email, data in por_campus.items():
        lines = "\n".join(format_team_line_coord(e) for e in data["equipes"])
        body = (
            COORD_PRE.format(nome=first_name(data["nome"]), campus=data["campus"])
            + "\n"
            + lines
            + "\n"
            + COORD_POST
        )
        send_email(email, f"{COORD_SUBJECT} {_TIMESTAMP}", body, dry_run=dry_run)
        count += 1
    return count
```

`send_summary_email`:
```python
def send_summary_email(por_campus: dict, dry_run: bool) -> None:
    print("\n=== Email de resumo para a organização ===")
    lines = "\n".join(
        f"- {data['campus']}: {len(data['equipes'])} equipe(s)"
        for data in sorted(por_campus.values(), key=lambda d: d["campus"])
    )
    total = sum(len(d["equipes"]) for d in por_campus.values())
    body = SUMMARY_PRE + "\n" + lines + f"\n\nTotal geral: {total} equipe(s)" + "\n" + SUMMARY_POST
    send_email(SUMMARY_TO, f"{SUMMARY_SUBJECT} {_TIMESTAMP}", body, dry_run=dry_run)
```

`send_no_teams_emails`:
```python
def send_no_teams_emails(no_teams_coordinators: list[dict], dry_run: bool) -> int:
    print("\n=== Emails para coordenadores de campi sem equipes ===")
    count = 0
    for coord in no_teams_coordinators:
        email = coord["coord_email"]
        if not email:
            print(f"  Aviso: sem email de coordenador para {coord['campus']} — envio ignorado")
            continue
        body = NO_TEAMS_BODY.format(
            nome=first_name(coord["coord_nome"]),
            campus=coord["campus"],
        )
        send_email(email, f"{NO_TEAMS_SUBJECT} {_TIMESTAMP}", body, dry_run=dry_run)
        count += 1
    return count
```

`send_no_teams_summary_email`:
```python
def send_no_teams_summary_email(no_teams_coordinators: list[dict], dry_run: bool) -> None:
    print("\n=== Email de resumo para a organização ===")
    lines = "\n".join(f"- {coord['campus']}" for coord in no_teams_coordinators)
    total = len(no_teams_coordinators)
    body = (
        "Seguem abaixo os campi sem equipes inscritas:\n\n"
        + (lines or "- Nenhum campus sem equipes inscritas")
        + f"\n\nTotal: {total} campus sem equipes inscritas"
        + "\n"
        + SUMMARY_POST
    )
    send_email(SUMMARY_TO, f"{NO_TEAMS_SUBJECT} — resumo {_TIMESTAMP}", body, dry_run=dry_run)
```

`send_advisor_emails`:
```python
def send_advisor_emails(por_resp: dict, dry_run: bool) -> int:
    print("\n=== Emails para responsáveis pelas equipes ===")
    count = 0
    for email, data in por_resp.items():
        lines = "\n".join(format_team_line_resp(e) for e in data["equipes"])
        body = (
            RESP_PRE.format(nome=first_name(data["nome"]))
            + "\n"
            + lines
            + "\n"
            + RESP_POST
        )
        send_email(email, f"{RESP_SUBJECT} {_TIMESTAMP}", body, dry_run=dry_run)
        count += 1
    return count
```

- [ ] **Passo 4: Atualizar `main()`**

Substituir `main` completa por:

```python
def main() -> None:
    args = parse_args()

    teams = load_teams(args.csv)
    print(f"Carregadas {len(teams)} equipes de '{args.csv}'.")

    if args.no_teams:
        coordinators = load_coordinators(args.coordenadores)
        print(f"Carregados {len(coordinators)} coordenador(es) de '{args.coordenadores}'.")
        no_teams_coordinators = find_no_teams_coordinators(coordinators, teams)
        n_no_teams = send_no_teams_emails(no_teams_coordinators, args.dry_run)
        send_no_teams_summary_email(no_teams_coordinators, args.dry_run)
        print(
            f"\nPronto! {n_no_teams} email(s) para coordenadores de campi sem equipes, "
            f"1 resumo para {SUMMARY_TO}."
        )
        return

    por_campus = group_by_coordinator(teams)
    por_resp   = group_by_advisor(teams)

    n_coord = send_coordinator_emails(por_campus, args.dry_run)
    n_resp  = send_advisor_emails(por_resp, args.dry_run)
    send_summary_email(por_campus, args.dry_run)

    print(f"\nPronto! {n_coord} email(s) para coordenadores, {n_resp} email(s) para responsáveis, 1 resumo para {SUMMARY_TO}.")
```

- [ ] **Passo 5: Verificar**

```bash
uv run python inscricoes_atuais.py --dry-run 2>&1 | head -30
```

Esperado: saída com `--- DRY-RUN: email para ...` em vez de envios reais; sem `NameError` ou `ImportError`.

---

## Task 6: Migrar `enviar_credenciais.py`

**Files:**
- Modify: `enviar_credenciais.py`

- [ ] **Passo 1: Substituir import**

Remover:
```python
import subprocess
```

Adicionar (junto aos outros imports do projeto):
```python
from email_utils import send_email
```

- [ ] **Passo 2: Remover `_send` local**

Remover completamente a função `_send` (linhas 43–66).

- [ ] **Passo 3: Substituir chamadas de `_send` por `send_email`**

Em `enviar_emails_coordenadores`, substituir:
```python
_send(
    to=data["coord_email"],
    subject=f"{EMAIL_SUBJECT_PREFIX} — Campus {campus}",
    body="".join(linhas),
    dry_run=dry_run,
)
```
por:
```python
send_email(
    data["coord_email"],
    f"{EMAIL_SUBJECT_PREFIX} — Campus {campus}",
    "".join(linhas),
    dry_run=dry_run,
)
```

Em `enviar_emails_tecnicos`, substituir:
```python
_send(
    to=email,
    subject=EMAIL_SUBJECT_PREFIX,
    body="".join(linhas),
    dry_run=dry_run,
)
```
por:
```python
send_email(email, EMAIL_SUBJECT_PREFIX, "".join(linhas), dry_run=dry_run)
```

Em `enviar_emails_participantes`, substituir:
```python
_send(
    to=to,
    subject=f"{EMAIL_SUBJECT_PREFIX} — Equipe {cred.nome_equipe}",
    body=body,
    cc=cc,
    dry_run=dry_run,
)
```
por:
```python
send_email(
    to,
    f"{EMAIL_SUBJECT_PREFIX} — Equipe {cred.nome_equipe}",
    body,
    cc=cc,
    dry_run=dry_run,
)
```

Em `enviar_resumo`, substituir:
```python
_send(
    to=EMAIL_INTERIF,
    subject=f"Resumo de envio de credenciais — {TITULO_EVENTO}",
    body="".join(linhas),
    dry_run=dry_run,
)
```
por:
```python
send_email(
    EMAIL_INTERIF,
    f"Resumo de envio de credenciais — {TITULO_EVENTO}",
    "".join(linhas),
    dry_run=dry_run,
)
```

- [ ] **Passo 4: Verificar**

```bash
uv run python enviar_credenciais.py --dry-run 2>&1 | head -20
```

Esperado: saída com `--- DRY-RUN: email para ...`; sem erros de importação.

---

## Task 7: Migrar `gerar_placas.py`

**Files:**
- Modify: `gerar_placas.py`

- [ ] **Passo 1: Substituir import**

Remover:
```python
import subprocess
```

Adicionar junto aos imports do projeto (após `from config import ...`):
```python
from email_utils import send_email
```

- [ ] **Passo 2: Remover `_send_pdf` local**

Remover completamente a função `_send_pdf` (linhas 260–290 aproximadamente).

- [ ] **Passo 3: Substituir a chamada no `main()`**

Substituir:
```python
body = PLACA_BODY_TEMPLATE.format(nome=coord_nome, campus=campus)
_send_pdf(
    to=coord_email,
    subject=f"{PLACA_SUBJECT} — {campus}",
    body=body,
    attach=caminho_pdf,
    dry_run=args.dry_run,
)
```
por:
```python
body = PLACA_BODY_TEMPLATE.format(nome=coord_nome, campus=campus)
send_email(
    coord_email,
    f"{PLACA_SUBJECT} — {campus}",
    body,
    attach=caminho_pdf,
    dry_run=args.dry_run,
)
```

- [ ] **Passo 4: Verificar sintaxe**

```bash
uv run python -c "import gerar_placas"
```

Esperado: sem erros de importação.

---

## Task 8: Migrar `gerar_etiquetas.py`

**Files:**
- Modify: `gerar_etiquetas.py`

- [ ] **Passo 1: Substituir import**

Remover:
```python
import subprocess
```

Adicionar junto aos imports do projeto (após `from config import ...`):
```python
from email_utils import send_email
```

- [ ] **Passo 2: Remover `_send_pdf` local**

Remover completamente a função `_send_pdf` (linhas 187–219 aproximadamente).

- [ ] **Passo 3: Substituir a chamada no `main()`**

Substituir:
```python
body = ETIQ_BODY_TEMPLATE.format(nome=coord_nome, campus=campus)
_send_pdf(
    to=coord_email,
    subject=f"{ETIQ_SUBJECT} — {campus}",
    body=body,
    attach=caminho_pdf,
    dry_run=args.dry_run,
)
```
por:
```python
body = ETIQ_BODY_TEMPLATE.format(nome=coord_nome, campus=campus)
send_email(
    coord_email,
    f"{ETIQ_SUBJECT} — {campus}",
    body,
    attach=caminho_pdf,
    dry_run=args.dry_run,
)
```

- [ ] **Passo 4: Verificar sintaxe**

```bash
uv run python -c "import gerar_etiquetas"
```

Esperado: sem erros de importação.

---

## Task 9: Suite completa + commit único

**Files:** todos os modificados acima

- [ ] **Passo 1: Executar suite completa**

```bash
uv run pytest tests/ -v
```

Esperado: todos os testes passando (mínimo 17 testes).

- [ ] **Passo 2: Verificar `--resumo` end-to-end**

```bash
uv run python lista_equipes_especiais.py --resumo --dry-run
uv run python lista_equipes_especiais.py --resumo --dry-run --output /tmp/resumo_teste.md && cat /tmp/resumo_teste.md
```

Esperado: quadro resumo no terminal, bloco DRY-RUN do e-mail, e arquivo Markdown com headers `#`/`##`.

- [ ] **Passo 3: Linter**

```bash
uv run ruff check . && uv run ruff format --check .
```

Corrigir qualquer aviso antes de commitar.

- [ ] **Passo 4: Commit único**

```bash
git add email_utils.py tests/ pyproject.toml config.py lista_equipes_especiais.py inscricoes_atuais.py enviar_credenciais.py gerar_placas.py gerar_etiquetas.py docs/superpowers/
git commit -m "$(cat <<'EOF'
feat: adiciona quadro resumo de equipes especiais e extrai send_email para email_utils

- Novo email_utils.py com send_email unificado (suporte a cc, attach, dry_run)
- Migra inscricoes_atuais, enviar_credenciais, gerar_placas e gerar_etiquetas
  para usar email_utils, eliminando implementações locais duplicadas
- lista_equipes_especiais: flag --resumo gera e envia quadro por categoria/campus
  para interif@ifsp.edu.br; --dry-run imprime sem enviar
- Adiciona SPECIAL_SUMMARY_SUBJECT em config.py
- Testes para email_utils e funções de resumo

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```
