"""GTIN recusado pela SEFAZ: o alerta leva ao produto, e o produto tem o gesto.

A nota que tomou a recusa já saiu de novo "SEM GTIN" (#1101) e o produto ficou
marcado (``metadata.gtin_nf_rejected``). Antes, o alerta mandava "limpar a marca
gtin_nf_rejected" e não havia tela para isso. O que esta suíte prende:

- o alerta é um por produto, está no sino do Gestor e leva ao produto no
  Catálogo ("Conferir o GTIN no Catálogo" → ``/catalog?sku=…&tab=social``);
- o detalhe do produto mostra a recusa (código, pedido, motivo);
- corrigir o GTIN e salvar apaga a marca, volta a mandar o GTIN na nota (a
  fonte passa a ser a embalagem) e fecha o alerta daquele produto;
- salvar o MESMO código recusado não apaga nada;
- "Manter sem GTIN na nota" registra quem conferiu, mantém a nota sem GTIN e
  fecha o alerta; não fecha o alerta de outro produto com SKU parecido.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.offerman.models import Product

from shopman.backstage.models import OperatorAlert
from shopman.shop.models import Shop
from shopman.shop.services import fiscal as fiscal_service
from shopman.shop.services.observability import create_operator_alert

pytestmark = pytest.mark.django_db

GTIN_RECUSADO = "7896064200011"
GTIN_EMBALAGEM = "3088542500285"
DETAIL_URL = "/api/v1/backstage/catalog/product/{sku}/"


@pytest.fixture
def gestor(db):
    Shop.objects.create(name="Nelson Boulangerie")
    user = User.objects.create_user("gestor-gtin", password="pw", is_staff=True)
    for codename in ("manage_orders", "manage_catalog"):
        user.user_permissions.add(
            Permission.objects.get(content_type=ContentType.objects.get(app_label="shop", model="shop"), codename=codename)
        )
    return user


@pytest.fixture
def agua(db):
    product = Product.objects.create(
        sku="AGUA", name="Água 500 ml", unit="un", base_price_q=500, is_published=True, is_sellable=True,
        metadata={"social": {"gtin": GTIN_RECUSADO}},
    )
    fiscal_service.mark_gtin_rejected(
        "AGUA", gtin=GTIN_RECUSADO, code="890", reason="Rejeicao: GTIN inexistente no CCG [nItem:1]", order_ref="WEB-7",
    )
    product.refresh_from_db()
    return product


def _alert_for(sku: str, order_ref: str = "WEB-7") -> None:
    create_operator_alert(
        type=fiscal_service.GTIN_REJECTED_ALERT_TYPE,
        severity="warning",
        order_ref=order_ref,
        message=f"A SEFAZ recusou o GTIN de {sku}.",
        dedupe_key=fiscal_service.gtin_rejected_alert_dedupe_key(order_ref, sku),
    )


def _open_alerts() -> set[str]:
    return {
        fiscal_service.gtin_rejected_alert_sku(message)
        for message in OperatorAlert.objects.filter(
            type=fiscal_service.GTIN_REJECTED_ALERT_TYPE, resolved_at__isnull=True,
        ).values_list("message", flat=True)
    }


def _patch(client, sku: str, payload: dict):
    url = DETAIL_URL.format(sku=sku)
    action = client.get(url).json()["action"]
    return client.patch(
        url, {**action["payload_schema"], "patch": payload},
        content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )


def test_o_alerta_esta_no_sino_do_gestor_e_leva_ao_produto(client, gestor, agua):
    _alert_for("AGUA")
    client.force_login(gestor)

    alertas = client.get(reverse("api-backstage-alerts"), {"scope": "orders"}).json()["alerts"]

    [alerta] = [a for a in alertas if a["type"] == fiscal_service.GTIN_REJECTED_ALERT_TYPE]
    abrir = next(x for x in alerta["actions"] if x["kind"] == "open_alert_context")
    assert (abrir["label"], abrir["href"]) == ("Conferir o GTIN no Catálogo", "/catalog?sku=AGUA&tab=social")
    assert "Dedupe" not in alerta["message"]


def test_o_detalhe_do_produto_mostra_a_recusa(client, gestor, agua):
    client.force_login(gestor)

    recusa = client.get(DETAIL_URL.format(sku="AGUA")).json()["product"]["gtin_rejected"]

    assert recusa["gtin"] == GTIN_RECUSADO
    assert (recusa["code"], recusa["order_ref"], recusa["confirmed"]) == ("890", "WEB-7", False)
    assert "CCG" in recusa["reason"]


def test_produto_sem_recusa_nao_tem_o_bloco_nem_aceita_a_confirmacao(client, gestor, agua):
    Product.objects.create(sku="PAO", name="Pão", unit="un", base_price_q=100)
    client.force_login(gestor)

    assert client.get(DETAIL_URL.format(sku="PAO")).json()["product"]["gtin_rejected"] is None
    assert _patch(client, "PAO", {"gtin_rejected": {"confirmed": True}}).status_code == 400


def test_corrigir_o_gtin_apaga_a_marca_e_fecha_o_alerta(client, gestor, agua):
    _alert_for("AGUA")
    client.force_login(gestor)

    resp = _patch(client, "AGUA", {"social": {"gtin": GTIN_EMBALAGEM}})

    assert resp.status_code == 200, resp.json()
    assert resp.json()["product"]["gtin_rejected"] is None
    agua.refresh_from_db()
    assert fiscal_service.GTIN_NF_REJECTED_KEY not in agua.metadata
    assert agua.metadata["gtin_source"].startswith("embalagem, gestor-gtin, ")
    # A próxima nota volta a levar o GTIN.
    assert fiscal_service._trusted_gtin(agua.metadata) == GTIN_EMBALAGEM
    assert _open_alerts() == set()


def test_salvar_o_mesmo_codigo_recusado_nao_apaga_nada(client, gestor, agua):
    _alert_for("AGUA")
    client.force_login(gestor)

    resp = _patch(client, "AGUA", {"social": {"brand": "Crystal", "gtin": GTIN_RECUSADO}})

    assert resp.status_code == 200, resp.json()
    agua.refresh_from_db()
    assert agua.metadata[fiscal_service.GTIN_NF_REJECTED_KEY]["code"] == "890"
    assert fiscal_service._trusted_gtin(agua.metadata) == ""
    assert _open_alerts() == {"AGUA"}


def test_manter_sem_gtin_registra_quem_conferiu_e_fecha_so_o_alerta_dele(client, gestor, agua):
    Product.objects.create(sku="AGUA-500", name="Água 1,5 l", unit="un", base_price_q=900)
    _alert_for("AGUA")
    _alert_for("AGUA-500", order_ref="WEB-8")
    client.force_login(gestor)

    resp = _patch(client, "AGUA", {"gtin_rejected": {"confirmed": True}})

    assert resp.status_code == 200, resp.json()
    recusa = resp.json()["product"]["gtin_rejected"]
    assert (recusa["confirmed"], recusa["confirmed_by"]) == (True, "gestor-gtin")
    agua.refresh_from_db()
    # A marca fica: a nota continua saindo sem GTIN, e o GTIN do cadastro não se perde.
    assert fiscal_service._trusted_gtin(agua.metadata) == ""
    assert agua.metadata["social"]["gtin"] == GTIN_RECUSADO
    assert _open_alerts() == {"AGUA-500"}


def test_a_confirmacao_nao_se_desfaz_por_patch(client, gestor, agua):
    client.force_login(gestor)

    assert _patch(client, "AGUA", {"gtin_rejected": {"confirmed": False}}).status_code == 400
    assert _patch(client, "AGUA", {"gtin_rejected": {"gtin": "1"}}).status_code == 400
