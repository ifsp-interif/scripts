# Scripts INTERIF

Scripts Python para organização do InterIF: geração de CSV, validação de CPFs, emails de confirmação de inscrição, geração de arquivos BOCA/NOCA e envio de credenciais de acesso.

## Pré-requisitos

- O CLI [`gws`](https://github.com/googleworkspace/cli) instalado e autenticado com uma conta com acesso às planilhas e ao Gmail (necessário para `equipes_interif.py`, `cpf_check.py`, `inscricoes_atuais.py`, `enviar_mensagem.py` e `enviar_credenciais.py`).
- [`uv`](https://docs.astral.sh/uv/) instalado (gerencia o ambiente virtual e as dependências declaradas em `pyproject.toml`).

```bash
uv sync   # cria o .venv e instala as dependências na primeira vez
```

---

## Fluxo completo

```
equipes_interif.py           ← gera equipes_interif.csv a partir das planilhas
       │
       ├─► lista_cursos.py           ← normaliza nomes de cursos (processo iterativo)
       │         │
       │         └─► verifica_matriculas.py  ← cruza prontuários com alunos matriculados;
       │                   │                    gera matriculados.csv
       │                   │
       │                   └─► lista_cursos.py --enriquecer  ← substitui nomes de cursos
       │                                                         pelos nomes oficiais
       │
       ├─► coach_aluno_email.py      ← detecta coaches com email @aluno.ifsp.edu.br
       │
       ├─► duplicatas_participantes.py ← detecta alunos inscritos em mais de uma equipe
       │
       ├─► cpf_check.py              ← valida CPFs; notifica inválidos por email
       │
       ├─► inscricoes_atuais.py      ← confirma inscrições (emails de boas-vindas)
       │
       ├─► enviar_mensagem.py        ← mala direta genérica com templates Jinja2
       │
       ├─► total_camisetas.py        ← contagem de camisetas por tamanho e campus
       │
       ├─► graficos_equipes.py       ← gera gráficos e lista equipes especiais
       │
       ├─► equipes_html.py           ← gera tabela HTML das equipes (CPFs mascarados)
       │
       ├─► gerar_arquivos_boca.py    ← gera usuarios.txt, INTERIF.toml, score.sep,
       │         │                      secret_interif.toml em output/
       │         │
       │         ├─► enviar_credenciais.py ← envia login/senha por email
       │         │     (lê output/usuarios.txt como fonte da verdade)
       │         │
       │         ├─► gerar_etiquetas.py ← gera etiquetas de credenciais em PDF
       │         │     (lê output/usuarios.txt como fonte da verdade)
       │         │
       │         └─► gerar_placas.py ← gera placas de identificação em PDF
       │               (lê output/usuarios.txt como fonte da verdade)
       │
       └─► gerar_arquivos_noca.py    ← alternativa ao BOCA; gera usuarios_noca.csv
                                        ou usuarios_noca.json
```

```bash
# 1. Gerar o CSV a partir das planilhas
uv run python equipes_interif.py --campi <ID_CAMPI> --teams <ID_EQUIPES>

# 2. Padronizar nomes de cursos (processo iterativo até o agrupamento ficar bom)
uv run python lista_cursos.py --gerar-mapa   # gera cursos_mapa.csv — edite antes de continuar
uv run python lista_cursos.py --aplicar --dry-run
uv run python lista_cursos.py --aplicar

# 3. Verificar situação de matrícula dos participantes
uv run python verifica_matriculas.py --graduacao alunos_grad.csv --medio alunos_medio.csv
uv run python verifica_matriculas.py --graduacao alunos_grad.csv --medio alunos_medio.csv --irregulares

# 3b. Enriquecer nomes de cursos com os nomes oficiais (usa matriculados.csv gerado no passo 3)
uv run python lista_cursos.py --enriquecer --dry-run
uv run python lista_cursos.py --enriquecer

# 4. Verificar coaches com email @aluno.ifsp.edu.br
uv run python coach_aluno_email.py

# 5. Verificar alunos inscritos em mais de uma equipe
uv run python duplicatas_participantes.py
uv run python duplicatas_participantes.py --notificar --dry-run   # revisar antes de enviar
uv run python duplicatas_participantes.py --notificar             # notificar os envolvidos

# 6. Validar os CPFs e corrigir eventuais inválidos
uv run python cpf_check.py --invalidos
uv run python cpf_check.py --notificar --dry-run   # revisar antes de enviar
uv run python cpf_check.py --notificar             # notificar os inválidos

# 7. Enviar os emails de confirmação de inscrição
uv run python inscricoes_atuais.py

# 7b. Mala direta com template Jinja2 (comunicação avulsa)
uv run python enviar_mensagem.py TEMPLATE.j2 --assunto "Assunto" --coordenadores --dry-run

# 8. Verificar pedidos de camiseta
uv run python total_camisetas.py
uv run python total_camisetas.py -o camisetas.md   # exportar como Markdown

# 9. Gerar gráficos e listar equipes especiais (ensino médio, femininas, mistas)
uv run python graficos_equipes.py
uv run python graficos_equipes.py -o especiais.md   # exportar lista como Markdown

# 9b. Gerar tabela HTML das equipes para divulgação
uv run python equipes_html.py
uv run python equipes_html.py -o equipes.html

# 10. Gerar os arquivos de configuração do BOCA
uv run python gerar_arquivos_boca.py
# ou, em ambiente de teste:
uv run python gerar_arquivos_boca.py --dry-run

# 10b. Alternativa: gerar arquivo de importação para o NOCA
uv run python gerar_arquivos_noca.py
uv run python gerar_arquivos_noca.py --formato json

# 11. Enviar credenciais de acesso por email
uv run python enviar_credenciais.py --dry-run      # revisar antes de enviar
uv run python enviar_credenciais.py                # disparar os emails

# 12. Gerar etiquetas de credenciais (uma por equipe, agrupadas por campus)
uv run python gerar_etiquetas.py --dry-run            # gera PDFs, simula envio
uv run python gerar_etiquetas.py                      # gera PDFs em etiquetas/
uv run python gerar_etiquetas.py --send               # gera PDFs e envia ao coordenador

# 13. Gerar placas de identificação (uma por equipe, agrupadas por campus)
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

## 2. `lista_cursos.py` — Padronizar nomes de cursos

Normaliza a coluna `Nome do curso` do `equipes_interif.csv`, cujo preenchimento livre pelos participantes gera muitas variantes do mesmo curso (diferenças de caixa, abreviações, erros de digitação).

O processo é iterativo: rode `--gerar-mapa`, edite o arquivo gerado até ficar satisfeito com os agrupamentos, rode `--aplicar`. Repita se necessário. Ao final, use `--enriquecer` para substituir os nomes pelos oficiais do sistema acadêmico (requer `matriculados.csv` gerado por `verifica_matriculas.py`).

### Passada 1 — gerar o mapeamento automático

```bash
uv run python lista_cursos.py --gerar-mapa
```

Usa `rapidfuzz` (similaridade mínima de 80) para agrupar nomes parecidos e escolhe automaticamente o nome canônico de cada grupo (o mais frequente; em empate, o mais longo). Gera `cursos_mapa.csv` com duas colunas: `original` e `canonico`, ordenado pelo nome canônico para facilitar a revisão.

**Edite `cursos_mapa.csv`** corrigindo a coluna `canonico` onde o agrupamento automático errou — é comum confundir cursos distintos com nomes similares (ex.: "Técnico em Informática" e "Técnico em Informática para Internet").

### Passada 2 — aplicar as correções

```bash
# Conferir antes de gravar
uv run python lista_cursos.py --aplicar --dry-run

# Gravar as substituições no equipes_interif.csv
uv run python lista_cursos.py --aplicar
```

### Passada 3 — enriquecer com nomes oficiais

Requer `matriculados.csv` gerado por `verifica_matriculas.py`. Busca cada participante pelo prontuário e substitui o nome do curso pelo nome oficial extraído do sistema acadêmico.

```bash
# Conferir antes de gravar
uv run python lista_cursos.py --enriquecer --dry-run

# Gravar as substituições no equipes_interif.csv
uv run python lista_cursos.py --enriquecer
```

### Opções

| Opção | Descrição |
|-------|-----------|
| `--gerar-mapa` | Gera `cursos_mapa.csv` com agrupamento automático |
| `--aplicar` | Aplica `cursos_mapa.csv` ao CSV de equipes |
| `--enriquecer` | Substitui nomes de cursos pelos nomes oficiais de `matriculados.csv` |
| `--dry-run` | (com `--aplicar` ou `--enriquecer`) Lista as substituições sem gravar |
| `--csv ARQUIVO` | CSV de equipes (padrão: `equipes_interif.csv`) |
| `--mapa ARQUIVO` | Arquivo de mapeamento (padrão: `cursos_mapa.csv`) |
| `--matriculados ARQUIVO` | CSV de matriculados (padrão: `matriculados.csv`) |

> `cursos_mapa.csv` é um arquivo derivado e está no `.gitignore`.

---

## 3. `verifica_matriculas.py` — Verificar situação de matrícula

Cruza os prontuários dos participantes inscritos no `equipes_interif.csv` com as listas de alunos matriculados exportadas do sistema acadêmico (uma para graduação, outra para ensino médio). Classifica cada participante como **Regular** (prontuário encontrado na lista de matriculados) ou **Irregular** (prontuário não encontrado).

Também gera `matriculados.csv` com todos os alunos matriculados consolidados, que é consumido pela passada `--enriquecer` do `lista_cursos.py`.

### Uso

```bash
uv run python verifica_matriculas.py --graduacao alunos_grad.csv --medio alunos_medio.csv
```

### Opções

| Opção | Atalho | Descrição |
|-------|--------|-----------|
| `--graduacao ARQUIVO` | | CSV de alunos da graduação (obrigatório) |
| `--medio ARQUIVO` | | CSV de alunos do ensino médio (obrigatório) |
| `--input ARQUIVO` | `-i` | CSV de equipes (padrão: `equipes_interif.csv`) |
| `--matriculados ARQUIVO` | `-m` | CSV consolidado de saída (padrão: `matriculados.csv`) |
| `--output ARQUIVO` | `-o` | Relatório de saída (padrão: `alunos_irregulares.txt`) |
| `--irregulares` | | Exibe apenas participantes com situação Irregular |

### Exemplos

```bash
# Relatório completo (regulares e irregulares)
uv run python verifica_matriculas.py --graduacao alunos_grad.csv --medio alunos_medio.csv

# Apenas os irregulares
uv run python verifica_matriculas.py --graduacao alunos_grad.csv --medio alunos_medio.csv --irregulares

# Salvar relatório em outro arquivo
uv run python verifica_matriculas.py --graduacao alunos_grad.csv --medio alunos_medio.csv -o relatorio.txt
```

---

## 4. `duplicatas_participantes.py` — Detectar alunos em múltiplas equipes

Lê o `equipes_interif.csv` e verifica se algum aluno (participante 1, 2 ou 3) está inscrito em mais de uma equipe, usando **e-mail** e **CPF** como critérios de identificação independentes. Coaches não são verificados, pois podem ser responsáveis por múltiplas equipes.

Quando o mesmo aluno é detectado por ambos os critérios, os conflitos são mesclados em uma única notificação.

### Uso

```bash
uv run python duplicatas_participantes.py [ARQUIVO] [opções]
```

`ARQUIVO` é opcional; o padrão é `equipes_interif.csv` no mesmo diretório do script.

### Opções

| Opção | Atalho | Descrição |
|-------|--------|-----------|
| `--notificar` | `-n` | Envia email para todos os envolvidos em cada conflito |
| `--dry-run` | | Mostra um preview dos emails no terminal sem chamar o `gws` (requer `--notificar`) |

### Emails de notificação (`--notificar`)

Para cada aluno detectado em mais de uma equipe, o script envia uma mensagem via `gws gmail +send` com:

- **Para (`--to`):** `EMAIL_INTERIF` (`config.py`)
- **Cópia (`--cc`):** o aluno, os coaches de todas as equipes envolvidas e os coordenadores locais de todos os campi envolvidos (deduplicados)

O email informa o critério de detecção (e-mail, CPF ou ambos), lista todas as equipes em que o aluno aparece e solicita que os envolvidos indiquem a equipe correta.

### Exemplos

```bash
# Listar conflitos no terminal
uv run python duplicatas_participantes.py

# Simular o envio de notificações
uv run python duplicatas_participantes.py --notificar --dry-run

# Enviar notificações de verdade
uv run python duplicatas_participantes.py --notificar
```

---

## 5. `cpf_check.py` — Validar CPFs

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

## 6. `coach_aluno_email.py` — Detectar coaches com email de aluno

Lê o `equipes_interif.csv` e lista todas as equipes cujo coach (responsável) possui endereço de email com domínio `@aluno.ifsp.edu.br`, indicando um possível cadastro incorreto. A saída é ordenada por campus e nome da equipe.

### Uso

```bash
uv run python coach_aluno_email.py
```

### Opções

| Opção | Descrição |
|-------|-----------|
| `--csv ARQUIVO` | CSV de equipes (padrão: `equipes_interif.csv`) |

### Exemplo de saída

```
4 equipe(s) com coach de email @aluno.ifsp.edu.br:

  Campus : Birigui
  Equipe : 404 team not found
  Coach  : Fulano de Tal <fulano@aluno.ifsp.edu.br>
```

---

## 7. `inscricoes_atuais.py` — Enviar emails de confirmação

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

## 8. `enviar_mensagem.py` — Mala direta com template Jinja2

Envia emails personalizados para coordenadores de campus, coaches ou participantes usando um arquivo de template [Jinja2](https://jinja.palletsprojects.com/). Útil para comunicações avulsas que não se encaixam nos fluxos fixos dos outros scripts.

A documentação completa com a lista de variáveis disponíveis no template e exemplos de uso está em **`ENVIAR_MENSAGEM.md`**.

### Uso básico

```bash
uv run python enviar_mensagem.py TEMPLATE.j2 --assunto "ASSUNTO" [AUDIÊNCIA] [--dry-run]
```

É obrigatório informar o template, o assunto e pelo menos uma audiência.

### Opções

| Opção | Descrição |
|-------|-----------|
| `TEMPLATE` | Caminho do arquivo de template Jinja2 (ex: `meu_template.j2`) |
| `--assunto TEXTO` | Assunto do email — também aceita variáveis Jinja2 |
| `--coordenadores` | Envia um email por coordenador de campus |
| `--coaches` | Envia um email por coach (responsável pela equipe) |
| `--participantes` | Envia um email por participante individual |
| `--por-equipe` | Com `--participantes`: um email por equipe (todos os membros copiados) |
| `--csv ARQUIVO` | CSV de equipes a usar (padrão: `equipes_interif.csv`) |
| `--cc EMAIL` | CC opcional para todos os envios |
| `--dry-run` | Imprime os emails sem enviar — use sempre antes do envio real |

### Exemplo

```bash
# Testar template para coordenadores
uv run python enviar_mensagem.py aviso.j2 --assunto "Aviso — {{ evento }}" --coordenadores --dry-run

# Disparar envio real
uv run python enviar_mensagem.py aviso.j2 --assunto "Aviso — {{ evento }}" --coordenadores
```

---

## 9. `total_camisetas.py` — Contagem de camisetas

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

## 10. `graficos_equipes.py` — Gerar gráficos e listar equipes especiais

Lê o `equipes_interif.csv`, gera os gráficos de distribuição das equipes e classifica as equipes em cinco categorias:

1. **Apenas alunos do ensino médio integrado** — composta somente por alunos do EM
2. **Exatamente três mulheres** — equipe com composição totalmente feminina
3. **Exatamente duas mulheres** — equipe mista com maioria feminina
4. **Exatamente uma mulher** — equipe mista com minoria feminina
5. **Demais equipes** — nenhuma das categorias acima

As categorias não são mutuamente exclusivas: uma equipe de ensino médio integralmente feminina aparece em ambos os grupos relevantes.

### Uso

```bash
uv run python graficos_equipes.py [opções]
```

### Opções

| Opção | Atalho | Descrição |
|-------|--------|-----------|
| `--input ARQUIVO` | `-i` | CSV de entrada (padrão: `equipes_interif.csv`) |
| `--output ARQUIVO.md` | `-o` | Salva o resultado em Markdown |
| `--resumo` | - | Gera e envia o quadro resumo por e-mail |
| `--dry-run` | - | Com `--resumo`, imprime o e-mail sem enviar |

### Exemplos

```bash
# Exibir no terminal
uv run python graficos_equipes.py

# Exportar como Markdown
uv run python graficos_equipes.py -o especiais.md
```

---

## 11. `equipes_html.py` — Gerar tabela HTML para divulgação

Converte o `equipes_interif.csv` em uma tabela HTML pronta para publicação. Os CPFs dos participantes são mascarados para proteção de dados pessoais. As equipes são ordenadas por campus e nome da equipe.

### Uso

```bash
uv run python equipes_html.py [opções]
```

### Opções

| Opção | Atalho | Descrição |
|-------|--------|-----------|
| `--input ARQUIVO` | `-i` | CSV de entrada (padrão: `equipes_interif.csv`) |
| `--output ARQUIVO` | `-o` | Arquivo HTML gerado (padrão: `equipes.html`) |

### Exemplos

```bash
# Gerar com nomes padrão
uv run python equipes_html.py

# Salvar em arquivo diferente
uv run python equipes_html.py -o public/equipes.html
```

---

## 12. `gerar_arquivos_boca.py` — Gerar arquivos do BOCA

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

## 13. `gerar_arquivos_noca.py` — Gerar arquivo de importação para o NOCA

Alternativa ao BOCA. Lê `equipes_interif.csv` e `assets/ifsp_campi.csv` e gera um arquivo de importação em lote para o NOCA (contest manager). Cada campus vira um site no NOCA; o campo `site` de cada linha aciona a criação automática do site durante o import.

Funções geradas:

| Função | Descrição |
|--------|-----------|
| `team` | Um por equipe inscrita (email: participante 1) |
| `staff` | Um por campus, username `staff{sigla}` |
| `judge` | Um por técnico/responsável, deduplicado por CPF |
| `user` | `scoreif` (placar) |

### Uso

```bash
uv run python gerar_arquivos_noca.py [CSV] [opções]
```

### Opções

| Opção | Atalho | Descrição |
|-------|--------|-----------|
| `CSV` | | CSV de equipes (padrão: `equipes_interif.csv`) |
| `--output DIR` | `-o` | Diretório de saída (padrão: diretório atual) |
| `--output-file ARQUIVO` | | Nome do arquivo gerado (padrão: `usuarios_noca.csv` ou `usuarios_noca.json`) |
| `--formato {csv,json}` | | Formato de saída (padrão: `csv`) |
| `--campi ARQUIVO` | | CSV de siglas de campus (padrão: `assets/ifsp_campi.csv`) |
| `--sigla` | | Usa sigla do campus no campo `site` |
| `--dry-run` | | Exibe o conteúdo sem gravar |

### Exemplos

```bash
# Gerar CSV de importação
uv run python gerar_arquivos_noca.py

# Gerar em formato JSON
uv run python gerar_arquivos_noca.py --formato json

# Pré-visualizar sem gravar
uv run python gerar_arquivos_noca.py --dry-run
```

---

## 14. `enviar_credenciais.py` — Enviar credenciais de acesso

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

## 15. `gerar_etiquetas.py` — Gerar etiquetas de credenciais

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

## 16. `gerar_placas.py` — Gerar placas de identificação

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
| `EMAIL_INTERIF` | `cpf_check`, `duplicatas_participantes`, `inscricoes_atuais`, `enviar_credenciais` | Email da organização |
| `SALT` / `SECRET_GERAL` | `gerar_arquivos_boca` | Segredos BOCA |
| `COORD_SUBJECT` / `COORD_PRE` / `COORD_POST` | `inscricoes_atuais` | Email para coordenadores de campus |
| `RESP_SUBJECT` / `RESP_PRE` / `RESP_POST` | `inscricoes_atuais` | Email para técnicos responsáveis |
| `SUMMARY_SUBJECT` / `SUMMARY_PRE` / `SUMMARY_POST` | `inscricoes_atuais` | Email de resumo de inscrições |
| `NO_TEAMS_SUBJECT` / `NO_TEAMS_BODY` | `inscricoes_atuais` | Email para coordenadores de campi sem equipes |
| `NOTIFY_SUBJECT` / `NOTIFY_BODY` | `cpf_check` | Notificação de CPF inválido |
| `DUPLICATA_SUBJECT` / `DUPLICATA_BODY` | `duplicatas_participantes` | Notificação de aluno em múltiplas equipes |
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
| `SPECIAL_SUMMARY_SUBJECT` | `graficos_equipes` | Assunto do email de resumo de equipes especiais |

Os textos de `*_PRE` aceitam placeholders preenchidos em runtime: `{nome}` (primeiro nome do destinatário) e `{campus}` (apenas em `COORD_PRE`). Os textos de `NOTIFY_BODY` aceitam `{nome}`, `{cpf}` e `{interif_email}`. O texto de `DUPLICATA_BODY` aceita `{nome}`, `{criterio}` e `{equipes_detalhe}`. Os templates `ETIQ_BODY_TEMPLATE` e `PLACA_BODY_TEMPLATE` aceitam `{nome}` e `{campus}`.

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
