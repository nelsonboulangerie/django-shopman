"""A nota da loja online: cadastro só com o "sim", e a NFC-e chega digital.

Decisões do dono (25/09/2026):

- guardar o CPF no cadastro é PERGUNTA; grava só lacuna, nunca troca o
  documento e nunca grava documento de outra conta;
- a nota autorizada vai ao cliente da loja pelo aviso de pedido (WhatsApp
  primeiro), com o link da DANFE — o balcão entrega no papel ou no e-mail.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from shopman.guestman.models import Customer
from shopman.orderman.models import Directive, Order

from shopman.shop.services import customer_tax_id

pytestmark = pytest.mark.django_db

CPF = "52998224725"
OUTRO_CPF = "11144477735"


# ── Guardar no cadastro ───────────────────────────────────────────────────


def test_cadastro_sem_documento_recebe_o_cpf():
    ana = Customer.objects.create(ref="ANA", first_name="Ana", phone="+5543999990001")
    assert customer_tax_id.save_to_customer(ana.uuid, "529.982.247-25") == customer_tax_id.SAVED
    ana.refresh_from_db()
    assert ana.document == CPF


def test_igual_ao_cadastro_ja_esta_la():
    ana = Customer.objects.create(ref="ANA", first_name="Ana", phone="+5543999990001", document=CPF)
    outcome = customer_tax_id.save_to_customer(ana.uuid, CPF)
    assert outcome == customer_tax_id.ALREADY_SAVED
    assert customer_tax_id.is_in_profile(outcome)


def test_diferente_do_cadastro_nao_troca():
    ana = Customer.objects.create(ref="ANA", first_name="Ana", phone="+5543999990001", document=CPF)
    outcome = customer_tax_id.save_to_customer(ana.uuid, OUTRO_CPF)
    assert outcome == customer_tax_id.KEPT_EXISTING
    assert not customer_tax_id.is_in_profile(outcome)
    ana.refresh_from_db()
    assert ana.document == CPF


def test_documento_de_outra_conta_nunca_entra():
    Customer.objects.create(ref="JOAO", first_name="João", phone="+5543999990002", document=CPF)
    ana = Customer.objects.create(ref="ANA", first_name="Ana", phone="+5543999990001")
    outcome = customer_tax_id.save_to_customer(ana.uuid, CPF)
    assert outcome == customer_tax_id.OWNED_BY_OTHER
    assert not customer_tax_id.is_in_profile(outcome)
    ana.refresh_from_db()
    assert ana.document == ""
    # Para ela, o documento "está no cadastro": fica como preferência da nota,
    # e o próximo checkout o traz como se fosse do cadastro (nada denuncia a
    # outra conta na próxima visita).
    assert ana.metadata["note_tax_id"] == CPF
    from shopman.shop.projections.delivery_fiscal import FROM_DOCUMENT, delivery_tax_id_prefill

    prefill = delivery_tax_id_prefill(ana.uuid)
    assert (prefill.tax_id, prefill.source) == (CPF, FROM_DOCUMENT)


def test_documento_invalido_ou_sem_cliente_nao_grava():
    ana = Customer.objects.create(ref="ANA", first_name="Ana", phone="+5543999990001")
    assert customer_tax_id.save_to_customer(ana.uuid, "52998224700") == customer_tax_id.NOT_SAVED
    assert customer_tax_id.save_to_customer(None, CPF) == customer_tax_id.NOT_SAVED


# ── A nota autorizada vai ao cliente da loja ─────────────────────────────


def _order(channel_ref: str, **data) -> Order:
    return Order.objects.create(
        ref=f"NF-{channel_ref.upper()}",
        channel_ref=channel_ref,
        status="completed",
        total_q=1600,
        handle_type="phone",
        handle_ref="5543999990001",
        data={
            "customer": {"name": "Ana", "phone": "+5543999990001"},
            "nfce_access_key": "4" * 44,
            "nfce_danfe_url": "https://api.focusnfe.com.br/notas_fiscais_consumidor/NFe1.html",
            **data,
        },
    )


def _note_notifications(order) -> list[Directive]:
    return list(Directive.objects.filter(
        topic="notification.send", payload__order_ref=order.ref, payload__template="fiscal_note_ready",
    ))


def test_nota_autorizada_da_loja_agenda_o_aviso_uma_vez():
    from shopman.shop.handlers.fiscal import NFCeEmitHandler

    order = _order("web")
    handler = NFCeEmitHandler(backend=Mock(spec=[]))
    handler._after_authorized(order)
    handler._after_authorized(order)  # retry da directive: não repete a mensagem
    assert len(_note_notifications(order)) == 1


def test_nota_do_balcao_nao_vira_aviso_de_whatsapp():
    from shopman.shop.handlers.fiscal import NFCeEmitHandler

    order = _order("pdv", receipt={"channels": ["print"]})
    NFCeEmitHandler(backend=Mock(spec=[]))._after_authorized(order)
    assert _note_notifications(order) == []


def test_aviso_leva_o_link_da_danfe(settings):
    from shopman.shop.adapters import notification_manychat
    from shopman.shop.services.notification import _build_context

    settings.SHOPMAN_FOCUS_NFE = {"environment": "producao"}
    order = _order("web")
    ctx = _build_context(order, {"order_ref": order.ref}, "fiscal_note_ready")
    assert ctx["danfe_url"] == "https://api.focusnfe.com.br/notas_fiscais_consumidor/NFe1.html"
    message = notification_manychat._build_message("fiscal_note_ready", ctx)
    assert message == (
        f"A nota fiscal do pedido {order.ref} está pronta: "
        "https://api.focusnfe.com.br/notas_fiscais_consumidor/NFe1.html"
    )


def test_aviso_de_nota_de_homologacao_diz_que_nao_vale(settings):
    from shopman.shop.adapters import notification_manychat
    from shopman.shop.services.notification import _build_context

    settings.SHOPMAN_FOCUS_NFE = {"environment": "homologacao"}
    order = _order("web")
    ctx = _build_context(order, {"order_ref": order.ref}, "fiscal_note_ready")
    assert notification_manychat._build_message("fiscal_note_ready", ctx).endswith(
        "\n(Nota de teste, sem valor fiscal.)"
    )
