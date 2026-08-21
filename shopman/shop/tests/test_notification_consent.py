"""Consentimento × aviso do pedido — os três estados, com DEBUG desligado.

Dois defeitos moravam na mesma função (`_filter_backend_chain`), em direções
opostas, e a suíte não via nenhum dos dois:

1. **O botão que desligava o WhatsApp não desligava o WhatsApp.** Depois de
   filtrar por consentimento, o código fazia `if origin == "whatsapp":
   allowed_channels.add("whatsapp")`. Como o login principal da loja é o link de
   acesso por WhatsApp, todo cliente logado carrega `origin_channel="whatsapp"`
   — então o opt-out gravado pela tela de Preferências era desfeito na linha
   seguinte.

2. **"Avisamos você" era falso para todo cliente novo.** O consentimento só
   nasce em `/conta/preferencias`, desligado nos quatro canais, e o fluxo de
   compra não passa por lá — a cadeia ficava vazia e nem o `order_received`
   saía, enquanto o acompanhamento promete seis vezes que a loja avisa.

Por que a suíte não pegou: os testes vizinhos rodavam com o fallback de console
(`DEBUG=1`), que devolve `["console"]` quando nada é permitido e faz a entrega
"dar certo". Todo teste aqui fixa `settings.DEBUG = False` de propósito.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from shopman.guestman import ConsentService
from shopman.guestman.models import Customer

pytestmark = pytest.mark.django_db


def _order(**overrides):
    order = MagicMock()
    order.ref = overrides.get("ref", "ORD-CONSENT")
    order.total_q = 5000
    order.status = "new"
    order.channel_ref = overrides.get("channel_ref", "web")
    order.handle_type = overrides.get("handle_type", "phone")
    order.handle_ref = overrides.get("handle_ref", "+5543999001122")
    order.data = overrides.get("data", {})
    order.snapshot = {"items": [], "data": {}}
    return order


def _customer(ref="CLI-CONSENT", phone="+5543999001122"):
    return Customer.objects.create(ref=ref, first_name="Ana", phone=phone)


def _deliver(order, template="order_ready", chain=("manychat",), payload=None):
    """Executa a cadeia com os backends disponíveis e devolve quem foi chamado."""
    from shopman.shop.services import notification as notification_svc

    backend = SimpleNamespace(is_available=lambda: True)
    payload = payload if payload is not None else {"order_ref": order.ref}
    with patch.object(notification_svc, "_resolve_backend_chain", return_value=list(chain)):
        with patch("shopman.shop.notifications.get_backend", return_value=backend):
            with patch.object(
                notification_svc,
                "notify",
                return_value=SimpleNamespace(success=True, error=None),
            ) as mock_notify:
                success, error = notification_svc.deliver_order_notification(
                    order, template, payload
                )
    used = [call.kwargs.get("backend") for call in mock_notify.call_args_list]
    return success, error, used


def test_revogado_vence_a_origem_whatsapp(settings):
    """O defeito medido: opt-out gravado + origin whatsapp continuava mandando."""
    settings.DEBUG = False
    customer = _customer()
    ConsentService.revoke_consent(customer.ref, "whatsapp")

    order = _order(
        data={
            "customer_ref": customer.ref,
            "origin_channel": "whatsapp",
            "customer": {"name": "Ana", "phone": customer.phone},
        }
    )
    success, error, used = _deliver(order, template="order_ready", chain=("manychat",))

    assert used == [], "o canal revogado voltou pela porta da origem"
    assert success is False
    assert error == "no active notification channel available"


def test_revogado_vence_ate_o_handle_manychat(settings):
    """Nem o pedido que nasceu DENTRO do WhatsApp escapa do opt-out."""
    settings.DEBUG = False
    customer = _customer()
    ConsentService.revoke_consent(customer.ref, "whatsapp")

    order = _order(
        handle_type="manychat",
        handle_ref="sub-123",
        data={
            "customer_ref": customer.ref,
            "origin_channel": "whatsapp",
            "customer": {"name": "Ana", "phone": customer.phone},
        },
    )
    _, _, used = _deliver(order, chain=("manychat",))
    assert used == []


def test_sem_registro_o_aviso_do_pedido_sai(settings):
    """Cliente que nunca abriu Preferências continua sendo avisado do pedido."""
    settings.DEBUG = False
    customer = _customer()
    assert ConsentService.get_consents(customer.ref) == []

    order = _order(
        data={
            "customer_ref": customer.ref,
            "origin_channel": "web",  # "Usar outro número": nem a origem salva
            "customer": {"name": "Ana", "phone": customer.phone},
        }
    )
    success, error, used = _deliver(order, chain=("manychat",))

    assert used == ["manychat"]
    assert success is True
    assert error is None


@pytest.mark.parametrize(
    "template",
    ["order_received", "payment_requested", "order_ready", "payment_failed"],
)
def test_os_quatro_templates_criticos_saem_sem_registro(settings, template):
    """Nem `order_received` escapava: a cadeia vinha vazia para todos."""
    settings.DEBUG = False
    customer = _customer()
    order = _order(
        data={
            "customer_ref": customer.ref,
            "origin_channel": "web",
            "customer": {"name": "Ana", "phone": customer.phone},
        }
    )
    success, _, used = _deliver(order, template=template, chain=("manychat",))
    assert used == ["manychat"], f"{template} não saiu"
    assert success is True


def test_revogar_um_canal_nao_derruba_os_outros(settings):
    """Desligar o WhatsApp não pode calar o SMS: a régua é por canal."""
    settings.DEBUG = False
    customer = _customer()
    ConsentService.revoke_consent(customer.ref, "whatsapp")

    order = _order(
        data={
            "customer_ref": customer.ref,
            "origin_channel": "whatsapp",
            "customer": {"name": "Ana", "phone": customer.phone},
        }
    )
    _, _, used = _deliver(order, chain=("manychat", "sms"))
    assert used == ["sms"]


def test_a_tela_de_preferencias_grava_o_desligado(settings):
    """Mexer numa chave grava as quatro — "desligado" vira opt-out de verdade.

    Sem isto o roteamento transacional não teria como distinguir a chave que a
    pessoa deixou desligada da chave que ela nunca viu, e a tela mostraria "não"
    para um canal que o sistema trataria como permissão.
    """
    settings.DEBUG = False
    from shopman.shop.services import account as account_service

    customer = _customer()
    enabled = account_service.toggle_notification_consent(customer.ref, "email")

    assert enabled == {"email"}
    gravados = {c.channel: c.status for c in ConsentService.get_consents(customer.ref)}
    assert gravados["email"] == "opted_in"
    for channel in ("whatsapp", "sms", "push"):
        assert gravados[channel] == "opted_out", channel

    order = _order(
        data={
            "customer_ref": customer.ref,
            "origin_channel": "whatsapp",
            "customer": {"name": "Ana", "phone": customer.phone, "email": "ana@example.com"},
        }
    )
    _, _, used = _deliver(order, chain=("manychat", "email"))
    assert used == ["email"]


def test_leitura_de_consentimento_falha_e_o_canal_cala(settings):
    """Se não dá para saber, não manda: o fallback protege o consentimento."""
    settings.DEBUG = False
    customer = _customer()

    order = _order(
        data={
            "customer_ref": customer.ref,
            "customer": {"name": "Ana", "phone": customer.phone},
        }
    )
    with patch(
        "shopman.shop.projections.customer_context.revoked_notification_channels",
        side_effect=RuntimeError("banco fora"),
    ):
        _, _, used = _deliver(order, chain=("manychat",))
    assert used == []


def test_pedido_sem_cliente_conhecido_nao_e_filtrado(settings):
    """Balcão/iFood sem `customer_ref`: a cadeia do canal vale como está."""
    settings.DEBUG = False
    order = _order(data={"customer": {"name": "Balcão", "phone": "+5543999887766"}})
    _, _, used = _deliver(order, chain=("manychat",))
    assert used == ["manychat"]
