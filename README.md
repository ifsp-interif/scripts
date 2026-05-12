# Scripts INTERIF

Dois scripts Python para geração e envio dos emails de confirmação de inscrição do INTERIF. Ambos dependem do CLI `gws` para acesso ao Google Workspace.

## Pré-requisito

O CLI `gws` deve estar instalado e autenticado com uma conta com acesso às planilhas e ao Gmail.

---

## 1. `equipes_interif.py` — Gerar o CSV de equipes

Lê duas planilhas do Google Sheets (inscrições de campi e de equipes), cruza os dados e salva o resultado em `equipes_interif.csv`.

### Uso

```bash
python3 equipes_interif.py --campi <ID_PLANILHA_CAMPI> --teams <ID_PLANILHA_EQUIPES>
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
- Nome e email do Responsável pela Equipe
- Nome e email dos Participantes 1, 2 e 3

Equipes sem coordenador de campus correspondente são listadas no terminal ao final.

---

## 2. `send_emails.py` — Enviar emails de confirmação

Lê o `equipes_interif.csv` e envia três grupos de emails via Gmail:

1. **Coordenadores de campus** — um email por campus com todas as equipes inscritas (incluindo o responsável de cada equipe)
2. **Responsáveis pelas equipes** — um email por responsável com suas equipes
3. **Organização** — um email de resumo com o total de equipes por campus, enviado para `interif@ifsp.edu.br`

O assunto de todos os emails inclui a data e hora de geração (ex.: `até 2026-05-12 13h29min`).

### Uso

```bash
python3 send_emails.py
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
python3 equipes_interif.py --campi <ID_CAMPI> --teams <ID_EQUIPES>

# 2. Revisar o CSV gerado
# (opcional, mas recomendado antes de enviar)

# 3. Enviar os emails
python3 send_emails.py
```
