"""O caminho que abre a gaveta: config por terminal, health honesto, trilha.

O chute físico é do navegador — o agente vive na loopback do balcão e o servidor
nunca o alcança. O que se prova aqui é o lado que o servidor tem: que a config
chega inteira à superfície, que o health não inventa o que não sabe, e que
abertura sem venda deixa rastro.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from shopman.backstage.models import CashShift, POSTerminal
from shopman.backstage.services import pos as pos_service
from shopman.backstage.services.exceptions import POSError
from shopman.backstage.services.pos_hardware import CashDrawerConfig
from shopman.backstage.services.pos_terminal import runtime_profile

pytestmark = pytest.mark.django_db

AGENT_CONFIG = {
    "adapter": "agent",
    "agent_url": "http://127.0.0.1:47811",
    "token": "token-do-agente-com-tamanho",
}


def _terminal(drawer=None, ref="pdv-teste") -> POSTerminal:
    metadata = {"hardware": {"cash_drawer": drawer}} if drawer else {}
    return POSTerminal.objects.create(ref=ref, label="Balcão", metadata=metadata)


def _drawer(terminal):
    return next(c for c in runtime_profile(terminal).components if c.key == "cash_drawer")


# ── Config ────────────────────────────────────────────────────────────────


def test_terminal_sem_gaveta_declarada_nao_chuta():
    config = CashDrawerConfig.from_terminal(_terminal())
    assert config.declared is False
    assert config.kicks_by_software is False
    assert config.surface_payload()["can_kick"] is False


def test_gaveta_de_chave_nao_chuta_por_software():
    config = CashDrawerConfig.from_terminal(_terminal({"adapter": "manual"}))
    assert config.declared is True
    assert config.kicks_by_software is False


def test_adapter_desconhecido_cai_para_manual():
    """Um typo no adapter não pode virar 'chuta a gaveta de um jeito qualquer'."""
    config = CashDrawerConfig.from_dict({"adapter": "webusb"})
    assert config.adapter == "manual"
    assert config.kicks_by_software is False


def test_o_pulso_default_e_o_da_tm_t20():
    """50/500ms — os `25/250` do manual são UNIDADES de 2ms, não milissegundos."""
    config = CashDrawerConfig.from_dict(AGENT_CONFIG)
    assert config.pulse_on_ms == 50
    assert config.pulse_off_ms == 500
    assert config.surface_payload()["pulse"] == {"pin": 0, "on_ms": 50, "off_ms": 500}


def test_pulso_ilegivel_cai_no_default_em_vez_de_explodir():
    config = CashDrawerConfig.from_dict({**AGENT_CONFIG, "pulse_on_ms": "muito", "pulse_off_ms": 0})
    assert config.pulse_on_ms == 50
    assert config.pulse_off_ms == 500


def test_agente_sem_token_e_defeito_dito_com_todas_as_letras():
    config = CashDrawerConfig.from_dict({"adapter": "agent", "token": ""})
    assert "token" in config.misconfigured_reason
    assert config.surface_payload()["can_kick"] is False


def test_gaveta_desligada_nao_chuta():
    config = CashDrawerConfig.from_dict({**AGENT_CONFIG, "enabled": False})
    assert config.kicks_by_software is False


# ── Health ────────────────────────────────────────────────────────────────


def test_gaveta_com_agente_nao_finge_saber_o_que_so_a_estacao_sabe():
    """`ready` daqui seria mentira: o servidor não alcança a loopback do balcão."""
    health = _drawer(_terminal(AGENT_CONFIG))
    assert health.status == "deferred"
    assert health.message == "verificado na estação"


def test_gaveta_com_agente_incompleto_e_atencao_agora_nao_na_fila():
    health = _drawer(_terminal({"adapter": "agent"}))
    assert health.status == "warning"
    assert "token" in health.message


def test_gaveta_de_chave_e_configuracao_completa_nao_pendencia():
    health = _drawer(_terminal({"adapter": "manual"}))
    assert health.status == "ready"
    assert health.message == "abre com a chave"


def test_gaveta_nao_declarada_continua_ausente():
    assert _drawer(_terminal()).status == "absent"


def test_deferred_nao_acende_o_badge_geral_do_terminal():
    """Um periférico que só a estação sonda não é defeito do terminal."""
    assert runtime_profile(_terminal(AGENT_CONFIG)).status == "ready"


# ── Projection ────────────────────────────────────────────────────────────


def test_a_config_chega_inteira_na_superficie():
    """Quem chama o agente é o navegador — sem isto, ele não tem como."""
    from shopman.backstage.projections.pos import build_pos

    terminal = _terminal({**AGENT_CONFIG, "open_on_cash_sale": False})
    payload = build_pos(terminal=terminal).cash_drawer

    assert payload["can_kick"] is True
    assert payload["agent_url"] == "http://127.0.0.1:47811"
    assert payload["token"] == "token-do-agente-com-tamanho"
    assert payload["open_on_cash_sale"] is False


def test_terminal_sem_gaveta_nao_vaza_token_para_a_superficie():
    from shopman.backstage.projections.pos import build_pos

    payload = build_pos(terminal=_terminal({"adapter": "manual", "token": "segredo"})).cash_drawer
    assert "token" not in payload


# ── Abrir sem venda ───────────────────────────────────────────────────────


@pytest.fixture
def operator():
    user = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    CashShift.objects.create(terminal=POSTerminal.default(), operator=user, opening_amount_q=10000)
    return user


def _grant_pos_perm(user) -> None:
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(CashShift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename="operate_pos"))


def test_abrir_sem_venda_deixa_rastro_de_quem_quando_e_por_que(operator):
    """É o único dos quatro momentos que não tem venda nem movimento contando a história."""
    pos_service.register_drawer_opening(operator=operator, reason="Troco para cliente")

    shift = CashShift.get_open_for_operator(operator)
    openings = shift.metadata["drawer_openings"]
    assert len(openings) == 1
    assert openings[0]["by"] == "marina"
    assert openings[0]["reason"] == "Troco para cliente"
    assert openings[0]["at"]


def test_abrir_sem_motivo_e_recusado(operator):
    """Trilha com motivo em branco não é trilha, é ruído."""
    with pytest.raises(POSError, match="motivo"):
        pos_service.register_drawer_opening(operator=operator, reason="   ")


def test_abrir_sem_caixa_aberto_e_recusado():
    user = get_user_model().objects.create_user(username="sem-turno", password="x")
    with pytest.raises(POSError, match="Caixa não aberto"):
        pos_service.register_drawer_opening(operator=user, reason="curiosidade")


def test_aberturas_acumulam_sem_apagar_a_anterior(operator):
    pos_service.register_drawer_opening(operator=operator, reason="primeira")
    pos_service.register_drawer_opening(operator=operator, reason="segunda")

    openings = CashShift.get_open_for_operator(operator).metadata["drawer_openings"]
    assert [o["reason"] for o in openings] == ["primeira", "segunda"]


def test_a_trilha_tem_teto_para_um_clique_preso_nao_inchar_o_turno(operator):
    shift = CashShift.get_open_for_operator(operator)
    shift.metadata = {"drawer_openings": [{"at": "x", "by": "y", "reason": f"n{i}"} for i in range(500)]}
    shift.save(update_fields=["metadata"])

    pos_service.register_drawer_opening(operator=operator, reason="a mais recente")

    openings = CashShift.get_open_for_operator(operator).metadata["drawer_openings"]
    assert len(openings) == 500
    assert openings[-1]["reason"] == "a mais recente"


def test_abrir_sem_venda_nao_mexe_no_dinheiro_esperado(operator):
    """Abrir a gaveta não é movimento: o fechamento cego não pode sentir isso."""
    pos_service.register_drawer_opening(operator=operator, reason="conferência")

    shift = CashShift.get_open_for_operator(operator)
    assert shift.movements.count() == 0
    assert shift.opening_amount_q == 10000


# ── Endpoint ──────────────────────────────────────────────────────────────


def test_endpoint_exige_permissao_de_operar_pdv(client):
    user = get_user_model().objects.create_user(username="curioso", password="x")
    client.force_login(user)

    response = client.post(
        reverse("api-backstage-pos-cash-drawer-open"),
        data={"reason": "quero ver"},
        content_type="application/json",
    )
    assert response.status_code in (401, 403)


def test_endpoint_registra_e_devolve_ok(client, operator):
    _grant_pos_perm(operator)
    client.force_login(operator)


    response = client.post(
        reverse("api-backstage-pos-cash-drawer-open"),
        data={"reason": "Troco"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert CashShift.get_open_for_operator(operator).metadata["drawer_openings"][0]["reason"] == "Troco"
