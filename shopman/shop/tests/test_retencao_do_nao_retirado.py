"""A retenção do não retirado: 40% provisório dos itens feitos para a encomenda (DEV-2026-089).

Decisão do dono (24/11/2026): "os itens de revenda voltam inteiros; dos itens feitos
para a encomenda, retemos até 40% do valor para cobrir o custo de produção, e o
restante volta pelo mesmo meio de pagamento". O percentual mora na loja
(``Shop.defaults["no_show"]["retention"]``), não no código; o código guarda só o teto
que os Termos publicam, e esta trava confere o teto com o texto de ``termos.vue``.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.models import Shop
from shopman.shop.policies.no_show_policy import TERMS_RETENTION_CAP_PERCENT, NoShowPolicy
from shopman.shop.services import no_show
from shopman.shop.tests import _no_show as world

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]

ROOT = Path(__file__).resolve().parents[3]


# ── O teto é o dos Termos ────────────────────────────────────────────────────


def test_o_teto_do_codigo_e_o_percentual_que_os_termos_publicam():
    termos = (ROOT / "surfaces/storefront-nuxt/app/pages/termos.vue").read_text(encoding="utf-8")

    published = [int(n) for n in re.findall(r"retemos\s+até\s+(\d+)%", termos)]

    assert published == [TERMS_RETENTION_CAP_PERCENT]


# ── A regra da loja ──────────────────────────────────────────────────────────


def test_a_regra_vem_da_loja_com_o_valor_e_a_data():
    policy = NoShowPolicy.from_defaults({"no_show": {"retention": {"percent": 40, "decided_at": "2026-11-24", "provisional": True}}})

    assert (policy.retention.percent, policy.retention.decided_at, policy.retention.provisional) == (40, "2026-11-24", True)
    assert policy.retention_refusal() == ""


@pytest.mark.parametrize("raw", [None, {}, {"percent": "40"}, {"percent": -1}, {"percent": 101}, {"percent": True}])
def test_sem_regra_valida_o_gesto_recusa(raw):
    block = {"retention": raw} if raw is not None else {}

    policy = NoShowPolicy.from_defaults({"no_show": block})

    assert policy.retention is None
    assert "não está configurada" in policy.retention_refusal()


def test_regra_acima_do_que_os_termos_publicam_recusa():
    policy = NoShowPolicy.from_defaults({"no_show": {"retention": {"percent": TERMS_RETENTION_CAP_PERCENT + 5}}})

    assert "passa do que os Termos publicam" in policy.retention_refusal()


# ── A conta de cada linha ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ({"destiny": no_show.LOSS, "produced": True, "value_q": 8900}, 3560),  # feito aqui e perdido
        ({"destiny": no_show.LOSS, "produced": True, "value_q": 935}, 374),  # 373,99 arredonda para 374
        ({"destiny": no_show.LOSS, "produced": False, "value_q": 3000}, 0),  # revenda volta inteira
        ({"destiny": no_show.RESTOCK, "produced": True, "value_q": 1870}, 0),  # voltou à venda
    ],
)
def test_a_loja_retem_o_percentual_so_da_perda_produzida_aqui(line, expected):
    assert no_show.line_retained_q(line, 40) == expected


# ── O gesto inteiro ──────────────────────────────────────────────────────────


@pytest.fixture
def fim_do_expediente(monkeypatch):
    world.make_shop()
    for sku, price in (("CROIS", 935), ("BOLO", 3000), ("GELEIA", 2500)):
        world.product(sku, price_q=price)
        world.lot(sku)
    world.produced("CROIS")
    world.produced("BOLO")
    moment = world.at(19, 5)
    monkeypatch.setattr(timezone, "now", lambda: moment)


def test_revenda_volta_inteira_e_o_bolo_feito_aqui_retem_40_por_cento(fim_do_expediente):
    # Croissant com estoque baixado: volta à venda. Bolo e geleia sem estoque baixado: perda.
    order = world.ready_order(
        "RET-40", [("CROIS", 2, 935), ("BOLO", 1, 3000), ("GELEIA", 1, 2500)], held=False, ready_at=world.at(14),
    )
    order.data["hold_ids"] = [world.fulfilled_hold("CROIS", 2, order_ref="RET-40")]
    order.save(update_fields=["data", "updated_at"])
    world.pay(order, "pix")
    order.refresh_from_db()

    block = no_show.mark_not_picked_up(order, actor="ana", approved_by="gerente")

    by_sku = {line["sku"]: line for line in block["lines"]}
    assert (by_sku["CROIS"]["destiny"], by_sku["CROIS"]["retained_q"]) == (no_show.RESTOCK, 0)
    assert (by_sku["BOLO"]["destiny"], by_sku["BOLO"]["retained_q"]) == (no_show.LOSS, 1200)
    assert (by_sku["GELEIA"]["destiny"], by_sku["GELEIA"]["retained_q"]) == (no_show.LOSS, 0)
    assert (block["paid_q"], block["retained_q"], block["refund_q"]) == (7370, 1200, 6170)
    assert block["retention"] == {"percent": 40, "decided_at": "2026-11-24", "provisional": True}


def test_sem_a_regra_na_loja_o_gesto_nao_existe(fim_do_expediente):
    shop = Shop.load()
    shop.defaults = {}
    shop.save(update_fields=["defaults"])
    order = world.ready_order("RET-SEM-REGRA", [("BOLO", 1, 3000)], held=False, ready_at=world.at(14))

    assert "não está configurada" in no_show.eligibility_reason(order)
    with pytest.raises(no_show.NoShowRefused):
        no_show.mark_not_picked_up(order, actor="ana", approved_by="gerente")
    order.refresh_from_db()
    assert order.status == Order.Status.READY


# ── A migração grava a regra na loja do ar ───────────────────────────────────


def test_a_migracao_grava_a_regra_e_respeita_a_que_ja_existe():
    from django.apps import apps

    migration = importlib.import_module("shopman.shop.migrations.0141_retencao_do_nao_retirado")
    sem_regra = Shop.objects.create(name="Sem regra", defaults={"menu": {"x": 1}})

    migration.add_retention(apps, None)
    sem_regra.refresh_from_db()

    assert sem_regra.defaults["no_show"]["retention"] == {"percent": 40, "decided_at": "2026-11-24", "provisional": True}
    assert sem_regra.defaults["menu"] == {"x": 1}

    sem_regra.defaults["no_show"]["retention"]["percent"] = 30
    sem_regra.save(update_fields=["defaults"])
    migration.add_retention(apps, None)
    sem_regra.refresh_from_db()
    assert sem_regra.defaults["no_show"]["retention"]["percent"] == 30
