"""`purge_synthetic_data`: o sintético sai, o cadastro do Dia 1 fica (decisão B1, D-029).

O que se prova aqui:

- todo modelo instalado tem destino declarado (modelo novo sem linha reprova);
- o ensaio executa e desfaz; o ``--apply`` grava e a segunda rodada não acha nada;
- ledger imutável (estoque, pagamento) sai, que é o único momento em que deve;
- contas de operador e estações pareadas ficam; conta e dispositivo de cliente saem;
- o ``--apply`` exige o nome do banco digitado e recusa com o go-live armado.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.apps import apps
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.utils import timezone
from shopman.guestman.models import Customer
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.orderman.models import Directive, Order, OrderItem
from shopman.payman.models import PaymentIntent
from shopman.stockman import stock
from shopman.stockman.models import Move, Position, Quant

from config import synthetic_purge

pytestmark = pytest.mark.django_db

def _db() -> str:
    return str(connection.settings_dict["NAME"])


@pytest.fixture(autouse=True)
def _go_live_desarmado(monkeypatch):
    monkeypatch.setenv("SHOPMAN_GO_LIVE", "false")
    monkeypatch.delenv("SHOPMAN_ADR015_FORCE", raising=False)


def _trusted_device(subject_type: str, subject_id: str, token: str):
    TrustedDevice = apps.get_model("doorman", "TrustedDevice")
    return TrustedDevice.objects.create(
        subject_type=subject_type, subject_id=subject_id, token_hash=token,
        expires_at=timezone.now() + timedelta(days=30),
    )


@pytest.fixture
def banco_do_ensaio():
    """Um pouco de cada lado: cadastro da casa e dado do ensaio."""
    product = Product.objects.create(sku="FENDU", name="Fendu", unit="un", base_price_q=900)
    listing = Listing.objects.create(ref="web-teste", name="Web teste")
    ListingItem.objects.create(listing=listing, product=product, price_q=900)

    operador = User.objects.create_user("joyce", is_staff=True)
    operador.groups.add(Group.objects.get_or_create(name="Gerente")[0])

    cliente = Customer.objects.create(ref="CLI-TESTE", first_name="Ana", phone="+5543999990001")
    conta_cliente = User.objects.create_user("cli-teste")
    apps.get_model("doorman", "CustomerUser").objects.create(user=conta_cliente, customer_id=cliente.uuid)
    _trusted_device("customer", str(cliente.uuid), "c" * 64)
    _trusted_device("station", "pdv-main", "s" * 64)

    order = Order.objects.create(ref="PDV-TESTE-1", channel_ref="pdv", status="completed", total_q=900)
    OrderItem.objects.create(
        order=order, line_id="L1", sku="FENDU", name="Fendu", qty=Decimal("1"),
        unit_price_q=900, line_total_q=900,
    )
    Directive.objects.create(topic="notification.send", payload={"order_ref": order.ref})
    PaymentIntent.objects.create(ref="PI-TESTE-1", order_ref=order.ref, method="pix", amount_q=900)

    vitrine = Position.objects.create(ref="vitrine-teste", name="Vitrine")
    stock.receive(Decimal("10"), "FENDU", vitrine, reason="ensaio")

    DeliveryDevice = apps.get_model("backstage", "DeliveryDevice")
    leitora = DeliveryDevice.objects.create(label="Leitora", identification="L-1", current_order=order)
    return {"operador": operador, "conta_cliente": conta_cliente, "leitora": leitora}


def test_todo_modelo_instalado_tem_destino_declarado():
    synthetic_purge.check_policy()


def test_modelo_sem_destino_recusa_antes_de_tocar_em_qualquer_coisa(monkeypatch, banco_do_ensaio):
    policy = dict(synthetic_purge.POLICY)
    policy.pop("orderman.Order")
    monkeypatch.setattr(synthetic_purge, "POLICY", policy)

    with pytest.raises(CommandError, match="orderman.Order"):
        call_command("purge_synthetic_data", "--apply", "--confirm-database", _db(), stdout=None)
    assert Order.objects.count() == 1


def test_cadastro_que_aponta_para_dado_apagado_recusa(monkeypatch):
    policy = dict(synthetic_purge.POLICY)
    policy["backstage.DeliveryDevice"] = synthetic_purge.Rule(synthetic_purge.KEEP, "sem detach")
    monkeypatch.setattr(synthetic_purge, "POLICY", policy)

    with pytest.raises(synthetic_purge.PolicyError, match="current_order"):
        synthetic_purge.check_policy()


def test_o_ensaio_executa_e_desfaz(banco_do_ensaio):
    report = synthetic_purge.run(apply=False)

    assert report.before["orderman.Order"] == 1
    assert report.after["orderman.Order"] == 0
    assert Order.objects.count() == 1
    assert Customer.objects.count() == 1
    assert Move.objects.count() == 1


def test_apply_apaga_o_ensaio_e_mantem_o_dia_1(banco_do_ensaio):
    call_command("purge_synthetic_data", "--apply", "--confirm-database", _db(), stdout=None)

    # dado do ensaio, inclusive o ledger que o app não deixa apagar
    assert Order.objects.count() == 0
    assert OrderItem.objects.count() == 0
    assert Directive.objects.count() == 0
    assert PaymentIntent.objects.count() == 0
    assert Customer.objects.count() == 0
    assert Quant.objects.count() == 0
    assert Move.objects.count() == 0
    assert not User.objects.filter(pk=banco_do_ensaio["conta_cliente"].pk).exists()
    TrustedDevice = apps.get_model("doorman", "TrustedDevice")
    assert list(TrustedDevice.objects.values_list("subject_type", flat=True)) == ["station"]

    # cadastro do Dia 1
    assert Product.objects.filter(sku="FENDU").exists()
    assert ListingItem.objects.filter(product__sku="FENDU").exists()
    assert Position.objects.filter(ref="vitrine-teste").exists()
    operador = User.objects.get(pk=banco_do_ensaio["operador"].pk)
    assert list(operador.groups.values_list("name", flat=True)) == ["Gerente"]
    leitora = banco_do_ensaio["leitora"]
    leitora.refresh_from_db()
    assert leitora.current_order_id is None


def test_segunda_rodada_nao_acha_nada(banco_do_ensaio):
    synthetic_purge.run(apply=True)
    report = synthetic_purge.run(apply=True)

    assert report.removed(synthetic_purge.PURGE) == 0
    assert report.removed(synthetic_purge.PURGE_ROWS) == 0
    assert report.before == report.after


def test_apply_exige_o_nome_do_banco_digitado(banco_do_ensaio):
    with pytest.raises(CommandError, match="--confirm-database"):
        call_command("purge_synthetic_data", "--apply", stdout=None)
    with pytest.raises(CommandError, match="--confirm-database"):
        call_command("purge_synthetic_data", "--apply", "--confirm-database", "outro", stdout=None)
    assert Order.objects.count() == 1


def test_apply_recusa_com_o_go_live_armado(monkeypatch, banco_do_ensaio):
    monkeypatch.setenv("SHOPMAN_GO_LIVE", "true")

    with pytest.raises(CommandError, match="go-live"):
        call_command("purge_synthetic_data", "--apply", "--confirm-database", _db(), stdout=None)
    assert Order.objects.count() == 1


def test_apply_recusa_em_producao(settings, banco_do_ensaio):
    settings.SHOPMAN_ENVIRONMENT = "production"

    with pytest.raises(CommandError, match="production"):
        call_command("purge_synthetic_data", "--apply", "--confirm-database", _db(), stdout=None)
    assert Order.objects.count() == 1


def test_retrato_do_dia_1_sem_dado_pessoal(banco_do_ensaio):
    report = synthetic_purge.run(apply=False)

    portrait = report.portrait
    assert portrait["orders"] == 0
    assert portrait["customers"] == 0
    assert portrait["stock_quants"] == 0
    assert set(portrait["accounts"]) >= {"joyce"}
    assert "cli-teste" not in portrait["accounts"]
