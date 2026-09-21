"""Emissão avulsa da NFC-e pelas Últimas vendas do PDV.

A regra padrão da casa emite só a pedido. Quando o cliente volta ao balcão
pedindo a nota de uma venda que não a pediu, o gerente autoriza e a nota sai —
pelo MESMO desafio gerencial do cancelamento (crachá ou PIN), com quem
autorizou gravado no pedido. Sem gerente, nada acontece.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.cashman.models import Shift
from shopman.doorman.models import PinCredential
from shopman.orderman.models import Directive, Order

from shopman.shop.directives import FISCAL_EMIT_NFCE
from shopman.shop.models import Channel, Shop
from shopman.shop.services import fiscal

pytestmark = pytest.mark.django_db

MANAGER_PIN = "4321"
RULE = "shopman.shop.fiscal_resolvers.on_request_or_tax_id,shopman.shop.fiscal_resolvers.on_requested_receipt"


def _grant(user, codename: str) -> None:
    ct = ContentType.objects.get_for_model(Shift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))


@pytest.fixture(autouse=True)
def _rule(settings):
    # A regra padrão da casa: nota só quando pedem (nota, CPF ou comprovante).
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = RULE


@pytest.fixture
def backend():
    with patch("shopman.shop.services.fiscal.fiscal_pool.get_backend", return_value=object()):
        yield


@pytest.fixture
def counter(client):
    Shop.objects.create(name="Loja", brand_name="Loja")
    Channel.objects.create(ref="pdv", name="PDV", is_active=True, config={})
    operator = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    _grant(operator, "operate_pos")
    manager = get_user_model().objects.create_user(username="pablo", password="x", is_staff=True)
    _grant(manager, "adjust_shift")
    PinCredential.set_for(manager, MANAGER_PIN)
    client.force_login(operator)
    return {"operator": operator, "manager": manager}


def _sale(ref: str = "PDV-AVULSA", **data) -> Order:
    order = Order.objects.create(
        ref=ref, channel_ref="pdv", session_key=f"s-{ref}", status=Order.Status.COMPLETED, total_q=1500,
        data={
            "origin_channel": "pos",
            "fulfillment_type": "pickup",
            "payment": {"method": "cash", "amount_q": 1500,
                        "tenders": [{"method": "cash", "amount_q": 1500, "status": "received"}]},
            **data,
        },
        snapshot={"items": [{"sku": "PAO", "name": "Pão", "qty": 1, "price_q": 1500}]},
    )
    order.items.create(sku="PAO", name="Pão", qty=1, unit_price_q=1500, line_total_q=1500)
    return order


def _post(client, ref: str, approval: dict | None):
    body = {"manager_approval": approval} if approval is not None else {}
    return client.post(reverse("api-backstage-pos-emit-fiscal", args=[ref]), body, content_type="application/json")


def _emissions(ref: str):
    return Directive.objects.filter(topic=FISCAL_EMIT_NFCE, payload__order_ref=ref)


# ── Sem gerente, nada acontece ───────────────────────────────────────────


def test_sem_autorizacao_recusa_e_nao_emite(client, counter, backend):
    order = _sale()
    response = _post(client, order.ref, None)
    assert response.status_code == 422, response.content
    assert response.json()["error"]["code"] == "manager_approval_required"
    order.refresh_from_db()
    assert fiscal.ISSUE_OVERRIDE_KEY not in (order.data.get("fiscal") or {})
    assert not _emissions(order.ref).exists()


def test_pin_errado_recusa_e_nao_emite(client, counter, backend):
    order = _sale()
    response = _post(client, order.ref, {"username": "pablo", "pin": "0000"})
    assert response.status_code == 422, response.content
    assert response.json()["error"]["code"] == "manager_approval_invalid"
    assert not _emissions(order.ref).exists()


def test_operador_sem_permissao_de_gerente_nao_autoriza(client, counter, backend):
    # A marina opera o PDV, mas não é gerente: o PIN dela não assina exceção.
    PinCredential.set_for(counter["operator"], "1111")
    order = _sale()
    response = _post(client, order.ref, {"username": "marina", "pin": "1111"})
    assert response.status_code == 422, response.content
    assert not _emissions(order.ref).exists()


# ── Com gerente, a nota sai e a assinatura fica ──────────────────────────


def test_gerente_autoriza_emite_e_assina(client, counter, backend):
    order = _sale()
    assert fiscal.fiscal_state(order) == fiscal.FISCAL_STATE_NOT_EXPECTED

    response = _post(client, order.ref, {"username": "pablo", "pin": MANAGER_PIN})

    assert response.status_code == 200, response.content
    assert "data e a hora de agora" in response.json()["detail"]
    directive = _emissions(order.ref).get()
    assert directive.status == "queued"
    order.refresh_from_db()
    override = order.data["fiscal"][fiscal.ISSUE_OVERRIDE_KEY]
    assert override["approved_by"] == "pablo"
    assert override["requested_by"]
    assert override["at"]
    event = order.events.get(type="fiscal_issue_override")
    assert event.payload["approved_by"] == "pablo"
    # A nota passa a existir para o resto do sistema pelo vocabulário de sempre.
    assert fiscal.fiscal_state(order) == fiscal.FISCAL_STATE_QUEUED


def test_segundo_pedido_nao_duplica_a_emissao(client, counter, backend):
    order = _sale()
    assert _post(client, order.ref, {"username": "pablo", "pin": MANAGER_PIN}).status_code == 200
    again = _post(client, order.ref, {"username": "pablo", "pin": MANAGER_PIN})
    assert again.status_code == 409
    assert "em andamento" in again.json()["detail"]
    assert _emissions(order.ref).count() == 1


# ── Recusas honestas (e a autorização não fica gravada à toa) ─────────────


def test_venda_de_mais_de_24_horas_recusa(client, counter, backend):
    order = _sale()
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(hours=25))
    response = _post(client, order.ref, {"username": "pablo", "pin": MANAGER_PIN})
    assert response.status_code == 409
    assert "24 horas" in response.json()["detail"]
    order.refresh_from_db()
    assert fiscal.ISSUE_OVERRIDE_KEY not in (order.data.get("fiscal") or {})


def test_nota_ja_autorizada_recusa(client, counter, backend):
    order = _sale(nfce_access_key="4126" + "0" * 40)
    response = _post(client, order.ref, {"username": "pablo", "pin": MANAGER_PIN})
    assert response.status_code == 409
    assert "já foi autorizada" in response.json()["detail"]


def test_venda_cancelada_recusa(client, counter, backend):
    order = _sale()
    Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELLED)
    response = _post(client, order.ref, {"username": "pablo", "pin": MANAGER_PIN})
    assert response.status_code == 409
    assert not _emissions(order.ref).exists()


def test_sem_emissor_configurado_recusa(client, counter):
    order = _sale()
    with patch("shopman.shop.services.fiscal.fiscal_pool.get_backend", return_value=None):
        response = _post(client, order.ref, {"username": "pablo", "pin": MANAGER_PIN})
    assert response.status_code == 409
    assert "não está configurada" in response.json()["detail"]
    order.refresh_from_db()
    assert fiscal.ISSUE_OVERRIDE_KEY not in (order.data.get("fiscal") or {})


def test_directive_que_nao_nasce_desfaz_a_autorizacao(counter, backend):
    """Pagamento abaixo do total: ``emit`` alerta e não enfileira — a chave some junto."""
    from shopman.backstage.services import orders
    from shopman.backstage.services.exceptions import OrderError

    order = _sale(payment={"method": "cash", "amount_q": 100})
    with pytest.raises(OrderError, match="não foi enfileirada"):
        orders.emit_fiscal_on_demand(order, actor="pos:marina", approved_by_username="pablo")
    order.refresh_from_db()
    assert fiscal.ISSUE_OVERRIDE_KEY not in (order.data.get("fiscal") or {})


# ── A regra só cede para a chave gravada pelo escritor único ─────────────


def test_resolver_cede_so_a_autorizacao_com_assinatura():
    order = Order(ref="X", total_q=1, data={})
    assert fiscal.emission_resolver(order) is False
    order.data = {"fiscal": {"issue_override": {"requested_by": "pos:marina"}}}
    assert fiscal.emission_resolver(order) is False  # sem aprovador, não vale
    order.data = {"fiscal": {"issue_override": {"approved_by": "pablo"}}}
    assert fiscal.emission_resolver(order) is True


# ── A lista anuncia o botão pelo MESMO predicado ─────────────────────────


def test_ultimas_vendas_anunciam_a_emissao_avulsa(client, counter, backend):
    _sale("PDV-NAO-PEDIDA")
    _sale("PDV-PEDIDA", fiscal={"issue_document": True})
    _sale("PDV-AUTORIZADA", nfce_access_key="4126" + "0" * 40)

    response = client.get("/api/v1/backstage/pos/recent-sales/")

    assert response.status_code == 200
    sales = {s["order_ref"]: s for s in response.json()["sales"]}
    assert sales["PDV-NAO-PEDIDA"]["fiscal_state"] == "not_expected"
    assert sales["PDV-NAO-PEDIDA"]["can_emit_fiscal"] is True
    assert sales["PDV-PEDIDA"]["can_emit_fiscal"] is False
    assert sales["PDV-AUTORIZADA"]["can_emit_fiscal"] is False


def test_sem_emissor_a_lista_nao_oferece(client, counter):
    _sale("PDV-SEM-EMISSOR")
    with patch("shopman.shop.services.fiscal.fiscal_pool.get_backend", return_value=None):
        response = client.get("/api/v1/backstage/pos/recent-sales/")
    assert response.json()["sales"][0]["can_emit_fiscal"] is False
