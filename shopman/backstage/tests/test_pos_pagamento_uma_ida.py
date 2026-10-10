"""O Pagamento do PDV pede o total numa ida só ao servidor.

Medido em 10/10/2026: abrir o Pagamento era salvar a comanda, reler a projeção do
terminal, reabrir a comanda, reler a projeção de novo e só então revisar. Cinco
idas em série; no alpha o dono esperou 24 s pelo total. Agora o salvar devolve a
revisão junto (``tabs/save/?review=1``), e este arquivo trava o contrato:

1. a revisão que volta com o salvar é a MESMA que a revisão avulsa daria;
2. uma recusa da revisão vai no corpo e não desfaz o salvar;
3. o custo da ida tem teto (consultas), para não voltar a crescer por linha.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.cashman import services as cash
from shopman.cashman.models import Shift, Terminal
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.backstage.models import POSTab
from shopman.backstage.projections.pos import build_open_tab
from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import POS_SALE_INTENT_VERSION

pytestmark = pytest.mark.django_db

SAVE_URL = "/api/v1/backstage/pos/tabs/save/"
REVIEW_URL = "/api/v1/backstage/pos/sale/review/"
LINHAS = 10


@pytest.fixture
def balcao(client):
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    Channel.objects.create(
        ref="pdv",
        name="PDV",
        is_active=True,
        config={
            "payment": {"method": "cash", "timing": "external"},
            "stock": {"check_on_commit": False},
        },
    )
    POSTab.objects.create(ref="00000077", label="77")
    listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
    for i in range(LINHAS):
        product = Product.objects.create(
            sku=f"P{i:02d}", name=f"Produto {i}", base_price_q=900 + i, is_published=True, is_sellable=True,
        )
        ListingItem.objects.create(listing=listing, product=product, price_q=1000 + i)
    operator = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    operator.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(Shift), codename="operate_pos"),
    )
    client.force_login(operator)
    terminal = Terminal.default()
    bind_station(client, terminal.ref)
    shift = cash.open_shift(operator=operator, terminal=terminal, float_q=0)
    session = pos_service.open_pos_tab(channel_ref="pdv", tab_ref="77", actor="test", operator_username="marina")
    return {"client": client, "session": session, "shift": shift}


def _intent(session, *, linhas: int = LINHAS, revision: str | None = None) -> dict:
    return {
        "intent_version": POS_SALE_INTENT_VERSION,
        "tab_ref": "77",
        "tab_session_key": session.session_key,
        "expected_revision": revision or build_open_tab(session)["revision"],
        "items": [
            {
                "line_id": f"L{i:02d}",
                "sku": f"P{i:02d}",
                "name": f"Produto {i}",
                "qty": 2,
                "unit_price_q": 1000 + i,
                **({"discount": {"type": "percent", "value": 10, "reason": "cortesia"}} if i % 3 == 0 else {}),
            }
            for i in range(linhas)
        ],
        "manual_discount": {"type": "percent", "value": 5, "reason": "cortesia"},
        "fulfillment_type": "pickup",
        "payment_method": "cash",
        "payment_collection": "terminal",
        "client_request_id": "pagamento-uma-ida",
    }


def _post(client, url: str, body: dict):
    return client.post(url, data=json.dumps(body), content_type="application/json")


def test_salvar_com_revisao_devolve_a_mesma_revisao_da_chamada_avulsa(balcao):
    client, session = balcao["client"], balcao["session"]
    body = _intent(session)

    saved = _post(client, f"{SAVE_URL}?review=1", body)

    assert saved.status_code == 200, saved.content
    data = saved.json()
    assert data["revision"] != body["expected_revision"]
    assert "review_error" not in data
    avulsa = _post(client, REVIEW_URL, {**body, "expected_revision": data["revision"]})
    assert avulsa.status_code == 200, avulsa.content
    assert data["review"] == avulsa.json()["review"]
    assert data["review"]["total_q"] > 0


def test_sem_review_na_query_o_salvar_responde_como_sempre(balcao):
    client, session = balcao["client"], balcao["session"]

    saved = _post(client, SAVE_URL, _intent(session))

    assert saved.status_code == 200, saved.content
    assert "review" not in saved.json()
    assert "review_error" not in saved.json()


def test_recusa_da_revisao_vai_no_corpo_e_o_salvar_fica(balcao):
    client, session, shift = balcao["client"], balcao["session"], balcao["shift"]
    # Caixa fechado: a revisão recusa (`cash_shift_required`), o salvar não.
    cash.close_shift(shift, counted_q=0, actor=shift.opened_by)

    saved = _post(client, f"{SAVE_URL}?review=1", _intent(session))

    assert saved.status_code == 200, saved.content
    data = saved.json()
    assert "review" not in data
    assert data["review_error"]["status"] == 409
    assert data["review_error"]["error"]["code"] == "cash_shift_required"
    session.refresh_from_db()
    assert len(session.items) == LINHAS


def test_o_total_numa_ida_tem_teto_de_consultas(balcao):
    """Teto da ida inteira (salvar dez linhas novas + revisar), com folga pequena.

    Medido em 10/10/2026 depois da correção: ver o número impresso. Se este
    teste falhar, a ida do Pagamento voltou a crescer — confira o que entrou no
    caminho antes de subir o teto.
    """
    client, session = balcao["client"], balcao["session"]
    body = _intent(session)
    with CaptureQueriesContext(connection) as ctx:
        saved = _post(client, f"{SAVE_URL}?review=1", body)
    assert saved.status_code == 200, saved.content
    print(f"salvar+revisar {LINHAS} linhas novas: {len(ctx.captured_queries)} consultas")
    assert len(ctx.captured_queries) <= TETO_SALVAR_E_REVISAR

    # De novo, sem mudar nada: é o caso do autosave que já gravou tudo.
    again = {**body, "expected_revision": saved.json()["revision"]}
    with CaptureQueriesContext(connection) as ctx:
        resaved = _post(client, f"{SAVE_URL}?review=1", again)
    assert resaved.status_code == 200, resaved.content
    print(f"salvar+revisar sem mudança: {len(ctx.captured_queries)} consultas")
    assert len(ctx.captured_queries) <= TETO_SALVAR_E_REVISAR_SEM_MUDANCA


TETO_SALVAR_E_REVISAR = 180
TETO_SALVAR_E_REVISAR_SEM_MUDANCA = 105
