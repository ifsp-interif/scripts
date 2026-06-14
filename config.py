"""
Constantes específicas da edição — edite este arquivo a cada ano/fase.

Importado por todos os scripts InterIF; sem dependências externas.
"""

# ── Identidade do evento ──────────────────────────────────────────────────────

TITULO_EVENTO = "IX InterIF — Fase Local"
EMAIL_INTERIF = "interif@ifsp.edu.br"
DATA_EVENTO = "2026-06-20"

# ── BOCA ──────────────────────────────────────────────────────────────────────

SALT = "salt"
SECRET_GERAL = "geral_abc"

# ── Emails de confirmação de inscrição (inscricoes_atuais.py) ────────────────
# Placeholders disponíveis:  {nome}, {campus}  (preenchidos em runtime)

BANNER = " Esta é uma mensagem automática ".center(72, "*") + "\n\n"

COORD_SUBJECT = f"Equipes do {TITULO_EVENTO} inscritas no seu campus"
COORD_PRE = (
    BANNER
    + "Olá, {nome}!\n\n"
    + f"Seguem abaixo as equipes inscritas no {TITULO_EVENTO} pelo campus {{campus}}:\n"
)
COORD_POST = (
    f"\nEm caso de dúvidas ou necessidade de alteração, entre em contato com a organização.\n\n"
    f"Atenciosamente,\n"
    f"Organização {TITULO_EVENTO}"
)

RESP_SUBJECT = f"Suas equipes inscritas no {TITULO_EVENTO}"
RESP_PRE = (
    BANNER
    + "Olá, {nome}!\n\n"
    + f"Seguem abaixo as equipes sob sua responsabilidade inscritas no {TITULO_EVENTO}:\n"
)
RESP_POST = (
    f"\nEm caso de dúvidas ou necessidade de alteração, entre em contato com a organização.\n\n"
    f"Atenciosamente,\n"
    f"Organização {TITULO_EVENTO}"
)

SUMMARY_SUBJECT = f"Resumo de inscrições — {TITULO_EVENTO}"
SPECIAL_SUMMARY_SUBJECT = f"Quadro resumo de equipes especiais — {TITULO_EVENTO}"
SUMMARY_PRE = BANNER + "Seguem abaixo os totais de equipes inscritas por campus:\n"
SUMMARY_POST = "\nEste é um email automático gerado ao final do envio das confirmações."

NO_TEAMS_SUBJECT = f"Inscrições de equipes no {TITULO_EVENTO}"
NO_TEAMS_BODY = (
    BANNER
    + "Olá, {nome}!\n\n"
    + f"Identificamos que o campus {{campus}} ainda não possui equipes inscritas no {TITULO_EVENTO}.\n\n"
    + "Em caso de dúvidas ou necessidade de apoio, entre em contato com a organização.\n\n"
    + "Lembramos que o prazo final de inscrição é 2026-06-08\n\n"
    + "Atenciosamente,\n"
    + f"Organização {TITULO_EVENTO}"
)

# ── Notificação de CPF inválido (cpf_check.py) ────────────────────────────────
# Placeholders disponíveis: {nome}, {cpf}, {interif_email}  (preenchidos em runtime)

NOTIFY_SUBJECT = f"Atualização de CPF — {TITULO_EVENTO}"
NOTIFY_BODY = (
    BANNER
    + "Olá, {nome}!\n\n"
    + f"Identificamos que o CPF {{cpf}} registrado para você no {TITULO_EVENTO} é inválido.\n\n"
    + "Por favor, envie seu CPF correto para {interif_email} o mais breve possível "
    + "para garantir sua participação no evento.\n\n"
    + "Atenciosamente,\n"
    + f"Organização {TITULO_EVENTO}"
)

# ── Participante em múltiplas equipes (duplicatas_participantes.py) ───────────
# Placeholders: {nome}, {criterio}, {equipes_detalhe}  (preenchidos em runtime)

DUPLICATA_SUBJECT = f"[ATENÇÃO] Participante em múltiplas equipes — {TITULO_EVENTO}"
DUPLICATA_BODY = (
    BANNER
    + "Prezados,\n\n"
    + f"Durante a verificação das inscrições do {TITULO_EVENTO}, identificamos que "
    + "o(a) participante **{nome}** consta inscrito(a) em mais de uma equipe "
    + "(critério de detecção: {criterio}).\n\n"
    + "Equipes em que o(a) participante aparece:\n\n"
    + "{equipes_detalhe}\n\n"
    + "Pedimos que respondam este e-mail informando qual é a equipe correta em que "
    + "o(a) participante deve permanecer, para que possamos corrigir as inscrições.\n\n"
    + "Atenciosamente,\n"
    + f"Organização {TITULO_EVENTO}"
)

# ── Credenciais de acesso (enviar_credenciais.py) ─────────────────────────────

CRED_SUBJECT_PREFIX = f"Credenciais de acesso — {TITULO_EVENTO}"

# ── Etiquetas de credenciais (gerar_etiquetas.py) ────────────────────────────────
# Fonte monospaced usada para username/password. O arquivo deve existir em assets/.

ETIQ_FONTE_MONO = "DejaVuSansMono.ttf"
ETIQ_SUBJECT = f"Etiquetas de credenciais — {TITULO_EVENTO}"
ETIQ_BODY_TEMPLATE = (
    BANNER
    + "Olá, {nome}!\n\n"
    + "Segue em anexo as etiquetas de credenciais das equipes do campus {campus} "
    + f"para o {TITULO_EVENTO}.\n\n"
    + f"Atenciosamente,\nOrganização {TITULO_EVENTO}"
)

ETIQ_COACH_SUBJECT = f"Etiquetas de credenciais da(s) sua(s) equipe(s) — {TITULO_EVENTO}"
ETIQ_COACH_BODY_TEMPLATE = (
    BANNER
    + "Olá, {nome}!\n\n"
    + "Segue em anexo as etiquetas de credenciais da(s) equipe(s) sob sua responsabilidade "
    + "no campus {campus} "
    + f"para o {TITULO_EVENTO}.\n\n"
    + f"Atenciosamente,\nOrganização {TITULO_EVENTO}"
)

# ── Placas de identificação (gerar_placas.py) ────────────────────────────────
# Placeholders em PLACA_BODY_TEMPLATE: {nome}, {campus}  (preenchidos em runtime)

PLACA_TITULO_LINHA1 = "IX MARATONA DE PROGRAMAÇÃO"  # linha maior no cabeçalho
PLACA_TITULO_LINHA2 = "INTERIF"  # linha menor no cabeçalho
PLACA_DATA_EVENTO = "Fase Local, 20 de Junho de 2026"
PLACA_FONTE_TITULO = "DK Bocadillo.ttf"  # fonte decorativa do cabeçalho
PLACA_FONTE_NOME = "AccanthisADFStd-Regular.ttf"  # campus (linha fina)
PLACA_FONTE_NOME_BOLD = "AccanthisADFStdNo3-Bold.ttf"  # nome da equipe (negrito)
PLACA_SUBJECT = f"Placas das equipes — {TITULO_EVENTO}"
PLACA_BODY_TEMPLATE = (
    "Olá, {nome}!\n\n"
    "Seguem em anexo as placas de identificação das equipes do campus {campus} "
    f"para o {TITULO_EVENTO}.\n\n"
    f"Atenciosamente,\nOrganização {TITULO_EVENTO}"
)

# ── Lista de presença (gerar_lista_presenca.py) ──────────────────────────────
# Placeholders em LISTA_BODY_TEMPLATE: {nome}, {campus}, {data_limite}.
# Número de linhas de assinatura reservadas para os técnicos do campus.

LISTA_PRAZO_DIAS = 7  # dias após DATA_EVENTO para envio da lista digitalizada
LISTA_TECNICOS_LINHAS = 3
LISTA_SUBJECT = f"Lista de presença — {TITULO_EVENTO}"
LISTA_BODY_TEMPLATE = (
    BANNER
    + "Olá, {nome}!\n\n"
    + "Segue em anexo a lista de presença das equipes do campus {campus} "
    + f"para o {TITULO_EVENTO}.\n\n"
    + "Por favor, imprima a lista, colete as assinaturas dos participantes no dia do "
    + "evento e, após o término, digitalize e envie para "
    + f"{EMAIL_INTERIF} até {{data_limite}}.\n\n"
    + f"Atenciosamente,\nOrganização {TITULO_EVENTO}"
)
