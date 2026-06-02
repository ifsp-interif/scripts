# Design: quadro resumo de equipes especiais + extração de send_email

Data: 2026-06-02

## Contexto

`lista_equipes_especiais.py` lê `equipes_interif.csv` e exibe equipes agrupadas em cinco
categorias (ensino médio integrado, 3/2/1 mulher, demais). O script não tem suporte a
envio de e-mail. Paralelamente, quatro outros scripts repetem variantes locais de uma
função `send_email` usando `gws gmail +send` via subprocess.

## Objetivos

1. Adicionar ao `lista_equipes_especiais.py` a flag `--resumo`, que gera e envia para
   `interif@ifsp.edu.br` um quadro resumo com o total de equipes por categoria e o
   detalhamento por campus dentro de cada categoria.
2. Extrair a lógica de envio de e-mail para `email_utils.py`, eliminando duplicação nos
   cinco scripts afetados.

---

## Seção 1 — Interface CLI (`lista_equipes_especiais.py`)

Dois novos argumentos:

```
--resumo      Gera e envia apenas o quadro resumo; não lista equipes individuais
--dry-run     Imprime o e-mail no terminal em vez de enviá-lo
```

Comportamento por combinação de flags:

| Flags                       | Resultado                                              |
|-----------------------------|--------------------------------------------------------|
| *(nenhuma)*                 | comportamento atual inalterado                         |
| `--resumo`                  | imprime resumo no terminal + envia e-mail              |
| `--resumo --dry-run`        | imprime resumo no terminal + mostra e-mail sem enviar  |
| `--resumo --output X.md`    | resumo no terminal + e-mail + salva Markdown do resumo |

---

## Seção 2 — Estrutura do quadro resumo

O resumo é construído a partir do `TeamGroups` já existente. Para cada uma das cinco
categorias, contam-se as equipes por campus e exibem-se em ordem alfabética de campus.

**Tipo interno:**
```python
# categoria → {campus → contagem}
SummaryData = dict[str, dict[str, int]]
```

**Nova função `build_summary(groups: TeamGroups) -> SummaryData`**
Itera sobre os mesmos cinco grupos de `group_tables()`.

**Nova função `render_summary(groups: TeamGroups, csv_path: Path) -> str`**
Converte `SummaryData` em texto puro (cabeçalho, totais por categoria e detalhamento
por campus). Retorna string — usada tanto para imprimir no terminal quanto como corpo
do e-mail.

**Exemplo de saída (terminal e corpo do e-mail — texto puro):**
```
Quadro resumo — Equipes especiais
Total de equipes: 47

Apenas alunos do ensino médio integrado (8)
  Campinas: 3
  São Paulo: 5

Exatamente três mulheres (12)
  Campinas: 4
  ...

Demais equipes (18)
  ...
```

**`config.py`** — nova constante adicionada:
```python
SPECIAL_SUMMARY_SUBJECT = f"Quadro resumo de equipes especiais — {TITULO_EVENTO}"
```

Destinatário: `EMAIL_INTERIF` (já definido em `config.py` como `interif@ifsp.edu.br`).

---

## Seção 3 — `email_utils.py` (novo arquivo)

Função pública única:

```python
def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    cc: str | None = None,
    attach: Path | None = None,
    dry_run: bool = False,
) -> None: ...
```

Cobre todos os padrões existentes: envio simples, com CC e com anexo PDF.

**Formato dry-run unificado:**
```
--- DRY-RUN: email para {to} ---
Assunto: {subject}
CC: {cc}          ← apenas se cc fornecido
Anexo: {attach}   ← apenas se attach fornecido

{body}
--- fim do email ---
```

---

## Seção 4 — Migração dos scripts existentes

| Script                    | Mudança                                                                          |
|---------------------------|----------------------------------------------------------------------------------|
| `inscricoes_atuais.py`    | Remove `send_email` local + `DRY_RUN` global; passa `dry_run=args.dry_run`       |
| `enviar_credenciais.py`   | Remove `_send` local; usa `send_email(..., cc=cc, dry_run=dry_run)`              |
| `gerar_placas.py`         | Remove `_send_pdf` local; usa `send_email(..., attach=caminho_pdf, dry_run=...)` |
| `gerar_etiquetas.py`      | Idem `gerar_placas.py`                                                           |
| `lista_equipes_especiais.py` | Importa `send_email`; adiciona `--resumo`/`--dry-run` + lógica de resumo     |

Nenhuma outra lógica de negócio é alterada nos scripts migrados.

---

## Arquivos modificados / criados

| Arquivo                        | Ação      |
|--------------------------------|-----------|
| `email_utils.py`               | Criar     |
| `config.py`                    | Modificar — adicionar `SPECIAL_SUMMARY_SUBJECT` |
| `lista_equipes_especiais.py`   | Modificar — `--resumo`, `--dry-run`, `build_summary`, `render_summary`, `send_summary_email` |
| `inscricoes_atuais.py`         | Modificar — substituir `send_email` local + `DRY_RUN` |
| `enviar_credenciais.py`        | Modificar — substituir `_send` local |
| `gerar_placas.py`              | Modificar — substituir `_send_pdf` local |
| `gerar_etiquetas.py`           | Modificar — substituir `_send_pdf` local |

---

## Não está no escopo

- Alteração de qualquer lógica de agrupamento ou categorização de equipes.
- Refatoração de `interif_core.py`.
- Mudança no comportamento padrão (sem `--resumo`) de `lista_equipes_especiais.py`.
