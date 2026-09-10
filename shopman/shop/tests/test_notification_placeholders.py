"""Nenhum ``{placeholder}`` cru chega ao cliente.

Campo, 01/09: um pedido real da loja recebeu a régua de avisos por **SMS** e as
mensagens saíram com ``{customer_name_greeting}`` e ``{tracking_url}`` literais na
tela do cliente. Duas causas, ambas estruturais:

1. as chaves auxiliares eram derivadas SÓ dentro do adapter do ManyChat, e SMS,
   e-mail e WhatsApp leem o MESMO texto do Admin (``NotificationTemplate``);
2. ``tracking_url`` só existia quando o pedido carregava ``customer.uuid`` (magic
   link do doorman) — e o checkout da loja nunca grava esse uuid, então a chave
   simplesmente não existia no contexto.

A política de renderização é deliberada e não muda: chave ausente vai literal em
vez de suprimir o aviso (``SafeFormatMap``). Por isso o conserto é do lado da
PRODUÇÃO das chaves, e o guardrail abaixo é o formato que impede a recaída: ele
varre os textos semeados (os que o lojista recebe no Admin) e os fallbacks de cada
canal, e falha se algum evento de pedido usar chave que o contexto não produz.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.test import override_settings

from shopman.shop.adapters import notification_email, notification_manychat, notification_sms
from shopman.shop.adapters._notification_templates import derive_context
from shopman.shop.services.notification import _build_context

COMTELE_SETTINGS = {"api_key": "key-1", "route": "17", "timeout": 5}

#: O corpo semeado de `order_received` — o texto que a Joyce recebeu.
SEEDED_ORDER_RECEIVED = (
    "Olá{customer_name_greeting}! Recebemos seu pedido *{order_ref}*. "
    "O estabelecimento vai conferir a disponibilidade. Acompanhe por aqui: {tracking_url}"
)

_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


def _order(*, name: str = "Joyce", uuid: str | None = None):
    """Pedido da LOJA: cliente identificado por telefone, SEM `customer.uuid`.

    É o formato real — `CheckoutView` monta `session.data["customer"]` com
    `ref`/`price_tier`/`name`/`phone` e o `CommitService` copia isso para o pedido.
    """
    customer: dict = {"name": name, "phone": "+5543999990001", "ref": "CLI-1"}
    if uuid:
        customer["uuid"] = uuid
    order = MagicMock()
    order.ref = "ORD-1"
    order.total_q = 5600
    order.status = "new"
    order.data = {"customer": customer, "fulfillment_type": "pickup"}
    order.snapshot = {"items": []}
    return order


# ══════════════════════════════════════════════════════════════════════
# 1. O bug de campo, pinado por canal
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
@override_settings(SHOPMAN_SMS=COMTELE_SETTINGS, SHOPMAN_STOREFRONT_BASE_URL="")
def test_sms_de_pedido_sai_com_nome_e_link_de_acompanhamento():
    """O caso da Joyce: SMS com o texto do Admin, cliente nomeado, sem magic link."""
    from shopman.shop.models import NotificationTemplate

    NotificationTemplate.objects.create(
        event="order_received",
        subject="Pedido {order_ref} recebido",
        body=SEEDED_ORDER_RECEIVED,
        is_active=True,
    )

    context = _build_context(_order(), {"order_ref": "ORD-1"}, "order_received")
    message = notification_sms._build_message("order_received", context)

    assert "Joyce" in message
    assert "/pedido/ORD-1" in message
    assert "{" not in message, f"placeholder cru no SMS: {message!r}"


@pytest.mark.django_db
@override_settings(SHOPMAN_STOREFRONT_BASE_URL="")
def test_email_e_whatsapp_recebem_as_mesmas_chaves_que_o_sms():
    """A derivação vale para TODOS os canais — não só para o que a tinha em casa."""
    from shopman.shop.models import NotificationTemplate

    NotificationTemplate.objects.create(
        event="order_received",
        subject="Olá{customer_name_greeting}, pedido {order_ref}",
        body=SEEDED_ORDER_RECEIVED,
        is_active=True,
    )
    context = _build_context(_order(), {"order_ref": "ORD-1"}, "order_received")

    sent: dict = {}

    def fake_send_mail(**kwargs):
        sent.update(kwargs)

    with patch("shopman.shop.adapters.notification_email.send_mail", side_effect=fake_send_mail):
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"):
            assert notification_email.send("joyce@example.com", "order_received", context) is True

    assert "Joyce" in sent["subject"]
    assert "{" not in sent["subject"], f"placeholder cru no assunto: {sent['subject']!r}"
    assert "Joyce" in sent["message"]
    assert "{" not in sent["message"], f"placeholder cru no corpo: {sent['message']!r}"

    whatsapp = notification_manychat._build_message("order_received", context)
    assert "Joyce" in whatsapp
    assert "{" not in whatsapp, f"placeholder cru no WhatsApp: {whatsapp!r}"


@override_settings(SHOPMAN_STOREFRONT_BASE_URL="https://loja.test")
def test_tracking_url_cai_no_link_comum_quando_nao_ha_magic_link():
    """Mesmo critério do `payment_url`: link comum é melhor que placeholder cru."""
    context = _build_context(_order(), {"order_ref": "ORD-1"}, "order_received")
    assert context["tracking_url"] == "https://loja.test/pedido/ORD-1"


@override_settings(SHOPMAN_STOREFRONT_BASE_URL="https://loja.test")
def test_falha_no_bloco_de_access_urls_grita_e_cai_no_link_comum():
    """O `except` era `logger.debug` e engoliu exatamente este defeito.

    Um `uuid` gravado torto no pedido rebenta dentro do bloco: antes isso saía só no
    debug e o aviso ia com `{tracking_url}` cru.
    """
    from shopman.shop.services import notification as notification_service

    order = _order(uuid="nao-e-um-uuid")
    with patch.object(notification_service.logger, "warning") as warning:
        context = _build_context(order, {"order_ref": "ORD-1"}, "order_received")

    assert context["tracking_url"] == "https://loja.test/pedido/ORD-1"
    assert warning.called, "a falha de magic link tem de gritar, não sussurrar em debug"
    assert "ORD-1" in warning.call_args.args, "o grito tem de nomear o pedido"


@override_settings(SHOPMAN_STOREFRONT_BASE_URL="https://loja.test")
def test_token_indisponivel_ainda_entrega_link_de_acompanhamento():
    """Cunhagem de token fora do ar não pode virar `{tracking_url}` na tela."""
    order = _order(uuid="6f9619ff-8b86-d011-b42d-00c04fc964ff")
    with patch(
        "shopman.doorman.services.access_link.AccessLinkService.create_token",
        side_effect=RuntimeError("token store fora do ar"),
    ):
        context = _build_context(order, {"order_ref": "ORD-1"}, "order_received")

    assert context["tracking_url"] == "https://loja.test/pedido/ORD-1"
    assert context["payment_url"] == "https://loja.test/pedido/ORD-1"


def test_derive_context_e_idempotente():
    once = derive_context({"customer_name": "Joyce", "tracking_url": "https://loja.test/pedido/ORD-1"})
    twice = derive_context(once)
    assert once == twice
    assert once["customer_name_greeting"] == ", Joyce"
    assert once["tracking_suffix"] == "\nAcompanhe: https://loja.test/pedido/ORD-1"


def test_derive_context_suprime_sufixo_sem_dado():
    ctx = derive_context({})
    assert ctx["customer_name_greeting"] == ""
    assert ctx["tracking_suffix"] == ""
    assert ctx["reorder_suffix"] == ""
    assert ctx["courier_tracking_suffix"] == ""
    assert ctx["pix_suffix"] == ""
    assert ctx["reason_note"] == ""


# ══════════════════════════════════════════════════════════════════════
# 2. Guardrail: toda chave usada num texto de PEDIDO tem que ser produzida
# ══════════════════════════════════════════════════════════════════════

#: Eventos servidos por `services/notification._build_context` (fluxo de pedido).
#: Os demais (produção, compras, estoque, campanha) recebem contexto montado pelo
#: emissor e estão fora do alcance deste guardrail.
_ORDER_EVENT_PREFIXES = ("order_", "payment_", "waitlist_", "preorder_", "loyalty_")


def _is_order_event(event: str) -> bool:
    return event.startswith(_ORDER_EVENT_PREFIXES)


def _seeded_bodies() -> dict[str, str]:
    """Os textos que o lojista recebe no Admin, lidos do seed por AST.

    Lidos da FONTE, não do banco: o guardrail tem de rodar sem seed e falhar no PR
    que introduz a chave, não no dia em que o cliente recebe a mensagem.
    """
    source = Path(settings.BASE_DIR) / "config" / "management" / "commands" / "seed.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "FALLBACK_TEMPLATES" not in targets:
            continue
        templates = ast.literal_eval(node.value)
        return {event: tpl["subject"] + "\n" + tpl["body"] for event, tpl in templates.items()}
    raise AssertionError("FALLBACK_TEMPLATES não encontrado em config/management/commands/seed.py")


def _produced_keys() -> set[str]:
    """Tudo que o contexto de um pedido oferece a um template."""
    order = _order()
    order.data["payment"] = {"method": "pix", "copy_paste": "0002012..."}
    order.data["courier"] = {"tracking_url": "https://courier.test/x"}
    context = _build_context(order, {"order_ref": "ORD-1", "reason": "sem estoque"}, "order_accepted")
    keys = set(derive_context(context))
    # Só existe com magic link (o pedido da loja não tem `customer.uuid`); é sempre
    # consumido pelo `{reorder_suffix}`, que se auto-suprime.
    keys.add("reorder_url")
    return keys


def _offenders(bodies: dict[str, str], produced: set[str], origin: str) -> list[str]:
    found: list[str] = []
    for event, text in sorted(bodies.items()):
        if not _is_order_event(event):
            continue
        for key in sorted(set(_PLACEHOLDER.findall(text)) - produced):
            found.append(f"{origin}[{event}] usa {{{key}}}")
    return found


def test_textos_semeados_so_usam_chaves_que_o_contexto_produz():
    offenders = _offenders(_seeded_bodies(), _produced_keys(), "seed")
    assert not offenders, (
        "Placeholder sem produtor vai LITERAL para o cliente (política do "
        "SafeFormatMap). Produza a chave em `services/notification._build_context` "
        "ou em `_notification_templates.derive_context`:\n" + "\n".join(offenders)
    )


def test_fallbacks_de_cada_canal_so_usam_chaves_que_o_contexto_produz():
    produced = _produced_keys()
    offenders: list[str] = []
    offenders += _offenders(notification_sms.MESSAGE_TEMPLATES, produced, "sms")
    offenders += _offenders(notification_manychat.MESSAGE_TEMPLATES, produced, "manychat")
    offenders += _offenders(notification_email.BODY_TEMPLATES, produced, "email.body")
    offenders += _offenders(notification_email.SUBJECT_TEMPLATES, produced, "email.subject")
    assert not offenders, "Placeholder sem produtor no fallback do canal:\n" + "\n".join(offenders)


def test_guardrail_encontrou_os_textos():
    """Sanidade: regex/AST quebrados não podem silenciar o guardrail."""
    bodies = _seeded_bodies()
    assert len([e for e in bodies if _is_order_event(e)]) > 10
    assert "customer_name_greeting" in _PLACEHOLDER.findall(bodies["order_received"])
