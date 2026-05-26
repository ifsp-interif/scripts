# Scripts INTERIF

Três scripts Python para geração de CSV, validação de CPFs e envio de emails de confirmação de inscrição do INTERIF. Todos dependem do CLI `gws` para acesso ao Google Workspace; o script de validação de CPFs também requer o pacote [`cpf`](https://pypi.org/project/cpf/) e o [`rich`](https://pypi.org/project/rich/), gerenciados via `uv`.

## Pré-requisitos

- O CLI [`gws`](https://github.com/googleworkspace/cli) instalado e autenticado com uma conta com acesso às planilhas e ao Gmail.
- [`uv`](https://docs.astral.sh/uv/) instalado (gerencia o ambiente virtual e as dependências declaradas em `pyproject.toml`).

```bash
uv sync   # cria o .venv e instala as dependências na primeira vez
```

---

## 1. `equipes_interif.py` — Gerar o CSV de equipes

Lê duas planilhas do Google Sheets (inscrições de campi e de equipes), cruza os dados e salva o resultado em `equipes_interif.csv`.

### Uso

```bash
uv run python equipes_interif.py --campi <ID_PLANILHA_CAMPI> --teams <ID_PLANILHA_EQUIPES>
```

### Argumentos

| Argumento | Descrição |
|-----------|-----------|
| `--campi` | ID da planilha Google Sheets com as inscrições de coordenadores de campus |
| `--teams` | ID da planilha Google Sheets com as inscrições de equipes |

O ID da planilha é a string que aparece na URL entre `/d/` e `/edit`:
`https://docs.google.com/spreadsheets/d/**ID_AQUI**/edit`

### Saída

Arquivo `equipes_interif.csv` no mesmo diretório do script, com as colunas:

- Nome da Equipe, Campus
- Nome e email do Coordenador do Campus
- Nome e email do Responsável pela Equipe (Coach)
- Nome, email e CPF dos Participantes 1, 2 e 3

Equipes sem coordenador de campus correspondente são listadas no terminal ao final.

---

## 2. `cpf_check.py` — Validar CPFs

Lê o `equipes_interif.csv`, extrai e valida os CPFs de responsáveis (coaches) e participantes (alunos) usando o algoritmo módulo 11 oficial. Exibe uma lista ordenada por campus e pode notificar por email as pessoas com CPF inválido.

A detecção de CPFs é feita em duas etapas:

1. **Colunas CPF explícitas** — procura colunas cujo cabeçalho contenha a palavra `CPF` e mapeia cada uma ao nome e email da pessoa correspondente.
2. **Fallback regex** — se não houver colunas CPF, varre todos os campos buscando padrões de 11 dígitos (com ou sem pontuação `XXX.XXX.XXX-XX`).

CPFs repetidos (mesmo número em equipes diferentes) são deduplicados: apenas a primeira ocorrência é exibida.

### Uso

```bash
uv run python cpf_check.py [ARQUIVO] [opções]
```

`ARQUIVO` é opcional; o padrão é `equipes_interif.csv` no mesmo diretório do script.

### Opções

| Opção | Atalho | Descrição |
|-------|--------|-----------|
| `--invalidos` | `-i` | Exibe apenas os CPFs inválidos |
| `--notificar` | `-n` | Envia email para cada pessoa com CPF inválido pedindo a correção |
| `--dry-run` | | Simula o envio de emails sem disparar mensagens (requer `--notificar`) |
| `--output SAIDA.csv` | `-o` | Exporta o resultado exibido como arquivo CSV |

### Emails de notificação (`--notificar`)

Para cada CPF inválido que possua endereço de email no CSV, o script envia uma mensagem via `gws gmail +send` com:

- **Para (`--to`):** o email da pessoa com CPF inválido (coach ou aluno)
- **Cópia (`--cc`):** `interif@ifsp.edu.br` e o coordenador local do campus (deduplicados caso coincidam)

Entradas sem email disponível são listadas como aviso no terminal, sem interromper o envio das demais.

### Exemplos

```bash
# Listar todos os CPFs com status de validade
uv run python cpf_check.py

# Exibir apenas os inválidos
uv run python cpf_check.py --invalidos

# Exportar os inválidos para CSV
uv run python cpf_check.py -i -o invalidos.csv

# Simular o envio de notificações (sem enviar de verdade)
uv run python cpf_check.py --notificar --dry-run

# Enviar notificações de verdade
uv run python cpf_check.py --notificar
```

---

## 3. `send_emails.py` — Enviar emails de confirmação

Lê o `equipes_interif.csv` e envia três grupos de emails via Gmail:

1. **Coordenadores de campus** — um email por campus com todas as equipes inscritas (incluindo o responsável de cada equipe)
2. **Responsáveis pelas equipes** — um email por responsável com suas equipes
3. **Organização** — um email de resumo com o total de equipes por campus, enviado para `interif@ifsp.edu.br`

O assunto de todos os emails inclui a data e hora de geração (ex.: `até 2026-05-12 13h29min`).

### Uso

```bash
uv run python send_emails.py
```

### Configuração

Edite o bloco de configuração no topo do arquivo para ajustar os textos sem mexer na lógica:

| Variável | Descrição |
|----------|-----------|
| `CSV_FILE` | Caminho para o CSV gerado pelo script anterior |
| `DRY_RUN` | `True` para simular o envio sem disparar emails |
| `COORD_SUBJECT` / `COORD_PRE` / `COORD_POST` | Assunto e corpo do email para coordenadores |
| `RESP_SUBJECT` / `RESP_PRE` / `RESP_POST` | Assunto e corpo do email para responsáveis |
| `SUMMARY_TO` / `SUMMARY_SUBJECT` / `SUMMARY_PRE` / `SUMMARY_POST` | Destinatário e corpo do email de resumo |

Os textos de `PRE` aceitam os placeholders `{nome}` (primeiro nome do destinatário) e `{campus}` (apenas no `COORD_PRE`).

### Teste sem envio

Defina `DRY_RUN = True` no topo do arquivo antes de executar. O `gws` exibirá o payload de cada mensagem sem enviá-la.

---

## Fluxo completo

```bash
# 1. Gerar o CSV a partir das planilhas
uv run python equipes_interif.py --campi <ID_CAMPI> --teams <ID_EQUIPES>

# 2. Validar os CPFs e corrigir eventuais inválidos
uv run python cpf_check.py --invalidos
uv run python cpf_check.py --notificar --dry-run   # revisar antes de enviar
uv run python cpf_check.py --notificar             # notificar os inválidos

# 3. Enviar os emails de confirmação de inscrição
uv run python send_emails.py
```
