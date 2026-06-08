# enviar_mensagem.py — Manual de uso

Script de mala direta com templates Jinja2. Carrega os dados de `equipes_interif.csv` e
envia um email personalizado para cada coordenador de campus, coach e/ou participante,
com o conteúdo gerado a partir de um arquivo de template.

---

## Uso básico

```bash
python enviar_mensagem.py TEMPLATE --assunto "ASSUNTO" [AUDIÊNCIA] [OPÇÕES]
```

É obrigatório informar o template, o assunto e pelo menos uma audiência.

---

## Argumentos

| Argumento | Descrição |
|---|---|
| `TEMPLATE` | Caminho do arquivo de template Jinja2 (ex: `meu_template.j2`) |
| `--assunto TEXTO` | Assunto do email — também aceita variáveis Jinja2 |
| `--coordenadores` | Envia um email por coordenador de campus |
| `--coaches` | Envia um email por coach (responsável pela equipe) |
| `--participantes` | Envia um email por participante individual |
| `--por-equipe` | Usado com `--participantes`: um email por equipe (todos os membros copiados) |
| `--csv ARQUIVO` | CSV de equipes a usar (padrão: `equipes_interif.csv`) |
| `--cc EMAIL` | CC opcional para todos os envios |
| `--dry-run` | Imprime os emails sem enviar — use sempre antes do envio real |

As flags de audiência podem ser combinadas: `--coaches --participantes` envia para os dois
grupos numa única invocação, usando o mesmo template.

---

## Variáveis disponíveis no template

### Comuns a todos os modos

| Variável | Tipo | Conteúdo |
|---|---|---|
| `nome` | str | Primeiro nome do destinatário |
| `campus` | str | Campus do destinatário |
| `evento` | str | Nome do evento (`IX InterIF — Fase Local`) |
| `email_organizacao` | str | Email da organização (`interif@ifsp.edu.br`) |
| `total_equipes` | int | Número de equipes no contexto |
| `total_participantes` | int | Número total de participantes no contexto |
| `equipes` | lista | Lista de equipes (ver estrutura abaixo) |
| `participantes` | lista | Lista de participantes do contexto (ver abaixo) |

### Específicas por audiência

| Variável | `--coordenadores` | `--coaches` | `--participantes` | `--participantes --por-equipe` |
|---|---|---|---|---|
| `coord_nome` | nome completo do coordenador | `""` | `""` | `""` |
| `coach` | `""` | nome do coach | nome do coach da equipe | nome do coach da equipe |
| `equipe` | `""` | `""` | nome da equipe do participante | nome da equipe |
| `nome` | primeiro nome do coord. | primeiro nome do coach | primeiro nome do participante | nome da equipe |

### Estrutura de cada item em `equipes`

```
equipes[i].nome               Nome da equipe
equipes[i].campus             Campus da equipe
equipes[i].coach              Nome do coach
equipes[i].coach_email        Email do coach
equipes[i].participantes      Lista de participantes da equipe
equipes[i].total_participantes Número de participantes
```

### Estrutura de cada item em `participantes`

```
participantes[i].nome         Nome do participante
participantes[i].email        Email do participante
```

> **Dica:** use o filtro `| length` para obter o tamanho de uma lista no template,
> ou use diretamente `total_equipes` e `total_participantes` que já vêm calculados.

---

## Exemplos de templates

### 1. Equipes inscritas no campus (para coordenadores)

**`template_campus.j2`**
```jinja2
Olá, {{ nome }}!

Seguem as equipes inscritas no {{ evento }} pelo campus {{ campus }}:

{% for eq in equipes %}
Equipe: {{ eq.nome }}
Coach:  {{ eq.coach }}
Participantes:
{% for p in eq.participantes %}  - {{ p.nome }}
{% endfor %}
{% endfor %}
Total: {{ total_equipes }} equipe(s) e {{ total_participantes }} participante(s).

Em caso de dúvidas, entre em contato: {{ email_organizacao }}

Atenciosamente,
Organização {{ evento }}
```

**Linha de comando:**
```bash
python enviar_mensagem.py template_campus.j2 \
  --assunto "Equipes inscritas no {{ evento }} — campus {{ campus }}" \
  --coordenadores \
  --dry-run
```

---

### 2. Equipes sob responsabilidade do coach

**`template_coach.j2`**
```jinja2
Olá, {{ nome }}!

Seguem as equipes sob sua responsabilidade inscritas no {{ evento }}:

{% for eq in equipes %}
▸ {{ eq.nome }} — {{ eq.campus }}
  Participantes ({{ eq.total_participantes }}):
{% for p in eq.participantes %}  • {{ p.nome }} <{{ p.email }}>
{% endfor %}
{% endfor %}
Total: {{ total_equipes }} equipe(s).

Em caso de dúvidas ou necessidade de alteração, entre em contato:
{{ email_organizacao }}

Atenciosamente,
Organização {{ evento }}
```

**Linha de comando:**
```bash
python enviar_mensagem.py template_coach.j2 \
  --assunto "Suas equipes no {{ evento }}" \
  --coaches \
  --dry-run
```

---

### 3. Confirmação de inscrição — um email por equipe (todos copiados)

Envia um único email por equipe. O primeiro participante recebe como destinatário principal;
os demais são copiados automaticamente. `nome` contém o nome da equipe para o cumprimento.

**`template_equipe.j2`**
```jinja2
Olá, equipe {{ nome }}!

A inscrição de vocês no {{ evento }} foi confirmada. Veja os detalhes:

Campus: {{ campus }}
Coach:  {{ coach }}

Participantes:
{% for p in participantes %}  - {{ p.nome }} <{{ p.email }}>
{% endfor %}
Fique atento às comunicações oficiais do evento.
Em caso de dúvidas: {{ email_organizacao }}

Atenciosamente,
Organização {{ evento }}
```

**Linha de comando:**
```bash
python enviar_mensagem.py template_equipe.j2 \
  --assunto "Confirmação de inscrição — equipe {{ equipe }}" \
  --participantes --por-equipe \
  --dry-run
```

---

### 4. Confirmação de inscrição para o participante

**`template_participante.j2`**
```jinja2
Olá, {{ nome }}!

Sua inscrição no {{ evento }} foi confirmada. Veja os detalhes abaixo:

Campus:  {{ campus }}
Equipe:  {{ equipe }}
Coach:   {{ coach }}

Colegas de equipe:
{% for p in participantes %}  - {{ p.nome }}
{% endfor %}

Fique atento às comunicações oficiais do evento.
Em caso de dúvidas: {{ email_organizacao }}

Atenciosamente,
Organização {{ evento }}
```

**Linha de comando:**
```bash
python enviar_mensagem.py template_participante.j2 \
  --assunto "Confirmação de inscrição — {{ evento }}" \
  --participantes \
  --dry-run
```

---

### 4. Aviso de encerramento de inscrições (para coordenadores)

**`template_encerramento.j2`**
```jinja2
Olá, {{ nome }}!

Hoje encerra o período de inscrição das equipes no {{ evento }}.

Até agora, o campus {{ campus }} tem {{ total_equipes }} equipe(s) inscritas{% if total_equipes > 0 %}:

{% for eq in equipes %}  - {{ eq.nome }}
{% endfor %}{% else %}.
{% endif %}
Se ainda houver equipes a inscrever, não deixe para a última hora!

{{ email_organizacao }}

Atenciosamente,
Organização {{ evento }}
```

**Linha de comando:**
```bash
python enviar_mensagem.py template_encerramento.j2 \
  --assunto "Encerramento das inscrições — {{ evento }}" \
  --coordenadores \
  --dry-run
```

---

## Fluxo recomendado

1. **Escreva o template** e teste a renderização localmente com `--dry-run`.
2. **Verifique** se o assunto e o corpo ficaram corretos para todos os destinatários.
3. **Envie para um destinatário de teste** usando `--cc` com seu próprio email e `--dry-run` desligado.
4. **Dispare o envio real** removendo `--dry-run`.

```bash
# 1. Testar renderização
python enviar_mensagem.py template_coach.j2 \
  --assunto "Suas equipes no {{ evento }}" \
  --coaches --dry-run

# 2. Envio real
python enviar_mensagem.py template_coach.j2 \
  --assunto "Suas equipes no {{ evento }}" \
  --coaches
```

---

## Observações

- **Variável inexistente no template:** o script encerra com erro indicando exatamente qual
  variável não foi encontrada. Corrija o template antes de reenviar.
- **Destinatário sem email:** o envio para esse destinatário é ignorado com um aviso; os
  demais continuam normalmente.
- **Múltiplas audiências:** use `--coordenadores --coaches --participantes` em conjunto para
  enviar o mesmo template para todos os grupos de uma vez.
- **`--por-equipe` sem `--participantes`:** a flag é silenciosamente ignorada; só tem efeito
  quando combinada com `--participantes`.
- **CC externo com `--por-equipe`:** o `--cc` informado é somado aos CCs gerados pelos demais
  membros da equipe; todos recebem a cópia.
- **CSV alternativo:** use `--csv outro_arquivo.csv` para testar com um subconjunto de dados
  antes do envio para a base completa.
