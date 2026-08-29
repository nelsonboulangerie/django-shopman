"""A trava da gaveta tem UMA porta: o destrave com PIN de gerente, e ele fica no livro.

A trava é do PDV (é a página que lê o sensor pelo agente do balcão; o servidor
não alcança). O servidor só entra no destrave, para registrar quem liberou, para
quem, quando, e o que o sensor disse. Regras decididas e não reabertas: trava
ao INICIAR a venda; sem carência; só quando SABE; cada destrave vale UMA venda.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.cashman import services as cash
from shopman.cashman.models import Entry, Shift, Terminal
from shopman.doorman.models import PinCredential

from shopman.backstage.projections.pos import build_pos
from shopman.backstage.services import pos as pos_service
from shopman.backstage.services.exceptions import POSError
from shopman.shop.services.pos_intent import PosIntentError

pytestmark = pytest.mark.django_db

MANAGER_PIN = "4321"


def _grant(user, codename: str) -> None:
    ct = ContentType.objects.get_for_model(Shift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))


@pytest.fixture
def operator():
    user = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    cash.open_shift(operator=user, float_q=10000)
    return user


@pytest.fixture
def manager():
    user = get_user_model().objects.create_user(username="pablo", password="x", is_staff=True)
    _grant(user, "adjust_shift")
    PinCredential.set_for(user, MANAGER_PIN)
    return user


def _approval(username: str = "pablo", pin: str = MANAGER_PIN) -> dict:
    return {"username": username, "pin": pin}


def _unlocks(operator):
    return list(Entry.objects.filter(shift=cash.open_shift_for_terminal(Terminal.default()), kind=Entry.Kind.DRAWER_UNLOCK))


def test_o_destrave_exige_pin_de_gerente(operator):
    with pytest.raises(PosIntentError) as exc:
        pos_service.unlock_drawer(operator=operator)
    assert exc.value.code == "manager_approval_required"
    assert _unlocks(operator) == []


def test_o_balconista_nao_destrava_a_propria_gaveta(operator):
    PinCredential.set_for(operator, "1111")
    with pytest.raises(PosIntentError) as exc:
        pos_service.unlock_drawer(operator=operator, manager_approval=_approval("marina", "1111"))
    assert exc.value.code == "manager_approval_invalid"


def test_o_destrave_fica_no_livro_com_quem_liberou_e_o_que_o_sensor_disse(operator, manager):
    entry = pos_service.unlock_drawer(operator=operator, manager_approval=_approval(), drawer_raw="0x12")

    assert entry.kind == Entry.Kind.DRAWER_UNLOCK
    assert entry.amount_q == 0  # efeito zero: a gaveta não mudou de saldo
    assert entry.operator == operator
    assert entry.approved_by == manager
    assert entry.payload == {"drawer_raw": "0x12", "outcome": "manager_override"}
    assert cash.balance(entry.shift) == 10000


def test_destravar_sem_caixa_aberto_e_recusado(manager):
    user = get_user_model().objects.create_user(username="sem-turno", password="x")
    with pytest.raises(POSError, match="Caixa não aberto"):
        pos_service.unlock_drawer(operator=user, manager_approval=_approval())


def test_cada_destrave_e_uma_linha_porque_cada_um_e_uma_venda(operator, manager):
    """Sem carência e sem liberação "até fechar": três liberações são três
    linhas. É a contagem por operador e por horário que o B.I. lê."""
    for _ in range(3):
        pos_service.unlock_drawer(operator=operator, manager_approval=_approval())
    assert len(_unlocks(operator)) == 3


def test_o_destrave_esta_no_contrato_de_acoes(operator):
    refs = {a.ref for a in build_pos(operator=operator).actions}
    assert "drawer_unlock" in refs


def test_endpoint_exige_permissao_de_operar_pdv(client):
    user = get_user_model().objects.create_user(username="curioso", password="x")
    client.force_login(user)
    response = client.post(
        reverse("api-backstage-pos-cash-drawer-unlock"),
        data={"manager_approval": _approval()},
        content_type="application/json",
    )
    assert response.status_code in (401, 403)


def test_endpoint_sem_pin_devolve_o_codigo_do_desafio(client, operator):
    """A tela precisa do CÓDIGO para abrir o diálogo de PIN, não de um toast mudo."""
    _grant(operator, "operate_pos")
    client.force_login(operator)
    response = client.post(reverse("api-backstage-pos-cash-drawer-unlock"), data={}, content_type="application/json")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "manager_approval_required"


def test_endpoint_com_pin_registra_e_devolve_ok(client, operator, manager):
    _grant(operator, "operate_pos")
    client.force_login(operator)
    response = client.post(
        reverse("api-backstage-pos-cash-drawer-unlock"),
        data={"manager_approval": _approval(), "drawer_raw": "0x12"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    (entry,) = _unlocks(operator)
    assert entry.approved_by == manager
    assert entry.payload["drawer_raw"] == "0x12"


# ── A trava que CAI não pode cair calada ──────────────────────────────────
#
# A trava falha aberta de propósito: sensor ruim degrada para "sem controle",
# nunca para "balcão parado com fila". Certo — e era a fuga mais barata contra
# ela. Deixar a gaveta aberta é trabalhoso e visível; puxar o cabo da gaveta é
# um gesto, uma vez, e desliga a proteção para sempre. Era silencioso.


def _alerts():
    from shopman.backstage.models import OperatorAlert

    return list(OperatorAlert.objects.filter(type="pos_drawer_sensor_blind"))


def _notes():
    return list(
        Entry.objects.filter(
            shift=cash.open_shift_for_terminal(Terminal.default()), kind=Entry.Kind.NOTE
        )
    )


def test_o_sensor_cego_vira_alerta_do_gerente_E_linha_no_livro(operator):
    """Duas saídas porque são duas perguntas.

    O alerta responde "isso está acontecendo agora" e some quando o gerente
    reconhece. O livro responde "quando o caixa ficou cego" na conferência do
    turno, e sobrevive ao reconhecimento.
    """
    pos_service.report_drawer_blind(operator=operator, reason="impressora não respondeu")

    (alerta,) = _alerts()
    assert alerta.severity == "warning"
    assert "marina" in alerta.message
    assert "impressora não respondeu" in alerta.message
    assert alerta.acknowledged is False

    (nota,) = _notes()
    assert nota.payload["event"] == "drawer_sensor_blind"
    assert nota.payload["detail"] == "impressora não respondeu"
    assert nota.amount_q == 0, "aviso não mexe em dinheiro"


def test_o_aviso_diz_que_as_vendas_SEGUEM(operator):
    """Alerta que parece parar o balcão faz o gerente correr até o caixa à toa."""
    pos_service.report_drawer_blind(operator=operator, reason="cabo")

    assert "seguem" in _alerts()[0].message.lower()


def test_o_aviso_aponta_O_CABO_porque_e_o_conserto(operator):
    pos_service.report_drawer_blind(operator=operator, reason="cabo")

    assert "cabo" in _alerts()[0].message.lower()


def test_sem_detalhe_o_aviso_ainda_sai(operator):
    """Sensor que morre sem explicar não pode virar aviso que não sai."""
    pos_service.report_drawer_blind(operator=operator)

    assert len(_alerts()) == 1


def test_endpoint_do_aviso_exige_permissao_de_operar_pdv(client, operator):
    client.force_login(operator)
    response = client.post(
        reverse("api-backstage-pos-cash-drawer-blind"),
        data={"reason": "cabo"},
        content_type="application/json",
    )
    assert response.status_code == 403
    assert _alerts() == []


def test_endpoint_registra_e_devolve_ok(client, operator):
    _grant(operator, "operate_pos")
    client.force_login(operator)
    response = client.post(
        reverse("api-backstage-pos-cash-drawer-blind"),
        data={"reason": "impressora não respondeu"},
        content_type="application/json",
    )
    assert response.status_code == 200 and response.json()["ok"] is True
    assert len(_alerts()) == 1


def test_o_aviso_esta_no_contrato_de_acoes(operator):
    """Se a ação não é projetada, o PDV cai no href cravado e ninguém percebe."""
    refs = {a.ref for a in build_pos(operator=operator).actions}
    assert "drawer_blind" in refs


# ── A trava virou DURA: quem libera é o mundo físico ──────────────────────
#
# Decisão do dono (29/08). Antes o PIN liberava UMA venda com a gaveta ainda
# aberta — pedágio caro, mas o comportamento continuava possível. Agora o
# bloqueio cai quando o sensor diz que fechou, e o PIN é a EXCEÇÃO. Duas
# consequências que estes testes travam: a duração da gaveta aberta passou a
# ser mensurável (o PIN mascarava esse número), e a emergência precisa ser
# distinguível do fechamento normal, senão a anomalia some na média.


def _blocks():
    return [
        e for e in _notes()
        if (e.payload or {}).get("event") == "drawer_blocked"
    ]


def test_o_fechamento_normal_grava_duracao_e_desfecho(operator):
    pos_service.record_drawer_block(operator=operator, duration_ms=8200, outcome="closed", drawer_raw="0x12")

    (bloco,) = _blocks()
    assert bloco.payload["outcome"] == "closed"
    assert bloco.payload["duration_ms"] == 8200
    assert bloco.payload["drawer_raw"] == "0x12"
    assert bloco.amount_q == 0, "medir tempo não mexe em dinheiro"


def test_a_emergencia_e_distinguivel_do_fechamento_normal(operator, manager):
    """Um gerente que libera 20× por dia tem que aparecer como anomalia."""
    entry = pos_service.unlock_drawer(
        operator=operator, manager_approval=_approval(), drawer_raw="0x12", duration_ms=45000,
    )

    assert entry.kind == Entry.Kind.DRAWER_UNLOCK
    assert entry.payload["outcome"] == "manager_override"
    assert entry.payload["duration_ms"] == 45000


def test_a_emergencia_por_sensor_morto_se_declara_como_tal(operator, manager):
    entry = pos_service.unlock_drawer(
        operator=operator, manager_approval=_approval(), outcome="sensor_lost", duration_ms=3000,
    )

    assert entry.payload["outcome"] == "sensor_lost"


def test_desfecho_desconhecido_nao_entra_no_livro_como_verdade(operator, manager):
    """Payload vem da tela: valor fora do vocabulário cai no default, não passa."""
    entry = pos_service.unlock_drawer(
        operator=operator, manager_approval=_approval(), outcome="tudo certo pode passar",
    )

    assert entry.payload["outcome"] == "manager_override"


@pytest.mark.parametrize("bruto", ["", None, "abc", -5])
def test_duracao_invalida_vira_zero_em_vez_de_explodir(operator, bruto):
    """O número nasce no relógio do navegador do balcão: nunca é confiável."""
    pos_service.record_drawer_block(operator=operator, duration_ms=bruto)

    assert _blocks()[0].payload["duration_ms"] == 0


def test_duracao_absurda_tem_teto(operator):
    """Kiosk com a hora errada não pode envenenar a média do B.I."""
    pos_service.record_drawer_block(operator=operator, duration_ms=99 * 24 * 60 * 60 * 1000)

    assert _blocks()[0].payload["duration_ms"] == 24 * 60 * 60 * 1000


def test_endpoint_do_bloqueio_registra(client, operator):
    _grant(operator, "operate_pos")
    client.force_login(operator)
    response = client.post(
        reverse("api-backstage-pos-cash-drawer-block"),
        data={"duration_ms": 1500, "outcome": "closed"},
        content_type="application/json",
    )

    assert response.status_code == 200 and response.json()["ok"] is True
    assert _blocks()[0].payload["duration_ms"] == 1500


# ── A hora morta: gaveta aberta sem ninguém vender ────────────────────────


def _left_open_alerts():
    from shopman.backstage.models import OperatorAlert

    return list(OperatorAlert.objects.filter(type="pos_drawer_left_open"))


def test_gaveta_esquecida_aberta_vira_alerta_e_linha(operator):
    """A trava só age quando alguém tenta vender; isto cobre o balcão parado."""
    pos_service.report_drawer_left_open(operator=operator, minutes=7)

    (alerta,) = _left_open_alerts()
    assert "7 min" in alerta.message
    assert "marina" in alerta.message

    nota = next(e for e in _notes() if (e.payload or {}).get("event") == "drawer_left_open")
    assert nota.payload["minutes"] == 7


def test_endpoint_da_gaveta_esquecida_exige_operar_pdv(client, operator):
    client.force_login(operator)
    response = client.post(
        reverse("api-backstage-pos-cash-drawer-left-open"),
        data={"minutes": 5},
        content_type="application/json",
    )

    assert response.status_code == 403
    assert _left_open_alerts() == []


def test_as_acoes_novas_estao_no_contrato(operator):
    refs = {a.ref for a in build_pos(operator=operator).actions}

    assert {"drawer_block", "drawer_left_open", "drawer_blind"} <= refs


# ── O limiar é do dono, e config errada não desliga a proteção ───────────
#
# Mora em `Shop.defaults["pos"]`, ao lado do `fiscal_toggle` — política de PDV
# do estabelecimento, editável no Admin sem deploy.


def _set_limiar(valor):
    from django.core.cache import cache

    from shopman.shop.models import Shop

    shop = Shop.objects.first() or Shop.objects.create(name="Nelson", brand_name="Nelson")
    defaults = dict(shop.defaults or {})
    defaults["pos"] = {**(defaults.get("pos") or {}), "drawer_idle_alert_minutes": valor}
    shop.defaults = defaults
    shop.save()
    cache.clear()  # `Shop.load()` é cacheado; sem isto o teste leria o de antes.


def test_o_limiar_tem_default_defensavel(db):
    from shopman.backstage.services.pos_hardware import (
        DEFAULT_IDLE_OPEN_ALERT_MINUTES,
        idle_open_alert_minutes,
    )

    assert idle_open_alert_minutes() == DEFAULT_IDLE_OPEN_ALERT_MINUTES == 3


def test_o_dono_muda_o_limiar_pelo_admin(db):
    from shopman.backstage.services.pos_hardware import idle_open_alert_minutes

    _set_limiar(10)

    assert idle_open_alert_minutes() == 10


@pytest.mark.parametrize("ruim", ["dez", -3, [], {}, True, 1.5])
def test_limiar_invalido_cai_no_default_em_vez_de_desligar_calado(db, ruim):
    """Desligar proteção por erro de digitação é o modo de falha inaceitável.

    Para desligar de propósito existe o `0`, que é explícito.
    """
    from shopman.backstage.services.pos_hardware import idle_open_alert_minutes

    _set_limiar(ruim)

    assert idle_open_alert_minutes() == 3


def test_zero_desliga_o_aviso_porque_e_explicito(db):
    from shopman.backstage.services.pos_hardware import idle_open_alert_minutes

    _set_limiar(0)

    assert idle_open_alert_minutes() == 0


def test_o_limiar_viaja_na_projecao_para_a_tela_poder_contar(db, operator):
    """Quem conta o tempo é a página (o sensor vive na loopback do balcão)."""
    _set_limiar(7)

    assert build_pos(operator=operator).cash_drawer.get("idle_open_alert_minutes") == 7
