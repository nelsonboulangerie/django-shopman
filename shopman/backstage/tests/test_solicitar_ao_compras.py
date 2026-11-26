"""Solicitar ao Compras (#3664; decisão do dono ao aprovar o WP-F11, 26/11/2026).

"A Cozinha também vê 'Pedir no Compras'. Só que se não for alguém com permissão
para isso (Compras), eventualmente, vira uma Solicitação de Compra."

O que se mede aqui, pelos caminhos reais (estoque no Stockman, recusa da API da
Produção, cadastro de compra no Buyman, projeção do Compras):

- quem opera o Compras segue com o link "Pedir no Compras"; quem não opera recebe
  "Solicitar ao Compras", e nada vai ao fornecedor;
- a solicitação mora no cadastro de compra do insumo
  (``Material.metadata.purchase.internal_requests``), uma por (insumo, lote);
- o "Comprar" mostra a linha na voz da casa, com o primeiro nome de quem pediu, e
  o insumo entra na lista com pelo menos o que falta;
- a Central conta as solicitações abertas;
- a solicitação fecha sozinha quando o pedido sai ao fornecedor, volta se o
  pedido é cancelado, e se encerra quando o insumo chega.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from shopman.buyman.models import Material
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.stockman import stock
from shopman.stockman.models import Move, Position, PositionKind
from shopman.utils.formatting import format_clock

from shopman.backstage.projections.purchase import build_purchase
from shopman.backstage.services import purchase as purchase_service

pytestmark = pytest.mark.django_db

BUTTER = "INS-MANTEIGA-F11B"


@pytest.fixture
def producao(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja F11b")
    Position.objects.get_or_create(
        ref="vitrine", defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True}
    )
    position, _ = Position.objects.get_or_create(
        ref="producao",
        defaults={"name": "Produção", "kind": PositionKind.PHYSICAL, "is_saleable": False, "is_default": True},
    )
    return position


@pytest.fixture
def ficha(producao):
    """Brioche: 1 kg de manteiga por 10 (aproveitamento 1)."""
    recipe = Recipe.objects.create(
        ref="brioche-f11b", name="Brioche", output_sku="BRIOCHE-F11B", batch_size=Decimal("10")
    )
    RecipeItem.objects.create(recipe=recipe, input_sku=BUTTER, quantity=Decimal("1"), unit="kg")
    return recipe


@pytest.fixture
def manteiga(db):
    return Material.objects.create(sku=BUTTER, name="Manteiga", unit="kg")


@pytest.fixture
def cozinha(db):
    """Opera a produção e NÃO opera o Compras."""
    from shopman.backstage.tests.production_grants import grant_production_operator

    user = User.objects.create_user("diofer-f11b", password="pw", is_staff=True, first_name="Diofer Souza")
    return grant_production_operator(user)


def _projected_body(projection: dict, action: dict, **fields) -> dict:
    return {
        **fields,
        "projection_generated_at": projection["generated_at"],
        "source_revision": projection["source_revision"],
        "fresh_until": projection["fresh_until"],
        "contract_version": projection["contract_version"],
        "action_ref": action["ref"],
        "action_proof": action["proof"],
    }


def _aviso_da_abertura(client, ficha, producao, *, key: str = "start-f11b") -> dict:
    stock.receive(Decimal("0.7"), BUTTER, position=producao, reason="entrada do Compras", kind=Move.Kind.BUY)
    work_order = craft.plan(ficha, 10, date=date.today(), position_ref="producao")
    board = client.get(reverse("api-backstage-production")).json()["board"]
    action = next(item for item in board["actions"] if item["ref"] == f"start:{work_order.pk}")
    body = _projected_body(board, action, quantity="10", expected_rev=action["expected_rev"], idempotency_key=key)
    refused = client.post(reverse("api-backstage-wo-start", args=[work_order.pk]), body, content_type="application/json")
    assert refused.status_code == 409, refused.json()
    return refused.json()["error"]


def _solicitar(client, error: dict):
    possibility = next(item for item in error["possibilities"] if item["kind"] == "request_purchase")
    return client.post(
        reverse("api-backstage-production-purchase-request"),
        {"purchase_request_proof": possibility["proof"]},
        content_type="application/json",
    )


def _requests() -> list[dict]:
    material = Material.objects.get(sku=BUTTER)
    return list(((material.metadata or {}).get("purchase") or {}).get("internal_requests") or [])


def _comprar(sku: str = BUTTER):
    return next(item for item in build_purchase().materials if item.sku == sku)


def _pedir(ref: str, qty: str, *, user=None) -> None:
    purchase_service.request_purchase_from_production(
        work_order_ref=ref,
        product_name="Brioche",
        items=[purchase_service.ProductionPurchaseRequestItem(sku=BUTTER, quantity=Decimal(qty), unit="kg")],
        user=user,
    )


def test_quem_nao_opera_o_compras_recebe_solicitar_e_nao_o_link(client, ficha, producao, manteiga, cozinha, monkeypatch):
    monkeypatch.setattr("shopman.backstage.api.operations.purchase_surface_url", lambda user: "")
    client.force_login(cozinha)

    error = _aviso_da_abertura(client, ficha, producao)

    kinds = {item["kind"]: item for item in error["possibilities"]}
    assert "purchase" not in kinds
    assert kinds["request_purchase"]["label"] == "Solicitar ao Compras"
    assert kinds["request_purchase"]["proof"]
    assert kinds["confirm"]["label"] == "Abrir assim mesmo"


def test_quem_opera_o_compras_segue_com_o_link(client, ficha, producao, manteiga, cozinha, monkeypatch):
    monkeypatch.setattr("shopman.backstage.api.operations.purchase_surface_url", lambda user: "https://compras.example")
    client.force_login(cozinha)

    error = _aviso_da_abertura(client, ficha, producao)

    kinds = {item["kind"] for item in error["possibilities"]}
    assert "purchase" in kinds
    assert "request_purchase" not in kinds


def test_insumo_sem_cadastro_de_compra_nao_oferece_solicitar(client, ficha, producao, cozinha, monkeypatch):
    """Sem `Material`, o Compras não teria onde ver a solicitação: o botão não aparece."""
    monkeypatch.setattr("shopman.backstage.api.operations.purchase_surface_url", lambda user: "")
    client.force_login(cozinha)

    error = _aviso_da_abertura(client, ficha, producao)

    assert "request_purchase" not in {item["kind"] for item in error["possibilities"]}


def test_a_solicitacao_grava_no_cadastro_de_compra_e_nao_duplica(client, ficha, producao, manteiga, cozinha, monkeypatch):
    monkeypatch.setattr("shopman.backstage.api.operations.purchase_surface_url", lambda user: "")
    client.force_login(cozinha)
    error = _aviso_da_abertura(client, ficha, producao)

    first = _solicitar(client, error)
    again = _solicitar(client, error)

    assert first.status_code == 200, first.json()
    assert first.json() == {"requested_skus": [BUTTER], "detail": "Solicitado ao Compras."}
    assert again.status_code == 200
    [entry] = _requests()
    assert entry["status"] == "open"
    assert entry["quantity"] == "0.3"
    assert entry["unit"] == "kg"
    assert entry["product"] == "Brioche"
    assert entry["work_order_ref"] == error["work_order_ref"]
    assert entry["requested_by"] == "diofer-f11b"
    assert entry["requested_by_name"] == "Diofer"
    # Nada saiu para o fornecedor.
    manteiga.refresh_from_db()
    assert "request_status" not in (manteiga.metadata or {}).get("purchase", {})


def test_prova_adulterada_e_recusada(client, manteiga, cozinha):
    client.force_login(cozinha)

    refused = client.post(
        reverse("api-backstage-production-purchase-request"),
        {"purchase_request_proof": "nao-assinada"},
        content_type="application/json",
    )

    assert refused.status_code == 400
    assert refused.json()["field"] == "purchase_request_proof"
    assert _requests() == []


def test_o_comprar_mostra_a_linha_na_voz_da_casa(manteiga):
    agora = timezone.now()
    _pedir("WO-F11B-1", "0.3", user=User.objects.create_user("diofer-linha", first_name="Diofer"))

    row = _comprar()

    [request] = row.internalRequests
    assert request.line == f"Diofer pediu às {format_clock(timezone.localtime(agora))}: falta 300 g para o lote de Brioche."
    assert "—" not in request.line
    # A solicitação é o piso da reposição: o insumo entra no "Comprar".
    assert row.suggestedQty >= 0.3


def test_dois_lotes_no_mesmo_insumo_ficam_os_dois(manteiga):
    user = User.objects.create_user("diofer-dois", first_name="Diofer")
    _pedir("WO-A", "0.3", user=user)
    _pedir("WO-B", "0.5", user=user)

    assert [entry["work_order_ref"] for entry in _requests()] == ["WO-A", "WO-B"]
    assert _comprar().suggestedQty == 1.0


def test_a_central_conta_as_solicitacoes_abertas(manteiga):
    from shopman.backstage.projections.hub_queue import _Collected, _purchase_status

    _pedir("WO-HUB", "0.3")
    out = _Collected()

    _purchase_status(None, "", "Compras", timezone.now(), out)

    assert out.statuses["purchase"].summary == "1 solicitação da Produção"


def test_fecha_ao_enviar_o_pedido_volta_ao_cancelar_e_encerra_ao_receber(manteiga, monkeypatch):
    monkeypatch.setattr(
        purchase_service,
        "_queue_supplier_purchase_request",
        lambda material, reviewed, user=None: {
            "purchase_ref": "PC-F11B",
            "supplier_ref": "forn",
            "channel": "email",
            "recipient": "x@example.com",
            "contact_name": "",
            "dedupe_key": "k",
        },
    )
    _pedir("WO-CICLO", "0.3")

    purchase_service.send_purchase_request(BUTTER, reviewed=True)
    assert [entry["status"] for entry in _requests()] == ["ordered"]
    assert _comprar().internalRequests == ()

    purchase_service.cancel_purchase_request(BUTTER)
    assert [entry["status"] for entry in _requests()] == ["open"]
    assert len(_comprar().internalRequests) == 1

    with transaction.atomic():
        purchase_service._close_purchase_request(Material.objects.get(sku=BUTTER), internal="received")
    assert [entry["status"] for entry in _requests()] == ["received"]
    assert _comprar().internalRequests == ()
