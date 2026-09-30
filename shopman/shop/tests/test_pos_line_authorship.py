"""Autoria por linha da comanda: quem lançou e quem editou (D-008).

A tela do PDV mostrava "Lançado por / Editado por" lendo
``items[].meta.pos_authorship``, e ninguém escrevia o campo: em produção era
sempre vazio, e os testes de componente passavam porque alimentavam a fixture à
mão. Estes testes exercitam o SERVIÇO que salva a comanda.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import PosIntentError

pytestmark = pytest.mark.django_db


@pytest.fixture
def pdv():
    from shopman.offerman.models import Product

    from shopman.shop.models import Channel

    Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
    for sku, price in (("PAO", 500), ("CAFE", 700)):
        Product.objects.create(sku=sku, name=sku.title(), base_price_q=price, is_published=True, is_sellable=True)
    User = get_user_model()
    joyce = User.objects.create_user(username="joyce", first_name="Joyce", last_name="Lima", is_staff=True)
    marina = User.objects.create_user(username="marina", first_name="Marina", is_staff=True)
    tab = pos_service.open_pos_tab(channel_ref="pdv", tab_ref="7", actor="pos:joyce", operator_username="joyce")
    return {"session_key": tab.session_key, "joyce": joyce, "marina": marina}


def _save(pdv, username: str, items: list[dict]) -> None:
    pos_service.save_pos_tab(
        channel_ref="pdv",
        payload={"tab_session_key": pdv["session_key"], "items": items},
        actor=f"pos:{username}",
        operator_username=username,
    )


def _authorship(pdv) -> dict:
    from shopman.orderman.models import Session

    session = Session.objects.get(session_key=pdv["session_key"])
    return {item["line_id"]: (item.get("meta") or {}).get("pos_authorship") for item in session.items}


PAO = {"line_id": "L-pao00001", "sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 500}
CAFE = {"line_id": "L-cafe0001", "sku": "CAFE", "name": "Café", "qty": 1, "unit_price_q": 700}


def test_duas_linhas_por_operadores_diferentes_tem_autores_diferentes(pdv):
    _save(pdv, "joyce", [PAO])
    _save(pdv, "marina", [PAO, CAFE])

    autoria = _authorship(pdv)
    assert autoria["L-pao00001"]["created_by"] == str(pdv["joyce"].pk)
    assert autoria["L-pao00001"]["created_label"] == "Joyce Lima"
    assert autoria["L-cafe0001"]["created_by"] == str(pdv["marina"].pk)
    assert autoria["L-cafe0001"]["created_label"] == "Marina"
    # A linha da Joyce não mudou: salvar a comanda com o café não a "edita".
    assert "updated_by" not in autoria["L-pao00001"]


def test_editar_a_linha_preserva_quem_lancou_e_registra_quem_editou(pdv):
    _save(pdv, "joyce", [PAO])
    criado = _authorship(pdv)["L-pao00001"]

    _save(pdv, "marina", [{**PAO, "qty": 3}])

    autoria = _authorship(pdv)["L-pao00001"]
    assert {k: autoria[k] for k in ("created_by", "created_label", "created_at")} == criado
    assert autoria["updated_by"] == str(pdv["marina"].pk)
    assert autoria["updated_label"] == "Marina"
    assert autoria["updated_at"] >= criado["created_at"]


def test_o_nome_e_congelado_no_ato(pdv):
    _save(pdv, "joyce", [PAO])
    pdv["joyce"].first_name = "Joyce Renomeada"
    pdv["joyce"].save()

    _save(pdv, "marina", [PAO, CAFE])

    assert _authorship(pdv)["L-pao00001"]["created_label"] == "Joyce Lima"


def test_observacao_e_desconto_contam_como_edicao(pdv):
    _save(pdv, "joyce", [PAO])
    _save(pdv, "marina", [{**PAO, "notes": "sem casca"}])
    assert _authorship(pdv)["L-pao00001"]["updated_by"] == str(pdv["marina"].pk)

    _save(pdv, "joyce", [{**PAO, "notes": "sem casca", "discount": {"type": "percent", "value": 10}}])
    assert _authorship(pdv)["L-pao00001"]["updated_by"] == str(pdv["joyce"].pk)


def test_o_cliente_nao_escreve_autoria(pdv):
    forjada = {"created_by": "999", "created_label": "Outra Pessoa", "created_at": "2020-01-01T00:00:00"}
    _save(pdv, "joyce", [{**PAO, "pos_authorship": forjada, "authorship": forjada}])

    assert _authorship(pdv)["L-pao00001"]["created_by"] == str(pdv["joyce"].pk)


def test_sem_operador_identificado_o_save_e_recusado(pdv):
    with pytest.raises(PosIntentError) as exc:
        _save(pdv, "ninguem", [PAO])
    assert exc.value.code == "operator_unidentified"


def test_a_comanda_aberta_devolve_a_autoria_por_linha(pdv):
    from shopman.orderman.models import Session

    from shopman.backstage.projections.pos import build_open_tab

    _save(pdv, "joyce", [PAO])
    _save(pdv, "marina", [PAO, CAFE])

    tab = build_open_tab(Session.objects.get(session_key=pdv["session_key"]))
    autores = {item["line_id"]: item["authorship"]["created_label"] for item in tab["items"]}
    assert autores == {"L-pao00001": "Joyce Lima", "L-cafe0001": "Marina"}
