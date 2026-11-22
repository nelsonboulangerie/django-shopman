"""A "Próxima livre" reservada pelo servidor, e quem abriu a comanda (#2443, PDV-19).

O quadro escolhia a comanda livre no navegador e abria pelo número: duas estações
que tocavam juntas abriam a MESMA comanda, e a segunda carregava a conta da
primeira. Abrir de novo também reescrevia o ``pos_operator``, e o quadro não sabia
de quem era a comanda vazia. Aqui:

- a reserva escolhe a menor livre e cria a conta; quem perde a corrida leva a
  seguinte, nunca a mesma (a trava é a do banco, uma conta aberta por comanda);
- a conta guarda quem a abriu (``pos_opened_by``), e reabrir não muda isso;
- o abrir diz se foi ELE que pôs a comanda em uso (``created``), que é a deixa do
  PDV para devolver ao quadro a comanda de balcão que deixou vazia.
"""

from __future__ import annotations

from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from shopman.cashman import services as cash
from shopman.cashman.models import Terminal
from shopman.orderman.models import Session

from shopman.backstage.models import POSTab
from shopman.backstage.projections.pos import build_pos_tabs
from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import PosIntentError

pytestmark = pytest.mark.django_db

NEXT_FREE_URL = "/api/v1/backstage/pos/tabs/next-free/"


@pytest.fixture
def pdv():
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    Channel.objects.create(
        ref="pdv", name="PDV", is_active=True,
        config={"payment": {"method": "cash", "timing": "external"}, "stock": {"check_on_commit": False}},
    )
    for number in (1, 2, 3):
        POSTab.objects.create(ref=str(number).zfill(8), label=str(number))


@pytest.fixture
def balcao(client, pdv):
    op = get_user_model().objects.create_user(username="fran", password="x", is_staff=True, first_name="Fran")
    op.user_permissions.add(Permission.objects.get(codename="operate_pos"))
    client.force_login(op)
    terminal = Terminal.default()
    bind_station(client, terminal.ref)
    cash.open_shift(operator=op, terminal=terminal, float_q=0)
    return client


def _open(ref: str, operator: str = "fran") -> Session:
    return pos_service.open_pos_tab(channel_ref="pdv", tab_ref=ref, actor="t", operator_username=operator)


def test_reserva_leva_a_menor_livre(pdv):
    _open("1")

    session = pos_service.reserve_next_free_pos_tab(channel_ref="pdv", operator_username="fran")

    assert session.handle_ref == "00000002"
    assert session.data["tab_ref"] == "00000002"


def test_sem_livre_abre_a_seguinte_a_maior(pdv):
    for ref in ("1", "2", "3"):
        _open(ref)

    session = pos_service.reserve_next_free_pos_tab(channel_ref="pdv", operator_username="fran")

    assert session.handle_ref == "00000004"
    assert POSTab.objects.filter(ref="00000004").exists()


def test_duas_reservas_seguidas_nunca_levam_a_mesma(pdv):
    first = pos_service.reserve_next_free_pos_tab(channel_ref="pdv", operator_username="fran")
    second = pos_service.reserve_next_free_pos_tab(channel_ref="pdv", operator_username="joyce")

    assert {first.handle_ref, second.handle_ref} == {"00000001", "00000002"}


def test_quem_perde_a_corrida_leva_a_seguinte(pdv):
    """A outra estação criou a conta da 1 entre a leitura e a criação desta."""
    rival = _open("1", operator="joyce")
    reads = iter(["00000001", "00000002"])

    with mock.patch.object(pos_service, "_next_free_numeric_tab_ref", side_effect=lambda _ref: next(reads)):
        session = pos_service.reserve_next_free_pos_tab(channel_ref="pdv", operator_username="fran")

    assert session.handle_ref == "00000002"
    assert Session.objects.get(pk=rival.pk).data["pos_opened_by"] == "joyce"
    assert Session.objects.filter(channel_ref="pdv", state="open", handle_ref="00000001").count() == 1


def test_disputa_sem_fim_recusa_com_voz_de_balcao(pdv):
    _open("1", operator="joyce")

    with mock.patch.object(pos_service, "_next_free_numeric_tab_ref", return_value="00000001"):
        with pytest.raises(PosIntentError) as refused:
            pos_service.reserve_next_free_pos_tab(channel_ref="pdv", operator_username="fran")

    assert refused.value.status == 409
    assert "Próxima livre" in refused.value.message


def test_quem_abriu_fica_mesmo_quando_outra_estacao_reabre(pdv):
    session = _open("2", operator="fran")
    _open("2", operator="joyce")

    data = Session.objects.get(pk=session.pk).data
    assert data["pos_opened_by"] == "fran"
    assert data["pos_operator"] == "joyce"


def test_o_quadro_diz_quem_abriu_pelo_primeiro_nome(pdv):
    get_user_model().objects.create_user(username="fran", password="x", first_name="Fran")
    _open("2", operator="fran")

    card = next(tab for tab in build_pos_tabs(channel_ref="pdv") if tab.ref == "00000002")

    assert card.opened_by_display == "Fran"


def test_api_reserva_e_diz_que_criou(balcao):
    _open("1", operator="joyce")

    response = balcao.post(NEXT_FREE_URL, content_type="application/json")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["tab_ref"] == "00000002"
    assert body["created"] is True
    session = Session.objects.get(session_key=body["session_key"])
    assert session.data["pos_opened_by"] == "fran"


def test_api_abrir_diz_se_foi_ele_que_pos_em_uso(balcao):
    first = balcao.post("/api/v1/backstage/pos/tabs/3/open/", content_type="application/json")
    again = balcao.post("/api/v1/backstage/pos/tabs/3/open/", content_type="application/json")

    assert first.json()["created"] is True
    assert again.json()["created"] is False
    assert first.json()["session_key"] == again.json()["session_key"]
