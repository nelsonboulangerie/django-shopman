"""Avisos lidos num relance e entregues a quem pode agir (dono, 08/10/2026).

- A janela lê na ordem: origem, assunto, prazo, detalhe, ações. Origem e assunto
  são do tipo (``alert_specs``); todo tipo que interrompe tem prazo, o do mundo lá
  fora (``respond_by``) ou a régua da casa.
- Quem recebe é quem está logado. O financeiro de UM pedido é do gerente; o
  financeiro panorâmico (contagem, total do dia, livro contra gateway) só o dono vê.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse
from django.utils import timezone

from shopman.backstage.alert_specs import ALERT_SPECS, deadline_for, deadline_kind
from shopman.backstage.models import OperatorAlert
from shopman.shop.models import Shop


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Nelson Boulangerie")


@pytest.fixture
def gerente(db, shop):
    user = User.objects.create_user("gerente-avisos", password="pw", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    return user


def _alert(type_: str, **fields) -> OperatorAlert:
    return OperatorAlert.objects.create(type=type_, severity="error", message=f"alerta {type_}", **fields)


def test_financeiro_de_um_pedido_e_do_gerente_e_o_panoramico_so_do_dono(client, gerente):
    for type_ in ("payment_failed", "payment_disputed", "payment_insufficient", "payment_after_cancel"):
        _alert(type_, order_ref="WEB-1")
    for type_ in sorted(OperatorAlert.FINANCE_TYPES):
        _alert(type_)
    client.force_login(gerente)

    vistos = {a["type"] for a in client.get(reverse("api-backstage-alerts"), {"scope": "orders"}).json()["alerts"]}

    assert {"payment_failed", "payment_disputed", "payment_insufficient", "payment_after_cancel"} <= vistos
    assert not vistos & OperatorAlert.FINANCE_TYPES


def test_contagem_e_livro_sao_panoramicos():
    for type_ in ("cash_out_of_tolerance", "bi_cash_variance", "payment_ledger_drift", "payment_reconciliation_failed"):
        assert OperatorAlert.audience_for_type(type_) == "finance"


def test_todo_tipo_que_interrompe_tem_origem_assunto_e_regua():
    for type_, spec in ALERT_SPECS.items():
        assert spec.origin and spec.subject and spec.origin_icon.startswith("i-lucide-"), type_
        assert spec.deadline_minutes > 0, type_


def test_whatsapp_tem_a_regua_de_5_minutos(db):
    alert = _alert("concierge_handoff")
    assert deadline_for(alert) == alert.created_at + timedelta(minutes=5)
    assert deadline_kind(alert) == "house"


def test_prazo_do_mundo_la_fora_vence_a_regua(db):
    prazo = timezone.now() + timedelta(minutes=7)
    alert = _alert("ifood_negotiation_open", order_ref="IFOOD-1", respond_by=prazo)
    assert deadline_for(alert) == prazo
    assert deadline_kind(alert) == "external"


def test_a_projecao_entrega_origem_assunto_e_prazo(client, gerente):
    _alert("concierge_handoff")
    client.force_login(gerente)

    [aviso] = [
        a for a in client.get(reverse("api-backstage-alerts"), {"scope": "orders"}).json()["alerts"]
        if a["type"] == "concierge_handoff"
    ]

    assert (aviso["origin_label"], aviso["subject"], aviso["deadline_kind"]) == (
        "WhatsApp", "Cliente esperando atendente", "house",
    )
    assert aviso["origin_icon"] == "i-lucide-message-circle"
    assert aviso["respond_by_iso"]


def test_aviso_da_casa_com_mais_de_um_dia_nao_interrompe(db):
    alert = _alert("concierge_handoff")
    OperatorAlert.objects.filter(pk=alert.pk).update(created_at=timezone.now() - timedelta(days=2))
    alert.refresh_from_db()
    assert deadline_for(alert) is None
    assert deadline_kind(alert) == ""


def test_aviso_sem_regua_nao_ganha_prazo(db):
    alert = _alert("stock_low")
    assert deadline_for(alert) is None
    assert deadline_kind(alert) == ""
