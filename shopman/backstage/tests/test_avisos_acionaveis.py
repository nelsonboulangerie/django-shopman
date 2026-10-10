"""Avisos acionáveis: todo aviso que pede um gesto leva aonde o gesto se faz.

Pedido do dono (09/10/2026): "Lote aguardando revisão de qualidade" tem que levar à
revisão de qualidade DAQUELE lote. O que este arquivo prende:

* o aviso da operação (``OperatorAlert``) leva ao app que resolve, com o registro no
  filtro: caminho relativo no próprio app, endereço inteiro noutro app;
* sem a URL do outro app, o aviso fica sem botão em vez de levar a um caminho que não
  existe no app de onde foi tocado;
* o aviso pessoal ("Para você") sai com o endereço do app da condição e um rótulo que
  diz aonde leva.
"""

from __future__ import annotations

from datetime import date

import pytest
from django.test import override_settings
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe

from shopman.backstage.api.notifications import _action_destination
from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections.alerts import alert_context_href
from shopman.shop.models import UserNotification
from shopman.shop.services.user_notifications import (
    PRODUCTION_QUALITY_REVIEW,
    _known_deep_link,
)

URLS = {
    "gestor": "https://gestor.example.test/",
    "production": "https://prod.example.test/",
    "pos": "https://pdv.example.test/",
    "bi": "https://bi.example.test/",
    "marketing": "https://mkt.example.test/",
    "purchase": "https://compras.example.test/",
}


def _alert(alert_type: str, order_ref: str = "") -> OperatorAlert:
    return OperatorAlert(type=alert_type, message="m", order_ref=order_ref)


@override_settings(SHOPMAN_SURFACE_URLS=URLS)
@pytest.mark.parametrize(
    ("alert_type", "order_ref", "surface", "href", "label"),
    (
        # No próprio app: o caminho, com o lote e o dia no filtro.
        ("production_low_yield", "WO-7", "production", "/quality?q=WO-7&date=2026-10-09", "Revisar a qualidade do lote"),
        # O mesmo aviso lido no Gestor: o endereço da Produção.
        (
            "production_low_yield",
            "WO-7",
            "orders",
            "https://prod.example.test/quality?q=WO-7&date=2026-10-09",
            "Revisar a qualidade do lote",
        ),
        # Aviso de pedido lido na Produção: o pedido no Gestor (era "/WEB-1" na Produção).
        ("courier_not_attended", "WEB-1", "production", "https://gestor.example.test/WEB-1", "Abrir o pedido"),
        ("courier_not_attended", "WEB-1", "orders", "/WEB-1", "Abrir o pedido"),
        # Os que não tinham destino nenhum.
        ("pos_drawer_left_open", "", "orders", "https://pdv.example.test/", "Abrir o PDV"),
        ("cash_shift_open_at_closing", "", "orders", "https://pdv.example.test/session", "Fechar o caixa"),
        ("cash_out_of_tolerance", "", "orders", "https://bi.example.test/cash", "Ver o caixa no B.I."),
        ("marketing_outbox_stuck", "", "orders", "https://mkt.example.test/", "Abrir a fila de decisões"),
        ("marketing_readiness_stale", "", "orders", "https://mkt.example.test/platforms", "Conferir as plataformas"),
        ("purchase_invoice_fiscal_divergence", "", "orders", "https://compras.example.test/", "Abrir o Compras"),
        ("ifood_store_closed_while_open", "", "orders", "/", "Conferir o iFood na Fila"),
        ("catalog_hidden_by_inactive_collection", "", "orders", "/catalog", "Abrir o Catálogo"),
        # Negociação do iFood: o pedido, já no bloco da resposta.
        ("ifood_negotiation_open", "IF-9", "orders", "/IF-9#ifood-negotiations", "Responder"),
    ),
)
def test_o_aviso_leva_aonde_se_resolve(alert_type, order_ref, surface, href, label):
    target_date = "2026-10-09" if alert_type.startswith("production_") else ""
    assert alert_context_href(_alert(alert_type, order_ref), surface=surface, target_date=target_date) == (href, label)


@override_settings(SHOPMAN_SURFACE_URLS={}, DEBUG=False)
def test_sem_a_url_do_outro_app_o_aviso_fica_sem_botao():
    assert alert_context_href(_alert("courier_not_attended", "WEB-1"), surface="production") == ("", "")
    # No próprio app o caminho basta.
    assert alert_context_href(_alert("courier_not_attended", "WEB-1"), surface="orders") == ("/WEB-1", "Abrir o pedido")


@override_settings(SHOPMAN_SURFACE_URLS=URLS)
@pytest.mark.parametrize(
    "alert_type",
    # Sistema (TI pelo e-mail crítico e Admin), cadastro só no Admin, ou fora do sistema.
    ("directive_backlog", "legal_parameter_stale", "certificate_expiring", "manychat_contact_erasure_due"),
)
def test_aviso_sem_tela_de_operador_fica_sem_botao(alert_type):
    assert alert_context_href(_alert(alert_type), surface="orders") == ("", "")


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(ref="aviso-qc", name="Pão de aviso", output_sku="AVISO-QC", batch_size=1)


@pytest.mark.django_db
def test_revisao_de_qualidade_leva_ao_lote_na_producao(recipe):
    work_order = craft.plan(recipe, 1, date=date(2026, 10, 9))
    path = _known_deep_link(PRODUCTION_QUALITY_REVIEW, f"work_order:{work_order.pk}")
    assert path == f"/quality?q={work_order.ref}&date=2026-10-09"

    notification = UserNotification(
        source_condition=PRODUCTION_QUALITY_REVIEW,
        source_ref=f"work_order:{work_order.pk}",
        action_url=path,
    )
    with override_settings(SHOPMAN_SURFACE_URLS=URLS):
        assert _action_destination(notification) == {
            "action_url": f"https://prod.example.test/quality?q={work_order.ref}&date=2026-10-09",
            "action_label": "Revisar a qualidade do lote",
        }
    with override_settings(SHOPMAN_SURFACE_URLS={}, DEBUG=False):
        assert _action_destination(notification)["action_url"] == path


def test_aviso_pessoal_sem_condicao_conhecida_mantem_o_caminho():
    notification = UserNotification(source_condition="", action_url="/account/sign-ins")
    assert _action_destination(notification) == {"action_url": "/account/sign-ins", "action_label": ""}
