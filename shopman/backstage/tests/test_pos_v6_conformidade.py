"""V6-PDV: o que a conformidade com a v4 pediu do servidor.

- a comanda renomeada guarda o número ("Mesa 6" grande, "#1007" pequeno) e a hora
  em que abriu ("aberta 21:48");
- o vínculo OPCIONAL comanda × mesa (dono, 04/10/2026): escolher a mesa ao
  renomear, uma comanda por mesa, o Salão vê a mesa ocupada e o pedido leva a mesa;
- o "vai à cozinha" da linha nova sai do roteamento real, com o envio automático
  opcional por estação (desligado por padrão);
- PDV › Ajustes lê e edita impressoras, maquininhas, envio à cozinha e atalhos;
- a planta desenha a vitrine e caixa e a entrada;
- o fim do dia traz a forma do movimento por hora (sem valores) e quem fecha.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from shopman.cashman.models import Terminal
from shopman.offerman.models import Collection, CollectionItem, Product
from shopman.orderman.models import Session

from shopman.backstage.models import DeliveryDevice, KDSInstance, POSTab, SeatingFixture, SeatingSpot
from shopman.backstage.projections.closing import build_day_closing
from shopman.backstage.projections.pos import build_open_tab, build_pos_tabs
from shopman.backstage.projections.seating import build_seating
from shopman.backstage.services.pos_seating import link_tab_to_spot
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.services.kds import kitchen_routes_for_skus
from shopman.shop.services.pos_intent import PosIntentError

pytestmark = pytest.mark.django_db


@pytest.fixture
def loja(db):
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
    POSTab.objects.create(ref="00001007", label="1007")
    POSTab.objects.create(ref="00001008", label="1008")


def _open(tab_ref: str) -> Session:
    opened = build_open_tab(pos_service.open_pos_tab(
        channel_ref="pdv", tab_ref=tab_ref, actor="pos:alice", operator_username="alice",
    ))
    return Session.objects.get(session_key=opened["tab_session_key"])


def _operador(*codenames: str):
    user = get_user_model().objects.create_user("bruna", password="x", is_staff=True, first_name="Bruna")
    for codename in codenames or ("operate_pos",):
        user.user_permissions.add(Permission.objects.get(content_type__app_label="cashman", codename=codename))
    return get_user_model().objects.get(pk=user.pk)


# ── "Mesa 6" grande, "#1007" pequeno, "aberta 21:48" ──────────────────────


def test_comanda_renomeada_guarda_o_numero_e_a_hora_de_abertura(loja):
    session = _open("1007")
    pos_service.rename_pos_tab(
        channel_ref="pdv", session_key=session.session_key, new_tab_ref="Mesa 6",
        actor="pos:alice", operator_username="alice",
    )
    session.refresh_from_db()
    payload = build_open_tab(session)
    assert payload["tab_display"] == "Mesa 6"
    assert payload["tab_number"] == "1007"
    assert payload["opened_at_display"]

    # O segundo renomear não troca o número.
    pos_service.rename_pos_tab(
        channel_ref="pdv", session_key=session.session_key, new_tab_ref="Varanda",
        actor="pos:alice", operator_username="alice",
    )
    session.refresh_from_db()
    assert build_open_tab(session)["tab_number"] == "1007"


def test_comanda_nunca_renomeada_tem_o_proprio_numero(loja):
    payload = build_open_tab(_open("1007"))
    assert payload["tab_number"] == "1007"


# ── Vínculo opcional comanda × mesa ──────────────────────────────────────


def test_mesa_vinculada_uma_comanda_por_mesa_e_o_salao_ve_ocupada(loja):
    SeatingSpot.objects.create(ref="mesa-4", label="Mesa 4", seats=4)
    first = _open("1007")
    second = _open("1008")

    link_tab_to_spot(
        channel_ref="pdv", session_key=first.session_key, seating_spot_ref="mesa-4", operator_username="alice",
    )
    first.refresh_from_db()
    assert build_open_tab(first)["seating_spot_ref"] == "mesa-4"
    assert build_seating()["open_tabs"]["mesa-4"]["session_key"] == first.session_key
    tabs = {tab.ref: tab for tab in build_pos_tabs(channel_ref="pdv")}
    assert tabs["00001007"].seating_spot_ref == "mesa-4"

    with pytest.raises(PosIntentError) as exc:
        link_tab_to_spot(
            channel_ref="pdv", session_key=second.session_key, seating_spot_ref="mesa-4", operator_username="alice",
        )
    assert exc.value.code == "seating_spot_in_use"

    link_tab_to_spot(
        channel_ref="pdv", session_key=first.session_key, seating_spot_ref="", operator_username="alice",
    )
    first.refresh_from_db()
    assert "seating_spot_ref" not in first.data
    assert build_seating()["open_tabs"] == {}


def test_renomear_pela_api_com_a_mesa_liga_o_vinculo(loja, client):
    SeatingSpot.objects.create(ref="mesa-6", label="Mesa 6", seats=4)
    session = _open("1007")
    client.force_login(_operador())
    response = client.post(
        "/api/v1/backstage/pos/tabs/rename/",
        data=json.dumps({
            "session_key": session.session_key,
            "expected_revision": build_open_tab(session)["revision"],
            "new_tab_ref": "Mesa 6",
            "seating_spot_ref": "mesa-6",
        }),
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    tab = response.json()["tab"]
    assert tab["tab_display"] == "Mesa 6"
    assert tab["tab_number"] == "1007"
    assert tab["seating_spot_ref"] == "mesa-6"


def test_mesa_que_nao_esta_no_salao_e_recusada(loja):
    session = _open("1007")
    with pytest.raises(PosIntentError) as exc:
        link_tab_to_spot(
            channel_ref="pdv", session_key=session.session_key, seating_spot_ref="nao-existe",
            operator_username="alice",
        )
    assert exc.value.code == "seating_spot_not_found"


# ── "vai à cozinha" pelo roteamento real, envio automático por estação ──


def test_roteamento_diz_a_estacao_e_o_envio_automatico_comeca_desligado(loja):
    bebidas = Collection.objects.create(ref="bebidas", name="Bebidas")
    cafe = Product.objects.create(sku="CAFE", name="Café", base_price_q=500, is_published=True, is_sellable=True)
    CollectionItem.objects.create(collection=bebidas, product=cafe, is_primary=True)
    station = KDSInstance.objects.create(ref="bar", name="Bar", type="picking")
    station.collections.add(bebidas)

    assert kitchen_routes_for_skus(["CAFE"]) == {"CAFE": {"station": "Bar", "auto_fire": False}}

    station.config = {"auto_fire": True}
    station.save()
    assert kitchen_routes_for_skus(["CAFE"])["CAFE"]["auto_fire"] is True


def test_sem_estacao_ativa_nada_vai_a_cozinha(loja):
    Product.objects.create(sku="GELEIA", name="Geleia", base_price_q=500, is_published=True, is_sellable=True)
    assert kitchen_routes_for_skus(["GELEIA"]) == {}


# ── PDV › Ajustes ────────────────────────────────────────────────────────


def test_ajustes_le_e_grava_cada_aba(loja, client):
    terminal = Terminal.objects.create(ref="balcao", label="Balcão", metadata={})
    Collection.objects.create(ref="doces", name="Doces")
    KDSInstance.objects.create(ref="forno", name="Forno", type="prep")
    client.force_login(_operador("operate_pos", "change_terminal"))
    url = "/api/v1/backstage/pos/settings/"

    data = client.get(url).json()
    assert [p["terminal_ref"] for p in data["printers"]] == ["balcao"]
    assert data["kitchen_stations"][0]["auto_fire"] is False

    def post(body):
        response = client.post(url, data=json.dumps(body), content_type="application/json")
        return response

    assert post({"section": "printer", "terminal_ref": "balcao", "roll_width_mm": 58, "cut_mode": "none"}).status_code == 200
    terminal.refresh_from_db()
    assert terminal.metadata["hardware"]["printer"] == {"roll_width_mm": 58, "cut_mode": "none"}
    assert post({"section": "printer", "terminal_ref": "balcao", "roll_width_mm": 33, "cut_mode": "none"}).status_code == 400

    assert post({"section": "card_machine", "label": "Maquininha 2", "identification": "SN 2"}).status_code == 200
    device = DeliveryDevice.objects.get(identification="SN 2")
    assert post({"section": "card_machine", "ref": str(device.ref), "label": "Maquininha 2", "active": False}).status_code == 200
    device.refresh_from_db()
    assert device.active is False

    assert post({"section": "kitchen_station", "station_ref": "forno", "auto_fire": True}).status_code == 200
    assert KDSInstance.objects.get(ref="forno").config["auto_fire"] is True

    response = post({"section": "shortcuts", "terminal_ref": "balcao", "favorite_collection_refs": ["doces", "fantasma"]})
    assert response.status_code == 200
    terminal.refresh_from_db()
    assert terminal.metadata["favorite_collection_refs"] == ["doces"]

    assert post({"section": "outra"}).json()["field"] == "section"


def test_ajustes_pede_a_permissao_do_balcao(loja, client):
    client.force_login(get_user_model().objects.create_user("visita", password="x"))
    assert client.get("/api/v1/backstage/pos/settings/").status_code == 403


def _post_settings(client, body):
    return client.post("/api/v1/backstage/pos/settings/", data=json.dumps(body), content_type="application/json")


def test_a_caixa_nao_grava_maquininha_nem_impressora(loja, client):
    """Beta 05/11 (op:PDV-08, CEN-06): a Caixa cadastrava maquininha e trocava o rolo.

    Decisão do dono (05/11/2026): só o Gerente e o Dono. A Caixa lê, e segue
    gravando os atalhos e o envio à cozinha.
    """
    terminal = Terminal.objects.create(ref="balcao", label="Balcão", metadata={})
    client.force_login(_operador())

    data = client.get("/api/v1/backstage/pos/settings/").json()
    assert data["can_manage_setup"] is False
    assert data["terminal_is_this_device"] is False

    refused = _post_settings(client, {"section": "card_machine", "label": "Teste", "identification": "SN 9"})
    assert refused.status_code == 403
    assert refused.json()["detail"] == "Maquininha, impressora e Salão são ajustados pelo gerente."
    assert not DeliveryDevice.objects.exists()
    refused = _post_settings(client, {"section": "printer", "terminal_ref": "balcao", "roll_width_mm": 58,
                                      "cut_mode": "none"})
    assert refused.status_code == 403
    terminal.refresh_from_db()
    assert "hardware" not in terminal.metadata

    Collection.objects.create(ref="doces", name="Doces")
    shortcuts = _post_settings(client, {"section": "shortcuts", "terminal_ref": "balcao",
                                        "favorite_collection_refs": ["doces"]})
    assert shortcuts.status_code == 200


def test_maquininha_valida_tamanho_e_identificacao(loja, client):
    """Beta 05/11 (PDV-11, PDV-27): nome de 101 caracteres era 500; caixa diferente
    duplicava a identificação; apagar a identificação na edição não apagava nada."""
    client.force_login(_operador("operate_pos", "change_terminal"))

    long_name = _post_settings(client, {"section": "card_machine", "label": "M" * 101, "identification": "SN 1"})
    assert long_name.status_code == 400
    assert long_name.json()["field"] == "label"
    long_id = _post_settings(client, {"section": "card_machine", "label": "M", "identification": "S" * 101})
    assert long_id.json()["field"] == "identification"

    assert _post_settings(client, {"section": "card_machine", "label": "M1", "identification": "MG-SN-001"}).status_code == 200
    clash = _post_settings(client, {"section": "card_machine", "label": "M2", "identification": "mg-sn-001"})
    assert clash.status_code == 400
    assert clash.json()["field"] == "identification"

    device = DeliveryDevice.objects.get()
    emptied = _post_settings(client, {"section": "card_machine", "ref": str(device.ref), "label": "M1",
                                      "identification": "", "active": True})
    assert emptied.status_code == 400
    assert emptied.json()["field"] == "identification"
    toggled = _post_settings(client, {"section": "card_machine", "ref": str(device.ref), "label": "M1", "active": False})
    assert toggled.status_code == 200
    device.refresh_from_db()
    assert device.identification == "MG-SN-001"


# ── Planta: vitrine e caixa, entrada ─────────────────────────────────────


def test_salao_grava_a_vitrine_e_a_entrada(loja, client):
    SeatingSpot.objects.create(ref="mesa-1", label="Mesa 1", seats=2)
    client.force_login(_operador("operate_pos", "change_terminal"))
    url = "/api/v1/backstage/pos/seating/"
    revision = client.get(url).json()["revision"]
    response = client.post(url, data=json.dumps({
        "revision": revision, "spots": [], "removed": [],
        "fixtures": [
            {"kind": "showcase", "label": "Vitrine e caixa", "plan_x": 600, "plan_y": 40, "width": 40, "height": 320},
            {"kind": "entrance", "plan_x": 200, "plan_y": 420},
        ],
    }), content_type="application/json")
    assert response.status_code == 200, response.content
    kinds = {f["kind"]: f for f in response.json()["fixtures"]}
    assert kinds["showcase"]["plan_x"] == 600
    assert kinds["entrance"]["label"] == "Entrada"
    assert SeatingFixture.objects.count() == 2


# ── Fim do dia ───────────────────────────────────────────────────────────


def test_fim_do_dia_sem_historico_nao_inventa_grafico(loja):
    assert build_day_closing().hourly_shape is None
