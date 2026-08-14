"""Curadoria do Admin — o que ESTA loja não mostra (WP-ADM-R1).

Os pacotes de ``packages/`` registram o Admin completo dos seus models, e é assim
que deve ser: eles são genéricos e não sabem quem vai instalá-los. Quem decide o
que aparece é o deployment. Este módulo é esse lugar — um `unregister` explícito,
com o motivo escrito ao lado, em vez de vinte deleções espalhadas dentro do Core.

Duas famílias de tela saem daqui:

**Artefato de sistema.** Tabela que só o código escreve e ninguém lê no Admin
(dedupe, token de login, registro de refs). Manter a tela custa atenção do gestor
e não devolve nada: quando alguém precisa investigar, investiga pelo shell.

**Duplicata de inline.** A tela-mãe já mostra a mesma informação no contexto que
lhe dá sentido — transação embaixo da cobrança, expedição embaixo do pedido. Ler
transação solta, sem a cobrança em volta, não é uma pergunta que alguém faz.

Duas telas que pareciam corte óbvio ficaram, e vale dizer por quê: as
movimentações de caixa continuam de pé porque dinheiro é onde mora fraude e
"todas as sangrias do mês" é pergunta que a tela do turno não responde (o
WP-ADM-6 já as travara como trilha somente-leitura); as referências continuam
porque a ação de renomear em massa é feature viva do Core, com tela de
confirmação e teste próprio.

Nada aqui apaga dado: `unregister` tira a tela, o model e as linhas seguem
intactos. Para trazer uma tela de volta, apague a linha correspondente.
"""

from __future__ import annotations

import logging

from django.apps import apps
from django.contrib import admin

logger = logging.getLogger(__name__)

# (app_label, model_name, motivo) — o motivo é para quem ler daqui a um ano.
HIDDEN_SCREENS: tuple[tuple[str, str, str], ...] = (
    # ── Artefatos de sistema ────────────────────────────────────────────
    ("orderman", "idempotencykey", "infra de dedupe de request; ninguém lê no Admin"),
    ("orderman", "sessionevent", "trilha técnica da sessão; aparece na sessão, em Auditoria"),
    ("doorman", "accesslink", "artefato de login; nasce e expira sozinho"),
    ("doorman", "verificationcode", "código de uso único; nasce e expira sozinho"),
    ("doorman", "customeruser", "ponte user↔cliente; escrita só pelo fluxo de login"),
    ("guestman", "externalidentity", "identidade de provedor externo; escrita pela integração"),
    ("customer_identifiers", "customeridentifier", "identificador técnico do cliente"),
    ("refs", "refsequence", "contador de sequência; escrita só pelo gerador de refs"),
    ("storefront", "customerfavorite", "escrito pelo cliente na loja; leitura vive lá"),
    ("taggit", "tag", "marcadores nascem e são editados nos campos de produto e cliente"),
    # ── Duplicatas de inline (a tela-mãe já mostra) ─────────────────────
    ("payman", "paymenttransaction", "inline em Cobranças"),
    ("orderman", "fulfillment", "inline em Histórico de pedidos"),
    ("customer_loyalty", "loyaltytransaction", "inline em Contas de fidelidade"),
    ("backstage", "operationtaskrun", "inline em Execuções de checklist"),
    ("buyman", "suppliermaterialcost", "inline em Insumos e em Fornecedores"),
    ("guestman", "customeraddress", "inline em Clientes"),
)


def hide_curated_screens() -> None:
    """Tira do Admin as telas que este deployment não mostra.

    Silencioso quando a tela já não existe (app fora do INSTALLED_APPS deste
    deployment) — o estado desejado é justamente esse. Uma entrada que não bate
    com model nenhum, porém, é erro de digitação disfarçado de curadoria: fica
    registrada em log e o teste ``test_admin_curation`` derruba a suíte.
    """
    for app_label, model_name, _reason in HIDDEN_SCREENS:
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            logger.warning(
                "curadoria do Admin: %s.%s não existe (entrada obsoleta?)",
                app_label,
                model_name,
            )
            continue
        try:
            admin.site.unregister(model)
        except admin.sites.NotRegistered:
            continue
