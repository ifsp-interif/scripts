# Scripts INTERIF

Scripts Python para organização do InterIF: geração de CSV, validação de CPFs, emails de confirmação de inscrição, geração de arquivos BOCA e envio de credenciais de acesso.

## Pré-requisitos

- O CLI [`gws`](https://github.com/googleworkspace/cli) instalado e autenticado com uma conta com acesso às planilhas e ao Gmail (necessário para `equipes_interif.py`, `cpf_check.py`, `inscricoes_atuais.py` e `enviar_credenciais.py`).
- [`uv`](https://docs.astral.sh/uv/) instalado (gerencia o ambiente virtual e as dependências declaradas em `pyproject.toml`).

```bash
uv sync   # cria o .venv e instala as dependências na primeira vez
```

---

## Fluxo completo

```
equipes_interif.py        ← gera equipes_interif.csv a partir das planilhas
       │
       ├─► cpf_check.py               ← valida CPFs; notifica inválidos por email
       │
       ├─► inscricoes_atuais.py       ← confirma inscrições (emails de boas-vindas)
       │
       ├─► total_camisetas.py         ← contagem de camisetas por tamanho e campus
       │
       ├─► lista_equipes_especiais.py ← lista equipes por categoria especial
       │
       └─► gerar_arquivos_boca.py ← gera usuarios.txt, INTERIF.toml, score.sep,
                │                    secret_interif.toml em output/
                │
                ├─► enviar_credenciais.py ← envia login/senha por email
                │     (lê output/usuarios.txt como fonte da verdade)
                │
                ├─► gerar_etiquetas.py ← gera etiquetas de credenciais em PDF
                │     (lê output/usuarios.txt como fonte da verdade)
                │
                └─► gerar_placas.py ← gera placas de identificação em PDF
                      (lê output/usuarios.txt como fonte da verdade)
```

```bash
# 1. Gerar o CSV a partir das planilhas
uv run python equipes_interif.py --campi <ID_CAMPI> --teams <ID_EQUIPES>

# 2. Validar os CPFs e corrigir eventuais inválidos
uv run python cpf_check.py --invalidos
uv run python cpf_check.py --notificar --dry-run   # revisar antes de enviar
uv run python cpf_check.py --notificar             # notificar os inválidos

# 3. Enviar os emails de confirmação de inscrição
uv run python inscricoes_atuais.py

# 4. Verificar pedidos de camiseta
uv run python total_camisetas.py
uv run python total_camisetas.py -o camisetas.md   # exportar como Markdown

# 4b. Listar equipes especiais (ensino médio, femininas, mistas)
uv run python lista_equipes_especiais.py
uv run python lista_equipes_especiais.py -o especiais.md   # exportar como Markdown

# 5. Gerar os arquivos de configuração do BOCA
uv run python gerar_arquivos_boca.py
# ou, em ambiente de teste:
uv run python gerar_arquivos_boca.py --dry-run

# 6. Enviar credenciais de acesso por email
uv run python enviar_credenciais.py --dry-run      # revisar antes de enviar
uv run python enviar_credenciais.py                # disparar os emails

# 7. Gerar etiquetas de credenciais (uma por equipe, agrupadas por campus)
uv run python gerar_etiquetas.py --dry-run            # gera PDFs, simula envio
uv run python gerar_etiquetas.py                      # gera PDFs em etiquetas/
uv run python gerar_etiquetas.py --send               # gera PDFs e envia ao coordenador

# 8. Gerar placas de identificação (uma por equipe, agrupadas por campus)
uv run python gerar_placas.py --dry-run               # gera PDFs, simula envio
uv run python gerar_placas.py                         # gera PDFs em placas/
uv run python gerar_placas.py --send                  # gera PDFs e envia ao coordenador
```

---

## 1. `equipes_interif.py` — Gerar o CSV de equipes

Lê duas planilhas do Google Sheets (inscrições de campi e de equipes), cruza os dados e salva o resultado em `equipes_interif.csv`. Também salva `coordenadores_interif.csv` com todos os coordenadores de campi inscritos.

### Uso

```bash
uv run python equipes_interif.py --campi <ID_PLANILHA_CAMPI> --teams <ID_PLANILHA_EQUIPES>
```

### Argumentos

| Argumento | Descrição |
|-----------|-----------|
| `--campi` | ID da planilha Google Sheets com as inscrições de coordenadores de campus |
| `--teams` | ID da planilha Google Sheets com as inscrições de equipes |
| `--output ARQUIVO` / `-o ARQUIVO` | CSV de equipes gerado (padrão: `equipes_interif.csv`) |
| `--coordenadores ARQUIVO` / `-c ARQUIVO` | CSV de coordenadores gerado (padrão: `coordenadores_interif.csv`) |

O ID da planilha é a string que aparece na URL entre `/d/` e `/edit`:
`https://docs.google.com/spreadsheets/d/**ID_AQUI**/edit`

### Saída

Arquivo `equipes_interif.csv` no mesmo diretório do script, com as colunas:

- Nome da Equipe, Campus
- Nome e email do Coordenador do Campus
- Nome e email do Responsável pela Equipe (Coach)
- Nome, email e CPF dos Participantes 1, 2 e 3
- Tamanho de camiseta dos Participantes 1, 2 e 3
- Quem mais deve receber as credenciais de acesso?

Arquivo `coordenadores_interif.csv` com todos os campi inscritos na planilha de coordenadores, incluindo aqueles sem equipes inscritas.

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
| `--dry-run` | | Mostra um preview dos emails no terminal sem chamar o `gws` (requer `--notificar`) |
| `--output SAIDA.csv` | `-o` | Exporta o resultado exibido como arquivo CSV |

### Emails de notificação (`--notificar`)

Para cada CPF inválido que possua endereço de email no CSV, o script envia uma mensagem via `gws gmail +send` com:

- **Para (`--to`):** o email da pessoa com CPF inválido (coach ou aluno)
- **Cópia (`--cc`):** `EMAIL_INTERIF` (`config.py`) e o coordenador local do campus (deduplicados caso coincidam)

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

## 3. `inscricoes_atuais.py` — Enviar emails de confirmação

Lê o `equipes_interif.csv` e envia três grupos de emails via Gmail:

1. **Coordenadores de campus** — um email por campus com todas as equipes inscritas (incluindo o responsável de cada equipe)
2. **Responsáveis pelas equipes** — um email por responsável com suas equipes
3. **Organização** — um email de resumo com o total de equipes por campus, enviado para `EMAIL_INTERIF` (definido em `config.py`)

O assunto de todos os emails inclui a data e hora de geração (ex.: `até 2026-05-12 13h29min`).

### Uso

```bash
uv run python inscricoes_atuais.py
uv run python inscricoes_atuais.py --dry-run
uv run python inscricoes_atuais.py --no-teams --dry-run
```

Com `--no-teams`/`-n`, o script usa também `coordenadores_interif.csv`, envia somente para coordenadores de campi que não possuem equipes inscritas e manda para `EMAIL_INTERIF` um resumo com a lista desses campi.

### Configuração

Os textos dos emails (`COORD_*`, `RESP_*`, `SUMMARY_*`, `NO_TEAMS_*`) e o destinatário do resumo (`EMAIL_INTERIF`) vêm de **`config.py`** — edite lá para mudar os textos.

Principais opções:

| Opção | Descrição |
|-------|-----------|
| `--csv ARQUIVO` | CSV de equipes (padrão: `equipes_interif.csv`) |
| `--coordenadores ARQUIVO` / `-c ARQUIVO` | CSV de coordenadores (padrão: `coordenadores_interif.csv`) |
| `--no-teams` / `-n` | Envia somente para coordenadores de campi sem equipes |
| `--dry-run` | Mostra um preview dos emails no terminal sem chamar o `gws` |

### Teste sem envio

Use `--dry-run` antes de executar o envio real para conferir destinatário, assunto e corpo de cada email.

---

## 4. `total_camisetas.py` — Contagem de camisetas

Lê o `equipes_interif.csv` e exibe o total de camisetas por tamanho em cada campus. Participantes que responderam "Não quero camiseta" são contados separadamente e excluídos dos totais por tamanho.

### Uso

```bash
uv run python total_camisetas.py [opções]
```

### Opções

| Opção | Atalho | Descrição |
|-------|--------|-----------|
| `--input ARQUIVO` | `-i` | CSV de entrada (padrão: `equipes_interif.csv`) |
| `--output ARQUIVO` | `-o` | Salva o resultado em Markdown (ex.: `camisetas.md`) |

### Exemplos

```bash
# Exibir tabela no terminal
uv run python total_camisetas.py

# Exportar como Markdown
uv run python total_camisetas.py -o camisetas.md
```

---

## 5. `lista_equipes_especiais.py` — Listar equipes por categoria especial

Lê o `equipes_interif.csv` e classifica as equipes em cinco categorias:

1. **Apenas alunos do ensino médio integrado** — composta somente por alunos do EM
2. **Exatamente três mulheres** — equipe com composição totalmente feminina
3. **Exatamente duas mulheres** — equipe mista com maioria feminina
4. **Exatamente uma mulher** — equipe mista com minoria feminina
5. **Demais equipes** — nenhuma das categorias acima

As categorias não são mutuamente exclusivas: uma equipe de ensino médio integralmente feminina aparece em ambos os grupos relevantes.

### Uso

```bash
uv run python lista_equipes_especiais.py [opções]
```

### Opções

| Opção | Atalho | Descrição |
|-------|--------|-----------|
| `--input ARQUIVO` | `-i` | CSV de entrada (padrão: `equipes_interif.csv`) |
| `--output ARQUIVO.md` | `-o` | Salva o resultado em Markdown |

### Exemplos

```bash
# Exibir no terminal
uv run python lista_equipes_especiais.py

# Exportar como Markdown
uv run python lista_equipes_especiais.py -o especiais.md
```

---

## 6. `gerar_arquivos_boca.py` — Gerar arquivos do BOCA

Lê `equipes_interif.csv` e `assets/ifsp_campi.csv` e gera os quatro arquivos de configuração necessários para o [BOCA Online Contest Administrator](https://www.ime.usp.br/~cassio/boca/):

| Arquivo | Conteúdo |
|---------|----------|
| `output/usuarios.txt` | Cadastro de times, staff, juízes e placar |
| `output/INTERIF.toml` | Configuração de sedes para o animator |
| `output/score.sep` | Definição de blocos de placar por campus |
| `output/secret_interif.toml` | Segredos por sede |

A numeração de `usernumber` segue blocos de 50 por campus (times: 1001–4000, staff: 5001–5060, juiz: 6001, placar: 6002). O script agrupa as equipes por campus internamente, sem depender da ordenação do CSV.

### Uso

```bash
uv run python gerar_arquivos_boca.py [CSV] [opções]
```

### Opções

| Opção | Atalho | Descrição |
|-------|--------|-----------|
| `CSV` | | CSV de equipes (padrão: `equipes_interif.csv`) |
| `--output DIR` | `-o` | Diretório de saída (padrão: `output/`) |
| `--user-output ARQUIVO` | `-u` | Nome do arquivo de usuários (padrão: `usuarios.txt`) |
| `--animator ARQUIVO` | `-a` | Nome do arquivo do animator (padrão: `INTERIF.toml`) |
| `--score ARQUIVO` | `-s` | Nome do arquivo de score (padrão: `score.sep`) |
| `--secrets ARQUIVO` | | Nome do arquivo de segredos (padrão: `secret_interif.toml`) |
| `--campi ARQUIVO` | | CSV de siglas de campus (padrão: `assets/ifsp_campi.csv`) |
| `--sigla` | | Usa sigla do campus no `userfullname` (ex.: `[IFSP - SPO]` em vez de `[IFSP - São Paulo]`) |
| `--dry-run` | | Exibe o conteúdo dos arquivos sem gravá-los |

### Exemplos

```bash
# Gerar os arquivos em output/
uv run python gerar_arquivos_boca.py

# Usar siglas nos nomes de usuário
uv run python gerar_arquivos_boca.py --sigla

# Pré-visualizar sem gravar
uv run python gerar_arquivos_boca.py --dry-run
```

---

## 7. `enviar_credenciais.py` — Enviar credenciais de acesso

Envia os dados de login do BOCA por email, usando `output/usuarios.txt` como **fonte da verdade** para username e senha. Os endereços de email são lidos do `equipes_interif.csv` e vinculados às equipes pelo nome. Isso garante que as senhas enviadas por email são idênticas às gravadas nos arquivos BOCA — mesmo que o CSV tenha sido alterado após a geração dos arquivos.

Grupos de destinatários:

1. **Coordenadores de campus** — um email por campus com todas as equipes e senhas, agrupadas por técnico responsável
2. **Técnicos responsáveis** — um email por técnico com suas equipes e senhas
3. **Participantes indicados** — um email por equipe para os participantes que solicitaram receber as credenciais (coluna *Quem mais deve receber as credenciais de acesso?*)
4. **Organização** — resumo enviado para `EMAIL_INTERIF` (definido em `config.py`)

### Uso

```bash
uv run python enviar_credenciais.py [opções]
```

### Opções

| Opção | Descrição |
|-------|-----------|
| `--usuarios ARQUIVO` | Caminho para `usuarios.txt` (padrão: `output/usuarios.txt`) |
| `--csv ARQUIVO` | CSV de equipes (padrão: `equipes_interif.csv`) |
| `--campi ARQUIVO` | CSV de siglas de campus (padrão: `assets/ifsp_campi.csv`) |
| `--dry-run` | Simula o envio sem disparar emails reais |

### Exemplos

```bash
# Revisar o que seria enviado
uv run python enviar_credenciais.py --dry-run

# Disparar os emails
uv run python enviar_credenciais.py
```

---

## 8. `gerar_etiquetas.py` — Gerar etiquetas de credenciais

Lê `output/usuarios.txt` (fonte da verdade gerada por `gerar_arquivos_boca.py`) e os endereços de email do `equipes_interif.csv`, e gera um PDF de etiquetas de credenciais por campus — layout 2 colunas × 6 etiquetas por página A4. Cada etiqueta exibe o campus, o nome da equipe, o username e a senha do BOCA.

### Uso

```bash
uv run python gerar_etiquetas.py [opções]
```

### Opções

| Opção | Atalho | Descrição |
|-------|--------|-----------|
| `--usuarios ARQUIVO` | | Caminho para `usuarios.txt` (padrão: `output/usuarios.txt`) |
| `--csv ARQUIVO` | | CSV de equipes (padrão: `equipes_interif.csv`) |
| `--campi ARQUIVO` | | CSV de siglas de campus (padrão: `assets/ifsp_campi.csv`) |
| `--output DIR` | `-o` | Diretório de saída dos PDFs (padrão: `etiquetas/`) |
| `--send` | `-s` | Envia cada PDF ao coordenador do campus via `gws gmail +send --attach` |
| `--dry-run` | | Gera os PDFs e mostra um preview dos emails no terminal sem chamar o `gws` |

### Exemplos

```bash
# Gerar etiquetas em etiquetas/ sem enviar
uv run python gerar_etiquetas.py

# Gerar e enviar ao coordenador de cada campus
uv run python gerar_etiquetas.py --send

# Revisar o que seria enviado sem disparar emails
uv run python gerar_etiquetas.py --send --dry-run

# Salvar em outro diretório
uv run python gerar_etiquetas.py -o output/etiquetas
```

---

## 9. `gerar_placas.py` — Gerar placas de identificação

Lê `output/usuarios.txt` (fonte da verdade gerada por `gerar_arquivos_boca.py`) e os dados das equipes do `equipes_interif.csv`, e gera um PDF de placas de identificação por campus — uma página landscape A4 por equipe, com fundo gradiente colorido. Cada placa exibe o título do evento, os logos, o nome da equipe e o username do BOCA.

### Uso

```bash
uv run python gerar_placas.py [opções]
```

### Opções

| Opção | Atalho | Descrição |
|-------|--------|-----------|
| `--usuarios ARQUIVO` | | Caminho para `usuarios.txt` (padrão: `output/usuarios.txt`) |
| `--csv ARQUIVO` | | CSV de equipes (padrão: `equipes_interif.csv`) |
| `--campi ARQUIVO` | | CSV de siglas de campus (padrão: `assets/ifsp_campi.csv`) |
| `--output DIR` | `-o` | Diretório de saída dos PDFs (padrão: `placas/`) |
| `--send` | `-s` | Envia cada PDF ao coordenador do campus via `gws gmail +send --attach` |
| `--dry-run` | | Gera os PDFs e mostra um preview dos emails no terminal sem chamar o `gws` |

### Exemplos

```bash
# Gerar placas em placas/ sem enviar
uv run python gerar_placas.py

# Gerar e enviar ao coordenador de cada campus
uv run python gerar_placas.py --send

# Revisar o que seria enviado sem disparar emails
uv run python gerar_placas.py --send --dry-run

# Salvar em outro diretório
uv run python gerar_placas.py -o output/placas
```

---

## `config.py` — Configuração da edição

**Edite este arquivo a cada edição do InterIF.** Centraliza todas as constantes que variam de um ano para o outro, evitando que fiquem espalhadas pelos scripts.

| Constante | Usada em | Descrição |
|-----------|----------|-----------|
| `TITULO_EVENTO` | todos | Nome completo do evento (ex.: `"IX InterIF — Fase Local"`) |
| `EMAIL_INTERIF` | `cpf_check`, `inscricoes_atuais`, `enviar_credenciais` | Email da organização |
| `SALT` / `SECRET_GERAL` | `gerar_arquivos_boca` | Segredos BOCA |
| `COORD_SUBJECT` / `COORD_PRE` / `COORD_POST` | `inscricoes_atuais` | Email para coordenadores de campus |
| `RESP_SUBJECT` / `RESP_PRE` / `RESP_POST` | `inscricoes_atuais` | Email para técnicos responsáveis |
| `SUMMARY_SUBJECT` / `SUMMARY_PRE` / `SUMMARY_POST` | `inscricoes_atuais` | Email de resumo de inscrições |
| `NO_TEAMS_SUBJECT` / `NO_TEAMS_BODY` | `inscricoes_atuais` | Email para coordenadores de campi sem equipes |
| `NOTIFY_SUBJECT` / `NOTIFY_BODY` | `cpf_check` | Notificação de CPF inválido |
| `CRED_SUBJECT_PREFIX` | `enviar_credenciais` | Prefixo do assunto dos emails de credenciais |
| `ETIQ_FONTE_MONO` | `gerar_etiquetas` | Nome do arquivo de fonte monospaced (em `assets/`) |
| `ETIQ_SUBJECT` | `gerar_etiquetas` | Assunto do email com as etiquetas em anexo |
| `ETIQ_BODY_TEMPLATE` | `gerar_etiquetas` | Corpo do email (placeholders: `{nome}`, `{campus}`) |
| `PLACA_TITULO_LINHA1` | `gerar_placas` | Primeira linha do cabeçalho da placa (ex.: `"IX MARATONA DE PROGRAMAÇÃO"`) |
| `PLACA_TITULO_LINHA2` | `gerar_placas` | Segunda linha do cabeçalho da placa (ex.: `"INTERIF"`) |
| `PLACA_DATA_EVENTO` | `gerar_placas` | Texto da faixa inferior com data/local (ex.: `"Fase Local, 20 de Junho de 2026"`) |
| `PLACA_FONTE_TITULO` | `gerar_placas` | Arquivo de fonte decorativa do cabeçalho (em `assets/`) |
| `PLACA_FONTE_NOME` | `gerar_placas` | Arquivo de fonte fina para o nome do campus (em `assets/`) |
| `PLACA_FONTE_NOME_BOLD` | `gerar_placas` | Arquivo de fonte bold para o nome da equipe (em `assets/`) |
| `PLACA_SUBJECT` | `gerar_placas` | Assunto do email com as placas em anexo |
| `PLACA_BODY_TEMPLATE` | `gerar_placas` | Corpo do email (placeholders: `{nome}`, `{campus}`) |

Os textos de `*_PRE` aceitam placeholders preenchidos em runtime: `{nome}` (primeiro nome do destinatário) e `{campus}` (apenas em `COORD_PRE`). Os textos de `NOTIFY_BODY` aceitam `{nome}`, `{cpf}` e `{interif_email}`. Os templates `ETIQ_BODY_TEMPLATE` e `PLACA_BODY_TEMPLATE` aceitam `{nome}` e `{campus}`.

---

## Módulos compartilhados

### `interif_core.py`

Núcleo importado por todos os scripts que lidam com dados de equipes. Contém apenas stdlib (`csv`, `dataclasses`, `pathlib`, `re`, `secrets`) e expõe:

- Constantes estruturais do BOCA (`TEAM_USERNUMBER_START`, `TEAM_BLOCK_SIZE`, `PASSWORD_ALPHABET`, etc.) — não mudam a cada edição
- `CredencialEquipe` — dataclass com todos os campos de uma equipe (credenciais + contatos)
- `load_campi(path)` — lê `assets/ifsp_campi.csv` → `{nome_campus: sigla}`
- `load_teams(path)` — lê `equipes_interif.csv` → lista de dicts
- `validate(teams, campi)` → `list[str]` de erros (vazia se tudo OK)
- `gerar_credenciais(teams, campi)` → `(list[CredencialEquipe], list[dict])`
- `parse_usuarios(path)` — lê `usuarios.txt` → lista de dicts `{username, password, fullname}`
- `enriquecer(usuarios, teams_csv, campi)` — junta credenciais com dados de email do CSV

---

## Diretório `assets/`

Contém arquivos de dados e recursos estáticos usados pelos scripts:

| Arquivo | Descrição |
|---------|-----------|
| `ifsp_campi.csv` | Mapeamento `campus → sigla` dos campi do IFSP |
| `logo.png` | Logo do InterIF (usado nas etiquetas) |
| `IFSP_Logo.jpg` | Logo institucional do IFSP (usado nas placas) |
| `DejaVuSansMono.ttf` | Fonte monospaced para username/password nas etiquetas |
| `DK Bocadillo.ttf` | Fonte decorativa usada nas placas |
| `AccanthisADFStd-Regular.ttf` | Fonte auxiliar das placas |
| `AccanthisADFStdNo3-Bold.ttf` | Fonte auxiliar bold das placas |

### `assets/ifsp_campi.csv`

Lista todos os campi do IFSP com suas respectivas siglas. **Deve ser atualizada a cada edição** para refletir eventuais novos campi ou alterações de sigla.

A lista oficial de campi está disponível em: <https://www.ifsp.edu.br/sobre-o-campus>

Formato do arquivo:

```csv
campus,sigla
Campus Araraquara,ARQ
Campus São Paulo,SPO
…
```
