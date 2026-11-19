"""GET /api/v1/backstage/orders/<ref>/promise-resolution/ (WP-G08, o diálogo "Resolver").

O aviso "Promessa em risco" leva um botão só, "Resolver"; as escolhas e a
mensagem ao cliente moram neste endpoint, lido na hora em que o diálogo abre
(``projections/order_promise_resolution``). Esta suíte prende:

- a porta: 200 com as quatro famílias de escolha na ordem (trocas, remarcar,
  tirar o item, cancelar), 409 sem risco, 403 sem permissão, 404;
- trocar só existe com sugestão, e leva ao PDV só o SKU em falta (``?swap=``);
- tirar o item manda a lista FINAL que ``POST orders/<ref>/edit/`` recebe
  (falta tudo: a linha sai; falta parte: a quantidade cai), com o gerente
  quando a prévia pede, e fecha com a frase certa quando é o único item ou a
  edição é recusada;
- cancelar diz o que acontece com o dinheiro, pela régua do cancelar do detalhe;
- a mensagem de cada escolha: proposta, na voz da casa, nas palavras do cliente,
  com o valor quando há dinheiro; a conversa do WhatsApp já leva o texto, e some
  quando o pedido não tem telefone.

Os lotes são planejados e cancelados pelo Craftsman de verdade, como em
``test_order_promise``.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, quote, unquote, urlsplit

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import formats, timezone
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.craftsman.service import CraftService as craft
from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product
from shopman.orderman.models import Order, OrderItem
from shopman.payman import PaymentService
from shopman.stockman import stock
from shopman.stockman.models import Hold, HoldStatus, Position, PositionKind, Quant
from shopman.stockman.services.holds import (
    QUALITY_GRADE_POLICY_VERSION,
    QUALITY_GRADE_POLICY_VERSION_METADATA_KEY,
)

from shopman.backstage.projections.order_promise_resolution import build_promise_resolution
from shopman.shop import notification_copy
from shopman.shop.models import Channel, Shop
from shopman.shop.services import order_composition
from shopman.shop.services.operator_orders import operational_revision

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]

SKU = "BAGUETE"
NAME = "Baguete de tradição"
PDV = "https://pdv.example.test"
OPENING = "Oi, Nelson! Aqui é da Nelson Boulangerie 💛"
SORRY = ", e sinto muito por isso."


@pytest.fixture(autouse=True)
def casa(db, settings):
    # A ponte do Craftsman com o estoque: é ela que mexe nos saldos de produção.
    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401, I001
    from django.core.cache import cache

    cache.clear()
    settings.SHOPMAN_SURFACE_URLS = {"pos": f"{PDV}/"}
    Shop.objects.create(name="Nelson Boulangerie", brand_name="Nelson")
    Channel.objects.update_or_create(ref="web", defaults={"name": "Loja online", "config": {}})
    Position.objects.get_or_create(
        ref="loja", defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    yield
    cache.clear()


@pytest.fixture
def gerente(client, django_user_model):
    user = django_user_model.objects.create_user(username="gerente-resolver", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    client.force_login(user)
    return user


@pytest.fixture
def vitrine(db):
    """A baguete (com ficha), o croissant e dois pães da mesma prateleira, no cardápio do canal."""
    listing = Listing.objects.create(ref="web", name="Loja online", is_active=True)
    collection = Collection.objects.create(ref="paes", name="Pães")
    products = {}
    for index, (sku, name, price_q) in enumerate((
        (SKU, NAME, 1100), ("FENDU", "Fendu", 1200), ("CAMPAGNE", "Pain de Campagne", 1870), ("BRIOCHE", "Brioche", 900),
    )):
        product = Product.objects.create(
            sku=sku, name=name, unit="un", base_price_q=price_q, availability_policy="planned_ok",
            is_sellable=True, is_published=True,
        )
        ListingItem.objects.create(listing=listing, product=product, price_q=price_q, is_published=True, is_sellable=True)
        CollectionItem.objects.create(collection=collection, product=product, sort_order=index, is_primary=True)
        products[sku] = product
    # Fora do Stockman: entra no pedido sem reserva (a outra linha do pedido).
    products["CAFE"] = Product.objects.create(sku="CAFE", name="Café coado", unit="un", base_price_q=900, is_sellable=True)
    Product.objects.create(sku="FARINHA", name="Farinha", unit="kg", base_price_q=500, is_sellable=False)
    for sku in (SKU, "BRIOCHE"):
        recipe = Recipe.objects.create(ref=sku.lower(), name=products[sku].name, output_sku=sku, batch_size=Decimal("10"))
        RecipeItem.objects.create(recipe=recipe, input_sku="FARINHA", quantity=Decimal("0.5"), unit="kg")
    return products


def _day(days: int = 0):
    return timezone.localdate() + timedelta(days=days)


def _order(ref: str, lines, *, days: int | None = 1, status: str = "accepted", **data) -> Order:
    """Um pedido com as linhas ``[(sku, nome, qtd, preço)]``; ``days`` é a data da encomenda."""
    body = {
        "customer": {"name": "Nelson Dias", "phone": "+5543999990000"},
        "fulfillment_type": "pickup",
        "payment": {"method": "cash"},
        "availability_decision": {"approved": True, "decisions": []},
        **data,
    }
    if days is not None:
        body["is_preorder"] = True
        body["delivery_date"] = _day(days).isoformat()
    total = sum(qty * price for _sku, _name, qty, price in lines)
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"s-{ref}", status=status, total_q=total, data=body,
    )
    for index, (sku, name, qty, price) in enumerate(lines, start=1):
        OrderItem.objects.create(
            order=order, line_id=f"L{index}", sku=sku, name=name, qty=qty, unit_price_q=price, line_total_q=qty * price,
        )
    return order


def _reserve(order: Order, sku: str, qty: str, *, day, quant: Quant | None = None) -> Hold:
    """A reserva do pedido, como o commit a deixa: presa ao saldo (ou sem saldo) e listada em ``hold_ids``."""
    hold = Hold.objects.create(
        sku=sku, quant=quant, quantity=Decimal(qty), target_date=day, status=HoldStatus.CONFIRMED,
        metadata={
            "reference": f"order:{order.ref}",
            QUALITY_GRADE_POLICY_VERSION_METADATA_KEY: QUALITY_GRADE_POLICY_VERSION,
            "priority": 0,
            **({"planned": True} if quant is not None and quant.target_date else {"on_demand": True} if quant is None else {}),
        },
    )
    order.data.setdefault("hold_ids", []).append({"sku": sku, "hold_id": hold.hold_id, "qty": float(qty)})
    order.save(update_fields=["data"])
    return hold


def _lost_lot(order: Order, sku: str, qty: str, *, days: int = 1):
    """O lote da data planejado, a reserva do pedido presa a ele, e o lote cancelado pela Produção."""
    work_order = craft.plan(Recipe.objects.get(output_sku=sku), quantity=Decimal("10"), date=_day(days))
    _reserve(order, sku, qty, day=_day(days), quant=Quant.objects.get(sku=sku, target_date=_day(days), batch=""))
    craft.void(work_order, reason="Forno parou")
    return work_order


def _pay_pix(order: Order) -> None:
    """O pedido pago por Pix no gateway: a diferença volta sozinha ao Pix do cliente."""
    intent_ref = f"INT-{order.ref}"
    PaymentService.create_intent(order.ref, order.total_q, "pix", gateway="mock", ref=intent_ref)
    PaymentService.authorize(intent_ref)
    PaymentService.capture(intent_ref)
    order.data["payment"] = {"method": "pix", "intent_ref": intent_ref}
    order.save(update_fields=["data"])


def _get(client, ref: str):
    return client.get(reverse("api-backstage-order-promise-resolution", args=[ref]))


def _choices(client, order: Order) -> dict[str, dict]:
    response = _get(client, order.ref)
    assert response.status_code == 200, response.json()
    return {choice["key"]: choice for choice in response.json()["choices"]}


def _happened(what: str, code: str) -> str:
    return f"O item {NAME} do seu pedido {code} {what}{SORRY}"


def _baguete_e_cafe(ref: str = "WEB-2611-G8G-N75", **kwargs) -> Order:
    return _order(ref, [(SKU, NAME, 4, 1100), ("CAFE", "Café coado", 2, 900)], **kwargs)


# ── A porta ──────────────────────────────────────────────────────────────────


def test_o_dialogo_traz_o_fato_as_quatro_familias_na_ordem_e_a_mensagem_de_cada_uma(client, gerente, vitrine):
    """A encomenda paga por Pix que perdeu o lote de amanhã, com o Fendu livre na data."""
    stock.plan(Decimal("10"), vitrine["FENDU"], _day(1))
    order = _baguete_e_cafe()
    _pay_pix(order)
    _lost_lot(order, SKU, "4")
    order = Order.objects.get(pk=order.pk)

    response = _get(client, order.ref)

    assert response.status_code == 200, response.json()
    happened = _happened("não vai ficar pronto amanhã", "N75")
    swap_message = f"{OPENING} {happened} Posso trocar por Fendu? Me avisa e eu ajusto por aqui ✨"
    reschedule_message = (
        f"{OPENING} {happened} Posso remarcar o seu pedido para outro dia? Me diz qual fica melhor para você ✨"
    )
    remove_message = (
        f"{OPENING} {happened} Posso tirar esse item do pedido e devolver R$ 44,00 pelo Pix? "
        "Me avisa e eu ajusto por aqui ✨"
    )
    cancel_message = (
        f"{OPENING} {happened} Se preferir, cancelo o pedido e devolvo R$ 62,00 pelo Pix. "
        "Me avisa como fica melhor para você ✨"
    )

    def whatsapp(message: str) -> str:
        return f"https://wa.me/5543999990000?text={quote(message, safe='')}"

    assert response.json() == {
        "order_ref": "WEB-2611-G8G-N75",
        "code": "N75",
        "customer_name": "Nelson Dias",
        "facts": ["Faltam 4x Baguete de tradição. O lote de amanhã foi cancelado."],
        "contact": {"enabled": True, "reason": ""},
        "interim_note": "O envio automático ainda não existe: copie a mensagem ou chame o cliente no WhatsApp.",
        "choices": [
            {
                "key": "swap:BAGUETE:FENDU",
                "kind": "swap",
                "label": "Trocar por Fendu",
                "detail": "10 livres para amanhã",
                "enabled": True,
                "reason": "",
                "message": swap_message,
                "whatsapp_url": whatsapp(swap_message),
                "conclude": {
                    "kind": "link", "label": "Trocar no PDV",
                    "href": f"{PDV}/preorders/WEB-2611-G8G-N75?swap=BAGUETE", "items": [], "payload_schema": {},
                },
                "requires_manager_approval": False,
            },
            {
                "key": "reschedule",
                "kind": "reschedule",
                "label": "Remarcar para outro dia ou outro lote",
                "detail": "",
                "enabled": True,
                "reason": "",
                "message": reschedule_message,
                "whatsapp_url": whatsapp(reschedule_message),
                "conclude": {
                    "kind": "link", "label": "Remarcar no PDV",
                    "href": f"{PDV}/preorders/WEB-2611-G8G-N75", "items": [], "payload_schema": {},
                },
                "requires_manager_approval": False,
            },
            {
                "key": "remove",
                "kind": "remove",
                "label": "Tirar só o item que falta e devolver a diferença",
                "detail": "R$ 44,00 serão estornados ao Pix do cliente.",
                "enabled": True,
                "reason": "",
                "message": remove_message,
                "whatsapp_url": whatsapp(remove_message),
                "conclude": {
                    "kind": "edit", "label": "Tirar o item", "href": "",
                    "items": [{"line_id": "L2", "sku": "CAFE", "qty": "2"}],
                    "payload_schema": {
                        "base_revision": operational_revision(order, field="edit"),
                        "expected_actor_id": gerente.pk,
                    },
                },
                "requires_manager_approval": True,
            },
            {
                "key": "cancel",
                "kind": "cancel",
                "label": "Cancelar o pedido inteiro",
                "detail": "R$ 62,00 serão estornados ao Pix do cliente.",
                "enabled": True,
                "reason": "",
                "message": cancel_message,
                "whatsapp_url": whatsapp(cancel_message),
                "conclude": {"kind": "cancel", "label": "Cancelar pedido", "href": "", "items": [], "payload_schema": {}},
                "requires_manager_approval": True,
            },
        ],
    }
    # Ler o diálogo não grava nada: o pedido segue sem ajuste.
    assert not order_composition.is_adjusted(Order.objects.get(pk=order.pk))


def test_pedido_sem_promessa_em_risco_e_409(client, gerente, vitrine):
    order = _baguete_e_cafe("WEB-SEM-RISCO")
    craft.plan(Recipe.objects.get(output_sku=SKU), quantity=Decimal("10"), date=_day(1))
    _reserve(order, SKU, "4", day=_day(1), quant=Quant.objects.get(sku=SKU, target_date=_day(1), batch=""))

    response = _get(client, order.ref)

    assert response.status_code == 409
    assert response.json() == {"detail": "Este pedido não tem mais promessa em risco."}


def test_sem_permissao_e_403(client, django_user_model, vitrine):
    order = _baguete_e_cafe("WEB-SEM-PERMISSAO")
    _lost_lot(order, SKU, "4")
    client.force_login(django_user_model.objects.create_user(username="so-olha-resolver", is_staff=True))

    assert _get(client, order.ref).status_code == 403


def test_pedido_que_nao_existe_e_404(client, gerente):
    response = _get(client, "NAO-EXISTE")

    assert response.status_code == 404
    assert response.json() == {"detail": "Pedido não encontrado."}


# ── Trocar ───────────────────────────────────────────────────────────────────


def test_sem_sugestao_nao_ha_escolha_de_troca(client, gerente, vitrine):
    """Os outros pães existem no cardápio e não têm lote amanhã: não se oferece o que não há."""
    order = _baguete_e_cafe("WEB-SEM-TROCA")
    _lost_lot(order, SKU, "4")

    choices = _choices(client, order)

    assert list(choices) == ["reschedule", "remove", "cancel"]


def test_a_troca_leva_ao_pdv_so_o_sku_em_falta(client, gerente, vitrine):
    """Nada de nome, preço, quantidade ou cliente no endereço: o PDV pede as alternativas ao servidor."""
    stock.plan(Decimal("10"), vitrine["FENDU"], _day(1))
    stock.plan(Decimal("6"), vitrine["CAMPAGNE"], _day(1))
    order = _baguete_e_cafe("WEB-TROCA")
    _lost_lot(order, SKU, "4")

    choices = _choices(client, order)

    # Uma escolha por sugestão, até duas por item em falta, na ordem do aviso.
    assert list(choices) == ["swap:BAGUETE:FENDU", "swap:BAGUETE:CAMPAGNE", "reschedule", "remove", "cancel"]
    assert [(choices[key]["label"], choices[key]["detail"]) for key in list(choices)[:2]] == [
        ("Trocar por Fendu", "10 livres para amanhã"),
        ("Trocar por Pain de Campagne", "6 livres para amanhã"),
    ]
    for key in ("swap:BAGUETE:FENDU", "swap:BAGUETE:CAMPAGNE"):
        href = urlsplit(choices[key]["conclude"]["href"])
        assert (href.path, parse_qs(href.query)) == ("/preorders/WEB-TROCA", {"swap": ["BAGUETE"]})
        assert choices[key]["conclude"]["label"] == "Trocar no PDV"
    assert "Pain de Campagne" in choices["swap:BAGUETE:CAMPAGNE"]["message"]


def test_com_mais_de_um_item_em_falta_o_rotulo_diz_qual_e_o_endereco_leva_os_dois(client, gerente, vitrine):
    stock.plan(Decimal("10"), vitrine["FENDU"], _day(1))
    order = _order("WEB-DOIS", [(SKU, NAME, 4, 1100), ("BRIOCHE", "Brioche", 2, 900), ("CAFE", "Café coado", 1, 900)])
    _lost_lot(order, SKU, "4")
    _lost_lot(order, "BRIOCHE", "2")

    response = _get(client, order.ref)
    choices = {choice["key"]: choice for choice in response.json()["choices"]}

    assert response.json()["facts"] == [
        "Faltam 4x Baguete de tradição. O lote de amanhã foi cancelado.",
        "Faltam 2x Brioche. O lote de amanhã foi cancelado.",
    ]
    assert list(choices) == ["swap:BAGUETE:FENDU", "swap:BRIOCHE:FENDU", "reschedule", "remove", "cancel"]
    assert choices["swap:BAGUETE:FENDU"]["label"] == "Trocar Baguete de tradição por Fendu"
    assert choices["swap:BRIOCHE:FENDU"]["label"] == "Trocar Brioche por Fendu"
    # O SKU desta escolha na frente; o outro item em falta com sugestão vai junto.
    assert parse_qs(urlsplit(choices["swap:BAGUETE:FENDU"]["conclude"]["href"]).query) == {"swap": ["BAGUETE", "BRIOCHE"]}
    assert parse_qs(urlsplit(choices["swap:BRIOCHE:FENDU"]["conclude"]["href"]).query) == {"swap": ["BRIOCHE", "BAGUETE"]}
    # A mensagem conta os dois itens e propõe a troca desta escolha.
    assert choices["swap:BRIOCHE:FENDU"]["message"] == (
        f"{OPENING} No seu pedido DOIS, o item Baguete de tradição não vai ficar pronto amanhã "
        f"e o item Brioche não vai ficar pronto amanhã{SORRY} "
        "Posso trocar Brioche por Fendu? Me avisa e eu ajusto por aqui ✨"
    )
    # Tirar os dois deixa o café: a lista final é só ele, e a mensagem fala "esses itens".
    assert choices["remove"]["conclude"]["items"] == [{"line_id": "L3", "sku": "CAFE", "qty": "1"}]
    assert "Posso tirar esses itens do pedido? O total fica em R$ 9,00." in choices["remove"]["message"]


def test_sem_o_endereco_do_pdv_trocar_e_remarcar_ficam_fechados_com_o_motivo(client, gerente, vitrine, settings):
    settings.SHOPMAN_SURFACE_URLS = {"pos": ""}
    stock.plan(Decimal("10"), vitrine["FENDU"], _day(1))
    order = _baguete_e_cafe("WEB-SEM-PDV")
    _lost_lot(order, SKU, "4")

    choices = _choices(client, order)

    for key in ("swap:BAGUETE:FENDU", "reschedule"):
        closed = choices[key]
        assert (closed["enabled"], closed["reason"]) == (False, "O endereço do PDV não está configurado.")
        assert (closed["conclude"]["href"], closed["message"], closed["whatsapp_url"]) == ("", "", "")
    # Tirar o item e cancelar não dependem do PDV.
    assert choices["remove"]["enabled"] is True
    assert choices["cancel"]["enabled"] is True


# ── Remarcar ─────────────────────────────────────────────────────────────────


def test_remarcar_segue_a_regua_do_reagendar(client, gerente, vitrine):
    """Pedido pronto não muda mais de data (``reschedule.state_refusal``): a escolha fica, fechada, com a frase."""
    from shopman.shop.services import reschedule

    order = _baguete_e_cafe("WEB-PRONTO", status="ready")
    _lost_lot(order, SKU, "4")

    choice = _choices(client, order)["reschedule"]

    refusal = reschedule.state_refusal(Order.objects.get(pk=order.pk))
    assert refusal
    assert (choice["enabled"], choice["reason"]) == (False, refusal)
    assert (choice["conclude"]["href"], choice["message"]) == ("", "")


# ── Tirar o item ─────────────────────────────────────────────────────────────


def test_tirar_o_item_quando_falta_parte_baixa_a_quantidade(client, gerente, vitrine):
    """Pedido de hoje reservado na vitrine, e a contagem baixa o saldo: falta 1 de 3."""
    loja = Position.objects.get(ref="loja")
    stock.receive(quantity=Decimal("3"), sku=SKU, position=loja, reason="vitrine")
    quant = Quant.objects.get(sku=SKU, position=loja, target_date__isnull=True)
    order = _order("WEB-PARTE", [(SKU, NAME, 3, 1100)], days=None, status="new")
    _reserve(order, SKU, "3", day=_day(), quant=quant)
    stock.adjust(quant, Decimal("2"), reason="Quebra")

    choice = _choices(client, order)["remove"]

    assert choice["enabled"] is True
    assert choice["conclude"]["items"] == [{"line_id": "L1", "sku": SKU, "qty": "2"}]
    # Nada foi pago: não há devolução nem gerente; a frase é a da prévia da edição.
    assert choice["detail"] == "O novo total é R$ 22,00, a pagar na retirada."
    assert choice["requires_manager_approval"] is False
    assert choice["message"] == (
        f"{OPENING} {_happened('está em falta em parte (falta 1 de 3)', 'PARTE')} "
        "Posso tirar o que falta do pedido? O total fica em R$ 22,00. Me avisa e eu ajusto por aqui ✨"
    )


def test_a_lista_final_e_exatamente_o_que_a_edicao_recebe(client, gerente, vitrine):
    """``conclude.items`` + ``payload_schema`` gravam pela rota que já existe; sem gerente, 422."""
    order = _baguete_e_cafe("WEB-GRAVA")
    _pay_pix(order)
    _lost_lot(order, SKU, "4")
    conclude = _choices(client, order)["remove"]["conclude"]
    url = reverse("api-backstage-order-edit", args=[order.ref])
    body = {"items": conclude["items"], **conclude["payload_schema"], "idempotency_key": "g08-resolver-tirar"}

    # A prévia avisou que o gerente assina: a mesma edição sem ele é recusada.
    refused = client.post(url, data=body, content_type="application/json")
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "manager_approval_required"

    # Sem dinheiro recebido, a mesma forma de corpo aplica direto.
    unpaid = _baguete_e_cafe("WEB-GRAVA-SEM-PAGAR")
    _lost_lot(unpaid, SKU, "4", days=2)
    conclude = _choices(client, unpaid)["remove"]["conclude"]
    applied = client.post(
        reverse("api-backstage-order-edit", args=[unpaid.ref]),
        data={"items": conclude["items"], **conclude["payload_schema"], "idempotency_key": "g08-resolver-tirar-2"},
        content_type="application/json",
    )
    assert applied.status_code == 200, applied.json()
    unpaid.refresh_from_db()
    assert [(item.sku, item.qty) for item in order_composition.effective_items(unpaid)] == [("CAFE", Decimal("2"))]
    assert order_composition.effective_total_q(unpaid) == 1800


def test_tirar_o_unico_item_do_pedido_manda_cancelar(client, gerente, vitrine):
    order = _order("WEB-UNICO", [(SKU, NAME, 4, 1100)])
    _lost_lot(order, SKU, "4")

    choice = _choices(client, order)["remove"]

    assert (choice["enabled"], choice["reason"]) == (False, "É o único item do pedido: cancele o pedido.")
    assert choice["conclude"] == {"kind": "edit", "label": "Tirar o item", "href": "", "items": [], "payload_schema": {}}
    # Escolha fechada não propõe nada ao cliente.
    assert (choice["message"], choice["whatsapp_url"], choice["requires_manager_approval"]) == ("", "", False)


def test_edicao_recusada_pelo_estado_fecha_tirar_e_trocar_com_a_frase_dela(client, gerente, vitrine):
    """NFC-e autorizada: a edição não existe mais (``order_edit.state_refusal``)."""
    stock.plan(Decimal("10"), vitrine["FENDU"], _day(1))
    order = _baguete_e_cafe("WEB-NOTA", nfce_access_key="4126" + "0" * 40)
    _lost_lot(order, SKU, "4")

    choices = _choices(client, order)

    phrase = "A NFC-e desta encomenda já foi autorizada: para mudar, cancele e refaça a encomenda."
    for key in ("swap:BAGUETE:FENDU", "remove"):
        assert (choices[key]["enabled"], choices[key]["reason"]) == (False, phrase)
        assert choices[key]["message"] == ""
    assert choices["remove"]["conclude"]["items"] == []


def test_previa_recusada_fecha_tirar_o_item_com_a_frase_da_edicao(client, gerente, vitrine):
    """Pix ainda esperando o cliente com o valor antigo: a prévia levanta ``EditRefused``."""
    order = _baguete_e_cafe("WEB-PIX-ABERTO", payment={"method": "pix", "intent_ref": "INT-WEB-PIX-ABERTO"})
    PaymentService.create_intent(order.ref, order.total_q, "pix", gateway="mock", ref="INT-WEB-PIX-ABERTO")
    _lost_lot(order, SKU, "4")

    choice = _choices(client, order)["remove"]

    assert choice["enabled"] is False
    assert choice["reason"] == (
        "Há uma cobrança (Pix ou link) com o valor antigo esperando o cliente. "
        "Receba ou cancele essa cobrança antes de mudar o valor."
    )
    assert (choice["conclude"]["items"], choice["message"]) == ([], "")


def test_item_atrasado_sai_inteiro_e_a_mensagem_nao_diz_que_ele_nao_vem(client, gerente, vitrine, monkeypatch):
    """Lote de hoje depois da hora: nada "falta" contado; tirar o item tira o item inteiro,
    e a mensagem diz só o que a casa sabe (está atrasado)."""
    Product.objects.filter(sku=SKU).update(metadata={"ready_from": "12:00"})
    today = timezone.localdate()
    monkeypatch.setattr(timezone, "now", lambda: timezone.make_aware(datetime.combine(today, time(9))))
    order = _baguete_e_cafe("WEB-ATRASADO", days=0)
    craft.plan(Recipe.objects.get(output_sku=SKU), quantity=Decimal("10"), date=_day())
    _reserve(order, SKU, "4", day=_day(), quant=Quant.objects.get(sku=SKU, target_date=_day(), batch=""))
    monkeypatch.setattr(timezone, "now", lambda: timezone.make_aware(datetime.combine(today, time(13))))

    response = _get(client, order.ref)
    choices = {choice["key"]: choice for choice in response.json()["choices"]}

    assert response.json()["facts"] == [
        "4x Baguete de tradição. O lote de hoje está atrasado: devia ficar pronto às 12h e não começou.",
    ]
    assert list(choices) == ["reschedule", "remove", "cancel"]
    assert choices["remove"]["conclude"]["items"] == [{"line_id": "L2", "sku": "CAFE", "qty": "2"}]
    assert choices["reschedule"]["message"].startswith(f"{OPENING} {_happened('está atrasado', 'ATRASADO')}")
    assert "não vai ficar pronto" not in choices["reschedule"]["message"]


def test_o_que_a_producao_ainda_pode_fazer_a_mensagem_nao_da_como_perdido(client, gerente, vitrine):
    """Sem lote planejado para hoje: a Produção ainda resolve. A proposta diz "pode não ficar pronto"."""
    order = _baguete_e_cafe("WEB-SEM-LOTE", days=0)
    _reserve(order, SKU, "4", day=_day())

    choices = _choices(client, order)

    assert list(choices) == ["reschedule", "remove", "cancel"]
    assert choices["reschedule"]["message"].startswith(
        f"{OPENING} {_happened('pode não ficar pronto hoje', 'LOTE')}"
    )


# ── Cancelar ─────────────────────────────────────────────────────────────────


def test_cancelar_sem_nada_cobrado_diz_isso_e_nao_promete_devolucao(client, gerente, vitrine):
    order = _baguete_e_cafe("WEB-SEM-COBRAR")
    _lost_lot(order, SKU, "4")

    choice = _choices(client, order)["cancel"]

    assert (choice["enabled"], choice["detail"]) == (True, "Nada foi cobrado do cliente.")
    assert choice["requires_manager_approval"] is False
    assert choice["conclude"] == {"kind": "cancel", "label": "Cancelar pedido", "href": "", "items": [], "payload_schema": {}}
    assert choice["message"] == (
        f"{OPENING} {_happened('não vai ficar pronto amanhã', 'COBRAR')} "
        "Se preferir, cancelo o pedido. Me avisa como fica melhor para você ✨"
    )


def test_cancelar_segue_a_regua_do_cancelar_do_detalhe(client, gerente, vitrine):
    """A mesma frase e a mesma trava do detalhe (``_cancel_capability``, ``_cancel_money_effect``)."""
    from shopman.backstage.projections.order_queue import build_operator_order

    order = _baguete_e_cafe("WEB-REGUA", status="ready")
    _pay_pix(order)
    _lost_lot(order, SKU, "4")
    order = Order.objects.get(pk=order.pk)

    choice = _choices(client, order)["cancel"]
    detail = build_operator_order(order, user=gerente)

    assert detail.can_cancel is False
    assert (choice["enabled"], choice["reason"]) == (False, detail.cancel_block_label)
    assert choice["detail"] == detail.cancel_money_effect == "R$ 62,00 serão estornados ao Pix do cliente."
    assert choice["message"] == ""


# ── A mensagem e a conversa ──────────────────────────────────────────────────


def test_toda_mensagem_e_proposta_na_voz_da_casa_e_nas_palavras_do_cliente(client, gerente, vitrine):
    stock.plan(Decimal("10"), vitrine["FENDU"], _day(1))
    order = _baguete_e_cafe()
    _pay_pix(order)
    _lost_lot(order, SKU, "4")

    choices = _choices(client, order)

    assert set(choices) == {"swap:BAGUETE:FENDU", "reschedule", "remove", "cancel"}
    for choice in choices.values():
        message = choice["message"]
        # Quem fala e com quem: o nome da loja (do Shop) e o primeiro nome do cliente.
        assert message.startswith("Oi, Nelson! Aqui é da Nelson Boulangerie 💛")
        assert "Nelson Dias" not in message
        # O pedido pelo final do ref, como o balcão fala.
        assert "do seu pedido N75" in message
        # Sem travessão, sem palavra de bastidor, sem quebra de linha.
        assert "—" not in message and "–" not in message and "\n" not in message
        lowered = message.lower()
        for jargon in ("lote", "reserva", "fornada", "produção"):
            assert jargon not in lowered
        # No máximo um 💛 e um ✨, e nenhum outro emoji.
        assert (message.count("💛"), message.count("✨")) == (1, 1)
        assert all(ord(char) < 0x2600 for char in message.replace("💛", "").replace("✨", ""))
    # Proposta, não comunicado: o que mexe no pedido pergunta, e o cancelar se oferece.
    for key in ("swap:BAGUETE:FENDU", "reschedule", "remove"):
        assert "Posso " in choices[key]["message"] and "?" in choices[key]["message"]
    assert "Se preferir, cancelo o pedido" in choices["cancel"]["message"]
    # O dinheiro, quando há: quanto e por onde volta.
    assert "devolver R$ 44,00 pelo Pix" in choices["remove"]["message"]
    assert "devolvo R$ 62,00 pelo Pix" in choices["cancel"]["message"]
    assert "R$" not in choices["swap:BAGUETE:FENDU"]["message"]
    assert "R$" not in choices["reschedule"]["message"]


def test_a_conversa_do_whatsapp_ja_leva_a_mensagem(client, gerente, vitrine):
    order = _baguete_e_cafe()
    _lost_lot(order, SKU, "4")

    body = _get(client, order.ref).json()

    assert body["contact"] == {"enabled": True, "reason": ""}
    for choice in body["choices"]:
        url = urlsplit(choice["whatsapp_url"])
        assert (url.scheme, url.netloc, url.path) == ("https", "wa.me", "/5543999990000")
        # O texto vai inteiro e codificado: nada de espaço, acento ou emoji cru no endereço.
        assert url.query.startswith("text=") and url.query.isascii() and " " not in url.query
        assert unquote(url.query.removeprefix("text=")) == choice["message"] != ""


def test_pedido_sem_telefone_nao_tem_conversa_e_diz_por_que(client, gerente, vitrine):
    order = _baguete_e_cafe("WEB-SEM-FONE", customer={"name": "Nelson Dias"})
    _lost_lot(order, SKU, "4")

    body = _get(client, order.ref).json()

    assert body["contact"] == {"enabled": False, "reason": "Este pedido não tem WhatsApp do cliente."}
    # A mensagem continua pronta para copiar; só a conversa some.
    assert all(choice["message"] and choice["whatsapp_url"] == "" for choice in body["choices"])


def test_sem_nome_de_gente_a_mensagem_cumprimenta_sem_nome(client, gerente, vitrine):
    order = _baguete_e_cafe("WEB-SEM-NOME", customer={"name": "", "phone": "+5543999990000"})
    _lost_lot(order, SKU, "4")

    message = _choices(client, order)["reschedule"]["message"]

    assert message.startswith("Oi! Aqui é da Nelson Boulangerie 💛 O item Baguete de tradição do seu pedido NOME ")


def test_encomenda_de_outro_dia_diz_o_dia_por_extenso(client, gerente, vitrine):
    order = _baguete_e_cafe("WEB-SABADO", days=4)
    _lost_lot(order, SKU, "4", days=4)

    message = _choices(client, order)["reschedule"]["message"]

    day = _day(4)
    spoken = f"para {formats.date_format(day, 'l').lower()}, {formats.date_format(day, 'd/m')}"
    assert _happened(f"não vai ficar pronto {spoken}", "SABADO") in message


def test_dinheiro_volta_em_dinheiro_na_retirada_e_a_frase_do_operador_e_a_do_caixa(client, gerente, vitrine):
    """Pago em dinheiro no balcão: a diferença fica a devolver no caixa, e o cliente lê "em dinheiro na retirada"."""
    order = _baguete_e_cafe("WEB-DINHEIRO")
    intent = PaymentService.settle(order.ref, order.total_q, "cash", idempotency_key="g08-resolver-dinheiro")
    order.data["payment"] = {"method": "cash", "intent_ref": intent.ref}
    order.save(update_fields=["data"])
    _lost_lot(order, SKU, "4")

    choices = _choices(client, order)

    assert choices["remove"]["detail"] == "R$ 44,00 em dinheiro ficam a devolver no caixa."
    assert choices["remove"]["requires_manager_approval"] is True
    assert "devolver R$ 44,00 em dinheiro na retirada?" in choices["remove"]["message"]
    assert choices["cancel"]["detail"] == "R$ 62,00 em dinheiro ficam a devolver no caixa."
    assert "devolvo R$ 62,00 em dinheiro." in choices["cancel"]["message"]


# ── A leitura fora da rota ───────────────────────────────────────────────────


def test_quem_nao_gerencia_pedidos_recebe_toda_escolha_fechada(django_user_model, vitrine):
    """A rota já exige a permissão; a leitura repete a régua para quem a chamar de outro lugar."""
    stock.plan(Decimal("10"), vitrine["FENDU"], _day(1))
    order = _baguete_e_cafe("WEB-LEITURA")
    _pay_pix(order)
    _lost_lot(order, SKU, "4")
    visitante = django_user_model.objects.create_user(username="visitante-resolver", is_staff=True)

    resolution = build_promise_resolution(Order.objects.get(pk=order.pk), user=visitante)

    assert [choice.kind for choice in resolution.choices] == ["swap", "reschedule", "remove", "cancel"]
    for choice in resolution.choices:
        assert (choice.enabled, choice.reason) == (False, "Identifique uma pessoa com permissão para gerenciar pedidos.")
        assert (choice.message, choice.whatsapp_url, choice.detail, choice.conclude.href) == ("", "", "", "")
        assert choice.conclude.items == () and choice.requires_manager_approval is False


def test_a_copy_da_proposta_nao_tem_travessao_nem_palavra_de_bastidor():
    """As frases moram em ``notification_copy`` (junto das outras frases ao cliente), e a regra vale na fonte."""
    texts = [
        *notification_copy.PROMISE_PROPOSAL_COPY.values(),
        *notification_copy.PROMISE_ITEM_SITUATION.values(),
        *notification_copy.PROMISE_REMOVED.values(),
        *notification_copy.PROMISE_REFUND_ROUTE.values(),
    ]
    for text in texts:
        assert "—" not in text and "–" not in text
        for jargon in ("lote", "reserva", "fornada"):
            assert jargon not in text.lower()
        assert text.count("💛") <= 1 and text.count("✨") <= 1
    # Toda proposta fecha com o ✨, e só a abertura leva o 💛: uma mensagem nunca soma dois.
    proposals = {key: text for key, text in notification_copy.PROMISE_PROPOSAL_COPY.items() if text.endswith("✨")}
    assert set(proposals) == {"swap", "swap_named", "reschedule", "remove_refund", "remove", "cancel_refund", "cancel"}
    assert all("💛" not in text for text in proposals.values())
    assert [key for key, text in notification_copy.PROMISE_PROPOSAL_COPY.items() if "💛" in text] == [
        "opening", "opening_without_shop",
    ]
