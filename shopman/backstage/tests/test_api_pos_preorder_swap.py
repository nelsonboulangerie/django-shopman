"""GET/POST /api/v1/backstage/pos/preorders/<ref>/swap/ (#2765): trocar o item que falta, no PDV.

O "Trocar por <produto>" do diálogo "Resolver" abre o PDV com ``?swap=<sku>``: o
endereço leva só a intenção. Esta suíte prende:

- as alternativas vêm do servidor, pela MESMA função do aviso
  (``order_promise.alternatives_for``), com a diferença de preço da prévia da
  edição e a quantidade da linha do pedido;
- ``()`` (a busca rodou e não achou) tem frase; ``None`` (não pôde procurar)
  não afirma que não há;
- SKU fora do pedido é ignorado em silêncio; sem permissão, 403;
- a troca grava pela edição da encomenda, relendo as alternativas: a que deixou
  de caber recusa com a frase, e nada muda.

Os lotes são planejados e cancelados pelo Craftsman de verdade, com as peças de
``test_api_order_promise_resolution``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from shopman.orderman.models import Order
from shopman.stockman import stock

from shopman.backstage.tests import test_api_order_promise_resolution as resolution
from shopman.backstage.tests.test_api_order_promise_resolution import (
    NAME,
    SKU,
    _baguete_e_cafe,
    _day,
    _lost_lot,
    _pay_pix,
)
from shopman.shop.services import order_composition
from shopman.shop.services.operator_orders import operational_revision

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]

# A casa e a vitrine do diálogo "Resolver": o mesmo pedido, os mesmos pães.
casa = resolution.casa
vitrine = resolution.vitrine


@pytest.fixture
def caixa(client, django_user_model):
    """Quem opera a encomenda no balcão: a porta do detalhe da encomenda do PDV."""
    user = django_user_model.objects.create_user(username="caixa-troca", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(codename="operate_pos", content_type__app_label="cashman"),
        Permission.objects.get(codename="manage_orders", content_type__app_label="shop"),
    )
    client.force_login(user)
    return user


def _get(client, ref: str, *skus: str):
    return client.get(reverse("api-backstage-pos-preorder-swap", args=[ref]), {"sku": list(skus)})


def _post(client, ref: str, body: dict):
    return client.post(reverse("api-backstage-pos-preorder-swap", args=[ref]), data=body, content_type="application/json")


def _swap_body(client, order: Order, offer: str, *, key: str) -> dict:
    read = _get(client, order.ref, SKU).json()
    return {
        "sku": SKU, "offer": offer, "base_revision": read["base_revision"],
        "expected_actor_id": read["expected_actor_id"], "idempotency_key": key,
    }


# ── A leitura ────────────────────────────────────────────────────────────────


def test_com_alternativa_traz_o_que_o_lote_da_data_cobre_e_a_diferenca_de_preco(client, caixa, vitrine):
    stock.plan(Decimal("10"), vitrine["FENDU"], _day(1))
    stock.plan(Decimal("6"), vitrine["CAMPAGNE"], _day(1))
    order = _baguete_e_cafe("WEB-SWAP-COM")
    _lost_lot(order, SKU, "4")

    response = _get(client, order.ref, SKU)

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["order_ref"] == "WEB-SWAP-COM"
    assert (body["refusal"], body["refusal_code"]) == ("", "")
    assert body["base_revision"] == operational_revision(order, field="edit")
    assert body["expected_actor_id"] == caixa.pk
    [item] = body["items"]
    assert (item["sku"], item["name"], item["qty"], item["qty_label"]) == (SKU, NAME, "4", f"4x {NAME}")
    assert item["fact"] == f"Faltam 4x {NAME}. O lote de amanhã foi cancelado."
    assert (item["searched"], item["empty_phrase"]) == (True, "")
    # As MESMAS do aviso e do diálogo "Resolver", na mesma ordem, com o mesmo verbo.
    assert [(o["sku"], o["label"], o["available_display"]) for o in item["options"]] == [
        ("FENDU", "Trocar por Fendu", "10 livres para amanhã"),
        ("CAMPAGNE", "Trocar por Pain de Campagne", "6 livres para amanhã"),
    ]
    fendu, campagne = item["options"]
    # 4 baguetes de R$ 11,00 saem, 4 fendus de R$ 12,00 entram (a quantidade da linha).
    assert fendu["qty_label"] == "4x Fendu"
    assert (fendu["total_before_q"], fendu["total_after_q"], fendu["difference_q"]) == (6200, 6600, 400)
    assert (fendu["total_before_display"], fendu["total_after_display"]) == ("R$ 62,00", "R$ 66,00")
    assert fendu["difference_display"] == "R$ 4,00 a mais"
    assert fendu["money"] == "O novo total é R$ 66,00, a pagar na retirada."
    assert (fendu["enabled"], fendu["reason"], fendu["requires_manager_approval"]) == (True, "", False)
    assert campagne["difference_display"] == "R$ 30,80 a mais"
    # Ler não grava nada.
    assert not order_composition.is_adjusted(Order.objects.get(pk=order.pk))


def test_troca_mais_barata_em_encomenda_paga_diz_o_estorno_e_pede_gerente(client, caixa, vitrine):
    stock.plan(Decimal("10"), vitrine["BRIOCHE"], _day(1))
    order = _baguete_e_cafe("WEB-SWAP-PIX")
    _pay_pix(order)
    _lost_lot(order, SKU, "4")

    [item] = _get(client, order.ref, SKU).json()["items"]
    brioche = next(option for option in item["options"] if option["sku"] == "BRIOCHE")

    assert brioche["difference_display"] == "R$ 8,00 a menos"
    assert brioche["money"] == "R$ 8,00 serão estornados ao Pix do cliente."
    assert (brioche["requires_manager_approval"], brioche["refund_q"]) == (True, 800)


def test_sem_nada_parecido_a_lista_vem_vazia_com_a_frase(client, caixa, vitrine):
    order = _baguete_e_cafe("WEB-SWAP-VAZIO")
    _lost_lot(order, SKU, "4")

    [item] = _get(client, order.ref, SKU).json()["items"]

    assert (item["searched"], item["options"]) == (True, [])
    assert item["empty_phrase"] == "Nenhum produto parecido livre para amanhã."


def test_busca_fora_do_ar_nao_afirma_que_nao_ha(client, caixa, vitrine, monkeypatch):
    from shopman.shop.services import substitutes

    order = _baguete_e_cafe("WEB-SWAP-FORA")
    _lost_lot(order, SKU, "4")

    def down(*_args, **_kwargs):
        raise RuntimeError("catálogo fora do ar")

    monkeypatch.setattr(substitutes, "find", down)
    [item] = _get(client, order.ref, SKU).json()["items"]

    assert (item["searched"], item["options"], item["empty_phrase"]) == (False, [], "")


def test_sku_fora_do_pedido_e_ignorado_em_silencio(client, caixa, vitrine):
    stock.plan(Decimal("10"), vitrine["FENDU"], _day(1))
    order = _baguete_e_cafe("WEB-SWAP-FORA-DO-PEDIDO")
    _lost_lot(order, SKU, "4")

    response = _get(client, order.ref, "NAO-EXISTE", "", "BRIOCHE", SKU, SKU)

    assert response.status_code == 200
    assert [item["sku"] for item in response.json()["items"]] == [SKU]
    # Sem SKU nenhum (ou só inválidos), a encomenda abre como sempre: nada a trocar.
    assert _get(client, order.ref).json()["items"] == []
    assert _get(client, order.ref, "NAO-EXISTE").json()["items"] == []


def test_encomenda_que_nao_se_edita_diz_por_que_e_nao_oferece_troca(client, caixa, vitrine):
    stock.plan(Decimal("10"), vitrine["FENDU"], _day(1))
    order = _baguete_e_cafe("WEB-SWAP-NOTA", nfce_access_key="4126" + "0" * 40)
    _lost_lot(order, SKU, "4")

    body = _get(client, order.ref, SKU).json()

    assert body["refusal_code"] == "fiscal_authorized"
    assert body["refusal"] == "A NFC-e desta encomenda já foi autorizada: para mudar, cancele e refaça a encomenda."
    assert body["items"] == []


def test_sem_permissao_e_403(client, django_user_model, vitrine):
    order = _baguete_e_cafe("WEB-SWAP-SEM-PERMISSAO")
    _lost_lot(order, SKU, "4")
    user = django_user_model.objects.create_user(username="so-pdv", is_staff=True)
    # Só operar o PDV não basta: a troca é edição de encomenda.
    user.user_permissions.add(Permission.objects.get(codename="operate_pos", content_type__app_label="cashman"))
    client.force_login(user)

    assert _get(client, order.ref, SKU).status_code == 403
    assert _post(client, order.ref, {"sku": SKU, "offer": "FENDU"}).status_code == 403


def test_pedido_que_nao_e_encomenda_e_404(client, caixa):
    assert _get(client, "NAO-EXISTE", SKU).status_code == 404


# ── A troca ──────────────────────────────────────────────────────────────────


def test_a_troca_grava_pela_edicao_com_a_quantidade_da_linha(client, caixa, vitrine):
    stock.plan(Decimal("10"), vitrine["FENDU"], _day(1))
    order = _baguete_e_cafe("WEB-SWAP-GRAVA")
    _lost_lot(order, SKU, "4")

    response = _post(client, order.ref, _swap_body(client, order, "FENDU", key="pdv-2765-troca"))

    assert response.status_code == 200, response.json()
    assert (response.json()["outcome"], response.json()["changed"]) == ("applied", True)
    order.refresh_from_db()
    assert [(item.sku, item.qty, item.unit_price_q) for item in order_composition.effective_items(order)] == [
        ("FENDU", Decimal("4"), 1200), ("CAFE", Decimal("2"), 900),
    ]
    assert order_composition.effective_total_q(order) == 6600
    # O item trocado não pede mais troca.
    assert _get(client, order.ref, SKU).json()["items"] == []


def test_alternativa_que_deixou_de_caber_recusa_e_nada_muda(client, caixa, vitrine, monkeypatch):
    from shopman.backstage.projections import order_promise

    stock.plan(Decimal("10"), vitrine["FENDU"], _day(1))
    order = _baguete_e_cafe("WEB-SWAP-SUMIU")
    _lost_lot(order, SKU, "4")
    body = _swap_body(client, order, "FENDU", key="pdv-2765-sumiu")

    # Entre a leitura e o toque, o lote da data deixou de ter o Fendu livre.
    monkeypatch.setattr(order_promise, "alternatives_for", lambda *_a, **_k: ())
    response = _post(client, order.ref, body)

    assert response.status_code == 400
    payload = response.json()
    assert payload["outcome"] == "not_applied"
    assert payload["code"] == "swap_offer_gone"
    assert payload["field"] == "offer"
    assert payload["detail"] == (
        "Este produto não está mais livre para a data da encomenda. Nada mudou: escolha outra alternativa."
    )
    assert payload["errors"] == {"offer": [payload["detail"]]}
    assert not order_composition.is_adjusted(Order.objects.get(pk=order.pk))


def test_a_troca_sem_conseguir_reler_recusa(client, caixa, vitrine, monkeypatch):
    from shopman.backstage.projections import order_promise

    stock.plan(Decimal("10"), vitrine["FENDU"], _day(1))
    order = _baguete_e_cafe("WEB-SWAP-SEM-LER")
    _lost_lot(order, SKU, "4")
    body = _swap_body(client, order, "FENDU", key="pdv-2765-sem-ler")

    monkeypatch.setattr(order_promise, "alternatives_for", lambda *_a, **_k: None)
    response = _post(client, order.ref, body)

    assert response.status_code == 400
    assert response.json()["code"] == "swap_unverified"
    assert not order_composition.is_adjusted(Order.objects.get(pk=order.pk))


def test_troca_de_sku_fora_do_pedido_e_recusada_no_dialeto(client, caixa, vitrine):
    order = _baguete_e_cafe("WEB-SWAP-SKU-RUIM")

    response = _post(client, order.ref, {"sku": "NAO-EXISTE", "offer": "FENDU"})

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Este item não está na encomenda.", "field": "sku",
        "errors": {"sku": ["Este item não está na encomenda."]},
    }


def test_troca_mais_barata_paga_sem_gerente_pede_o_gerente(client, caixa, vitrine):
    stock.plan(Decimal("10"), vitrine["BRIOCHE"], _day(1))
    order = _baguete_e_cafe("WEB-SWAP-GERENTE")
    _pay_pix(order)
    _lost_lot(order, SKU, "4")

    response = _post(client, order.ref, _swap_body(client, order, "BRIOCHE", key="pdv-2765-gerente"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "manager_approval_required"
    assert not order_composition.is_adjusted(Order.objects.get(pk=order.pk))
