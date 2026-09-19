"""``fiscal_state``: em que pé está a NFC-e, num vocabulário só.

A nota nasce em três pontos (fechamento do PDV, captura do pix/link, conclusão)
e a tela chutava o terceiro para todo pedido — "Fiscal na conclusão" num pix
que emite na captura. Estes testes prendem os cinco estados do contrato
(``not_expected`` | ``queued`` | ``awaiting_payment`` | ``authorized`` |
``failed``), a precedência entre evidência e regra, a leitura em lote, a
pergunta "pedir papel emite?" e o grito da expedição sem nota.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import override_settings
from shopman.orderman.models import Directive, Order

from shopman.backstage.models import OperatorAlert
from shopman.shop.directives import FISCAL_EMIT_NFCE
from shopman.shop.services import fiscal as fiscal_service
from shopman.shop.services.observability import create_operator_alert

pytestmark = pytest.mark.django_db

ALWAYS = "shopman.shop.fiscal_resolvers.always"
ON_REQUEST = "shopman.shop.fiscal_resolvers.on_request_or_tax_id"
ON_RECEIPT = "shopman.shop.fiscal_resolvers.on_requested_receipt"


@pytest.fixture(autouse=True)
def _backend_present():
    """Pool fiscal não-vazio: sem backend, ``emission_expected`` é sempre False."""
    with patch("shopman.shop.services.fiscal.fiscal_pool.get_backend", return_value=object()):
        yield


def _order(ref: str, *, payment: dict | None = None, status: str = "accepted", **extra) -> Order:
    data = {"fulfillment_type": "pickup", "payment": payment or {"method": "cash"}}
    data.update(extra)
    return Order.objects.create(ref=ref, channel_ref="pdv", status=status, total_q=1500, data=data)


# ── Os cinco estados ──────────────────────────────────────────────────────


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=ON_REQUEST)
def test_not_expected_quando_a_regra_diz_nao():
    order = _order("FS-NOT")

    assert fiscal_service.fiscal_state(order) == "not_expected"


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=ALWAYS)
def test_authorized_quando_a_chave_existe():
    order = _order("FS-AUTH", nfce_access_key="3526" + "0" * 40)

    assert fiscal_service.fiscal_state(order) == "authorized"


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=ALWAYS)
def test_awaiting_payment_para_pix_sem_captura():
    """Pix/link emitem na CAPTURA (``lifecycle._on_paid``), não na conclusão."""
    order = _order("FS-PIX", payment={"method": "pix"})

    assert fiscal_service.fiscal_state(order) == "awaiting_payment"


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=ALWAYS)
def test_pix_capturado_sem_chave_ainda_esta_na_fila():
    order = _order("FS-PIX-OK", payment={"method": "pix"})

    with patch("shopman.shop.services.payment.has_sufficient_captured_payment", return_value=True):
        assert fiscal_service.fiscal_state(order) == "queued"


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=ALWAYS)
def test_queued_para_quem_nao_exige_captura_e_ainda_nao_tem_chave():
    """Dinheiro no balcão: a nota sai no fechamento; COD: na conclusão. Nas duas, 'na fila'."""
    assert fiscal_service.fiscal_state(_order("FS-CASH")) == "queued"
    cod = _order("FS-COD", payment={"method": "cash", "collection": "on_delivery"}, fulfillment_type="delivery")
    assert fiscal_service.fiscal_state(cod) == "queued"


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=ALWAYS)
def test_failed_quando_a_directive_morreu():
    order = _order("FS-DIR-FAIL")
    Directive.objects.create(topic=FISCAL_EMIT_NFCE, status="failed", payload={"order_ref": order.ref})

    assert fiscal_service.fiscal_state(order) == "failed"


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=ALWAYS)
def test_failed_quando_ha_alerta_de_emissao_aberto():
    """A falha que morreu ANTES de virar Directive (o fechamento do PDV que não enfileirou)."""
    order = _order("FS-ALERT")
    create_operator_alert(
        type="fiscal_emit_failed", severity="critical", order_ref=order.ref,
        message="NFC-e do pedido FS-ALERT sem emissão", dedupe_key=f"fiscal_emit_failed:{order.ref}",
    )

    assert fiscal_service.fiscal_state(order) == "failed"

    OperatorAlert.objects.filter(order_ref=order.ref).update(resolved_at="2026-09-16T12:00:00Z")
    assert fiscal_service.fiscal_state(order) == "queued"


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=ALWAYS)
def test_a_directive_mais_recente_e_a_que_vale():
    order = _order("FS-REQUEUE")
    Directive.objects.create(topic=FISCAL_EMIT_NFCE, status="failed", payload={"order_ref": order.ref})
    Directive.objects.create(topic=FISCAL_EMIT_NFCE, status="queued", payload={"order_ref": order.ref})

    assert fiscal_service.fiscal_state(order) == "queued"


# ── Precedência: evidência antes da regra ────────────────────────────────


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=ON_REQUEST)
def test_a_tentativa_registrada_sobrevive_a_regra_dizer_nao():
    """Tirar o backend ou trocar o resolver não apaga uma nota que já tentou sair."""
    order = _order("FS-EVID")
    Directive.objects.create(topic=FISCAL_EMIT_NFCE, status="running", payload={"order_ref": order.ref})

    assert fiscal_service.fiscal_state(order) == "queued"


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=ON_REQUEST)
def test_a_chave_vale_mesmo_com_a_regra_dizendo_nao():
    order = _order("FS-KEY-RULE", nfce_access_key="chave")

    assert fiscal_service.fiscal_state(order) == "authorized"


# ── Leitura em lote ───────────────────────────────────────────────────────


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=ALWAYS)
def test_a_evidencia_pre_lida_dispensa_a_consulta():
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    order = _order("FS-BATCH")
    Directive.objects.create(topic=FISCAL_EMIT_NFCE, status="failed", payload={"order_ref": order.ref})

    with CaptureQueriesContext(connection) as captured:
        # O lote diz "queued" e "sem alerta": o serviço acredita nele, sem ir ao banco.
        state = fiscal_service.fiscal_state(order, directive_status="queued", emit_failed_alert=False)
    assert state == "queued"
    assert not [q for q in captured if "directive" in q["sql"].lower() or "operatoralert" in q["sql"].lower()]

    assert fiscal_service.fiscal_state(order, directive_status="", emit_failed_alert=True) == "failed"


# ── "Pedir papel já pede a nota" ─────────────────────────────────────────


@pytest.mark.parametrize(
    "resolver,expected",
    [
        (f"{ON_REQUEST},{ON_RECEIPT}", True),
        (ON_RECEIPT, True),
        (ALWAYS, True),
        (ON_REQUEST, False),
        ("shopman.shop.fiscal_resolvers.eletronic_payment", False),
        ("", False),
    ],
)
def test_receipt_request_emits_le_a_env_e_nao_o_default(resolver, expected):
    with override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=resolver):
        assert fiscal_service.receipt_request_emits() is expected


# ── Expedição sem NFC-e: grita, não barra ────────────────────────────────


def _handoff_alerts(order_ref: str):
    return OperatorAlert.objects.filter(type="fiscal_handoff_without_nfce", order_ref=order_ref)


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=ALWAYS)
def test_despacho_com_a_nota_na_fila_cria_UM_alerta_por_pedido():
    order = _order("FS-HANDOFF", payment={"method": "cash", "collection": "on_delivery"}, fulfillment_type="delivery")

    # O logger do módulo não propaga para o caplog (config de LOGGING da casa):
    # a prova do ``warning`` é pelo próprio logger.
    with patch.object(fiscal_service.logger, "warning") as warning:
        fiscal_service.alert_handoff_without_nfce(order, target_status="dispatched")
        fiscal_service.alert_handoff_without_nfce(order, target_status="completed")

    alerts = list(_handoff_alerts(order.ref))
    assert len(alerts) == 1
    assert "FS-HANDOFF saiu sem NFC-e autorizada" in alerts[0].message
    assert "despachado" in alerts[0].message
    assert warning.call_count == 2
    assert warning.call_args_list[0].args[0].startswith("fiscal.handoff_without_nfce")


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=ALWAYS)
def test_emissao_morta_tambem_grita_na_conclusao():
    order = _order("FS-HANDOFF-FAIL")
    Directive.objects.create(topic=FISCAL_EMIT_NFCE, status="failed", payload={"order_ref": order.ref})

    fiscal_service.alert_handoff_without_nfce(order, target_status="completed")

    alert = _handoff_alerts(order.ref).get()
    assert "concluído" in alert.message
    assert "falha de emissão" in alert.message


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=ALWAYS)
@pytest.mark.parametrize(
    "extra,target",
    [
        ({"nfce_access_key": "chave"}, "dispatched"),   # autorizada: nada a gritar
        ({"payment": {"method": "pix"}}, "dispatched"),  # esperando captura: outro estado
        ({}, "preparing"),                               # a cozinha começa, nada sai
    ],
)
def test_nao_grita_quando_nao_ha_o_que_gritar(extra, target):
    order = _order(f"FS-QUIET-{target}-{len(extra)}", **extra)

    fiscal_service.alert_handoff_without_nfce(order, target_status=target)

    assert not _handoff_alerts(order.ref).exists()


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=ON_REQUEST)
def test_nota_nao_esperada_sai_em_silencio():
    order = _order("FS-QUIET-NOT")

    fiscal_service.alert_handoff_without_nfce(order, target_status="dispatched")

    assert not _handoff_alerts(order.ref).exists()


def test_o_tipo_do_alerta_esta_registrado_no_catalogo():
    """Choice não registrada apaga a coluna no Admin — o tipo novo tem que estar na lista."""
    assert fiscal_service.HANDOFF_WITHOUT_NFCE_ALERT_TYPE in dict(OperatorAlert.TYPE_CHOICES)
