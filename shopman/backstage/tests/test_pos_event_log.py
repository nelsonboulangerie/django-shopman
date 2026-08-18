"""O log de eventos do PDV: uma linha do tempo, append-only, para o caixa inteiro.

Antes havia cinco rastros parciais (aberturas e pedidos de troco no
``CashShift.metadata``, dinheiro no ``CashMovement``, falhas no
``OperatorAlert``, fechamento no ``DayClosing.data``) e nenhum respondia "o que
aconteceu no caixa hoje, em ordem". O que se prova aqui:

- todo momento do caixa vira evento com quem, quando e em qual turno;
- o dinheiro NÃO se duplica: o evento aponta para o ``CashMovement``;
- o log é imutável no app (guarda igual à do ``Move`` do stockman);
- a trava da gaveta só tem UMA porta, o destrave com PIN de gerente, e ele
  fica registrado.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import ProtectedError
from django.urls import reverse
from shopman.doorman.models import PinCredential

from shopman.backstage.models import CashMovement, CashShift, DayClosing, POSEvent, POSTerminal
from shopman.backstage.projections.pos import build_pos
from shopman.backstage.services import pos as pos_service
from shopman.backstage.services import pos_events
from shopman.backstage.services.closing import perform_day_closing
from shopman.backstage.services.exceptions import POSError
from shopman.shop.services.pos_intent import PosIntentError

pytestmark = pytest.mark.django_db

MANAGER_PIN = "4321"


def _grant(user, codename: str) -> None:
    ct = ContentType.objects.get_for_model(CashShift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))


@pytest.fixture
def operator():
    return get_user_model().objects.create_user(username="marina", password="x", is_staff=True)


@pytest.fixture
def manager():
    user = get_user_model().objects.create_user(username="pablo", password="x", is_staff=True)
    _grant(user, "adjust_cashshift")
    PinCredential.set_for(user, MANAGER_PIN)
    return user


def _approval(username: str = "pablo", pin: str = MANAGER_PIN) -> dict:
    return {"username": username, "pin": pin}


def _kinds(shift) -> list[str]:
    return list(pos_events.for_shift(shift).values_list("kind", flat=True))


# ── A linha do tempo de um turno ──────────────────────────────────────────


def test_o_turno_inteiro_fica_em_ordem_num_log_so(operator, manager):
    """Abrir, suprir, sangrar, abrir a gaveta, pedir troco, fechar: uma lista, em ordem."""
    shift = pos_service.open_cash_shift(operator=operator, opening_amount_raw="100,00")
    pos_service.register_cash_movement(operator=operator, movement_type="suprimento", amount_raw="20,00")
    pos_service.register_cash_movement(
        operator=operator, movement_type="sangria", amount_raw="50,00", manager_approval=_approval()
    )
    pos_service.register_drawer_opening(operator=operator, reason="Conferência")
    entry = pos_service.request_change(operator=operator, kind="coins")
    pos_service.cancel_change_request(operator=operator, request_ref=entry["ref"])
    pos_service.close_cash_shift(operator=operator, closing_amount_raw="70,00")

    assert _kinds(shift) == [
        POSEvent.Kind.SHIFT_OPENED,
        POSEvent.Kind.CASH_IN,
        POSEvent.Kind.CASH_OUT,
        POSEvent.Kind.DRAWER_OPENED,
        POSEvent.Kind.CHANGE_REQUESTED,
        POSEvent.Kind.CHANGE_CANCELLED,
        POSEvent.Kind.SHIFT_CLOSED,
    ]
    # Todo evento sabe quem, e o terminal veio do turno sem ninguém dizer.
    for event in pos_events.for_shift(shift):
        assert event.operator == operator
        assert event.terminal_id == shift.terminal_id


def test_a_abertura_do_turno_grava_o_fundo_de_troco(operator):
    shift = pos_service.open_cash_shift(operator=operator, opening_amount_raw="150,00")

    event = POSEvent.objects.get(shift=shift, kind=POSEvent.Kind.SHIFT_OPENED)
    assert event.payload == {"opening_amount_q": 15000}


def test_o_fechamento_grava_a_diferenca_e_quem_fechou(operator):
    shift = pos_service.open_cash_shift(operator=operator, opening_amount_raw="100,00")
    pos_service.close_cash_shift(operator=operator, closing_amount_raw="95,00")

    event = POSEvent.objects.get(shift=shift, kind=POSEvent.Kind.SHIFT_CLOSED)
    assert event.payload == {"difference_q": -500, "supervisory": False}
    assert event.operator == operator


def test_o_fechamento_supervisorio_diz_que_foi_o_gerente(operator, manager):
    """Quem fecha o caixa do outro assina o evento — o turno é da Marina, o
    fechamento é do Pablo, e a linha do tempo mostra os dois."""
    manager.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get_for_model(DayClosing), codename="perform_closing"
        )
    )
    shift = pos_service.open_cash_shift(operator=operator, opening_amount_raw="100,00")

    pos_service.close_blocking_shift(actor_user=manager, shift_id=shift.pk, closing_amount_raw="100,00")

    event = POSEvent.objects.get(shift=shift, kind=POSEvent.Kind.SHIFT_CLOSED)
    assert event.operator == manager
    assert event.payload["supervisory"] is True


# ── O dinheiro tem UMA tabela ─────────────────────────────────────────────


def test_o_movimento_gera_evento_que_aponta_para_o_dinheiro_sem_copiar_o_valor(operator, manager):
    """``CashMovement`` continua sendo a tabela do dinheiro. O evento liga a ela
    e NÃO carrega o valor: duas cópias do mesmo número é como duas cópias passam
    a discordar."""
    shift = pos_service.open_cash_shift(operator=operator, opening_amount_raw="100,00")
    movement = pos_service.register_cash_movement(
        operator=operator, movement_type="sangria", amount_raw="30,00", manager_approval=_approval()
    )

    event = POSEvent.objects.get(shift=shift, kind=POSEvent.Kind.CASH_OUT)
    assert event.movement == movement
    assert "amount_q" not in event.payload
    assert movement.events.count() == 1


def test_suprimento_e_entrada_sangria_e_saida(operator, manager):
    shift = pos_service.open_cash_shift(operator=operator, opening_amount_raw="100,00")
    pos_service.register_cash_movement(operator=operator, movement_type="suprimento", amount_raw="10,00")
    pos_service.register_cash_movement(
        operator=operator, movement_type="sangria", amount_raw="10,00", manager_approval=_approval()
    )

    by_kind = {e.kind: e.movement.movement_type for e in pos_events.for_shift(shift) if e.movement_id}
    assert by_kind == {
        POSEvent.Kind.CASH_IN: CashMovement.MovementType.SUPRIMENTO,
        POSEvent.Kind.CASH_OUT: CashMovement.MovementType.SANGRIA,
    }


def test_movimento_e_evento_nascem_juntos_ou_nenhum(operator, monkeypatch):
    """Se o evento falhar, o movimento não pode ficar sozinho — senão voltamos
    a ter dinheiro sem linha do tempo, que é o buraco de antes."""
    pos_service.open_cash_shift(operator=operator, opening_amount_raw="100,00")

    def explode(*args, **kwargs):
        raise RuntimeError("log fora do ar")

    monkeypatch.setattr(pos_events, "record", explode)
    with pytest.raises(RuntimeError):
        pos_service.register_cash_movement(operator=operator, movement_type="suprimento", amount_raw="10,00")

    assert CashMovement.objects.count() == 0


# ── Imutável (no app) ─────────────────────────────────────────────────────


def test_o_log_recusa_editar_e_apagar(operator):
    shift = pos_service.open_cash_shift(operator=operator)
    event = POSEvent.objects.get(shift=shift)

    with pytest.raises(ValueError, match="imutáveis"):
        event.payload = {"opening_amount_q": 999999}
        event.save()
    with pytest.raises(ValueError, match="imutáveis"):
        event.delete()
    with pytest.raises(ValueError, match="imutáveis"):
        POSEvent.objects.all().update(payload={})
    with pytest.raises(ValueError, match="imutáveis"):
        POSEvent.objects.all().delete()

    event.refresh_from_db()
    assert event.payload == {"opening_amount_q": 0}


def test_o_log_protege_o_turno_e_o_movimento_de_serem_apagados(operator, manager):
    """Apagar o turno apagaria a linha do tempo dele por tabela. O ledger diz não."""
    shift = pos_service.open_cash_shift(operator=operator)
    movement = pos_service.register_cash_movement(operator=operator, movement_type="suprimento", amount_raw="10,00")

    with pytest.raises(ProtectedError):
        movement.delete()
    with pytest.raises(ProtectedError):
        shift.delete()


# ── Dia fechado e reconciliação ───────────────────────────────────────────


def test_o_fechamento_do_dia_vira_marco_no_log(operator):
    """O snapshot fica no ``DayClosing``; o log ganha o marco para o dia
    aparecer em ordem com o resto do caixa. Sem turno: o dia não é de ninguém."""
    closing_date = perform_day_closing(user=operator, items=[], quantities_by_sku={})

    closing = DayClosing.objects.get(date=closing_date)
    event = POSEvent.objects.get(kind=POSEvent.Kind.DAY_CLOSED)
    assert event.operator == operator
    assert event.shift is None
    assert event.payload == {"date": closing_date.isoformat(), "day_closing_id": closing.pk}


def test_a_reconciliacao_com_divergencia_fica_no_log_alem_do_alerta(monkeypatch):
    """O alerta é o aviso (tem reconhecimento, some da tela); o evento é o
    registro. Sem ele a divergência sumiria da linha do tempo assim que alguém a
    marcasse como vista."""
    from datetime import date

    from django.utils import timezone

    from shopman.backstage.services import financial_reconciliation as fr

    report = fr.FinancialReconciliationReport(
        date=date(2026, 8, 18),
        generated_at=timezone.now(),
        order_count=1,
        intent_count=1,
        transaction_count=1,
        order_gross_q=1000,
        captured_q=900,
        refunded_q=0,
        chargeback_q=0,
        net_q=900,
        by_method={},
        by_gateway={},
        issues=(fr.FinancialReconciliationIssue(code="x", severity="error", message="m"),),
    )
    monkeypatch.setattr(
        "shopman.shop.services.observability.create_operator_alert", lambda **kw: None
    )

    fr.persist_financial_reconciliation(report)

    event = POSEvent.objects.get(kind=POSEvent.Kind.RECONCILIATION_FAILED)
    assert event.operator is None
    assert event.payload["date"] == "2026-08-18"
    assert event.payload["errors"] == 1
    assert event.payload["critical"] == 0


# ── A trava da gaveta: uma porta só, e ela fica registrada ────────────────


def test_o_destrave_exige_pin_de_gerente(operator):
    pos_service.open_cash_shift(operator=operator)

    with pytest.raises(PosIntentError) as exc:
        pos_service.unlock_drawer(operator=operator)
    assert exc.value.code == "manager_approval_required"
    assert not POSEvent.objects.filter(kind=POSEvent.Kind.DRAWER_UNLOCKED).exists()


def test_o_balconista_nao_destrava_a_propria_gaveta(operator):
    PinCredential.set_for(operator, "1111")
    pos_service.open_cash_shift(operator=operator)

    with pytest.raises(PosIntentError) as exc:
        pos_service.unlock_drawer(operator=operator, manager_approval=_approval("marina", "1111"))
    assert exc.value.code == "manager_approval_invalid"


def test_o_destrave_fica_no_log_com_quem_liberou_e_o_que_o_sensor_disse(operator, manager):
    shift = pos_service.open_cash_shift(operator=operator)

    event = pos_service.unlock_drawer(
        operator=operator, manager_approval=_approval(), drawer_raw="0x12"
    )

    assert event.kind == POSEvent.Kind.DRAWER_UNLOCKED
    assert event.shift == shift
    assert event.operator == operator
    assert event.payload == {"approved_by": "pablo", "drawer_raw": "0x12"}


def test_destravar_sem_caixa_aberto_e_recusado(operator, manager):
    with pytest.raises(POSError, match="Caixa não aberto"):
        pos_service.unlock_drawer(operator=operator, manager_approval=_approval())


def test_o_destrave_esta_no_contrato_de_acoes(operator):
    pos_service.open_cash_shift(operator=operator)
    refs = {a.ref for a in build_pos(operator=operator).actions}
    assert "drawer_unlock" in refs


def test_endpoint_de_destrave_exige_permissao_de_operar_pdv(client):
    user = get_user_model().objects.create_user(username="curioso", password="x")
    client.force_login(user)

    response = client.post(
        reverse("api-backstage-pos-cash-drawer-unlock"),
        data={"manager_approval": _approval()},
        content_type="application/json",
    )
    assert response.status_code in (401, 403)


def test_endpoint_de_destrave_sem_pin_devolve_o_codigo_do_desafio(client, operator):
    """A tela precisa do CÓDIGO para abrir o diálogo de PIN, não de um toast mudo."""
    _grant(operator, "operate_pos")
    pos_service.open_cash_shift(operator=operator)
    client.force_login(operator)

    response = client.post(
        reverse("api-backstage-pos-cash-drawer-unlock"), data={}, content_type="application/json"
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "manager_approval_required"


def test_endpoint_de_destrave_com_pin_registra_e_devolve_ok(client, operator, manager):
    _grant(operator, "operate_pos")
    shift = pos_service.open_cash_shift(operator=operator)
    client.force_login(operator)

    response = client.post(
        reverse("api-backstage-pos-cash-drawer-unlock"),
        data={"manager_approval": _approval(), "drawer_raw": "0x12"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    event = POSEvent.objects.get(shift=shift, kind=POSEvent.Kind.DRAWER_UNLOCKED)
    assert event.payload["approved_by"] == "pablo"


def test_cada_destrave_e_uma_linha_porque_cada_um_e_uma_venda(operator, manager):
    """Sem carência e sem liberação "até fechar": a exceção tratada como exceção
    é a que se escancara. Três liberações são três linhas — é a contagem que o
    gerente quer ver por operador e por horário."""
    shift = pos_service.open_cash_shift(operator=operator)
    for _ in range(3):
        pos_service.unlock_drawer(operator=operator, manager_approval=_approval())

    assert POSEvent.objects.filter(shift=shift, kind=POSEvent.Kind.DRAWER_UNLOCKED).count() == 3


# ── Nada sobrou no metadata ───────────────────────────────────────────────


def test_o_metadata_do_turno_nao_guarda_mais_trilha_nenhuma(operator, manager):
    """Se alguém reintroduzir uma listinha no JSONField, este teste grita: a
    trilha tem UM lugar."""
    shift = pos_service.open_cash_shift(operator=operator)
    pos_service.register_drawer_opening(operator=operator, reason="Conferência")
    entry = pos_service.request_change(operator=operator, kind="coins")
    pos_service.serve_change_request(operator=operator, request_ref=entry["ref"], manager_approval=_approval())

    shift.refresh_from_db()
    assert not (shift.metadata or {})


# ── A migração leva a trilha antiga junto ─────────────────────────────────


def test_a_migracao_carrega_as_listas_do_metadata_para_o_log(operator):
    """Turno que já existia com `drawer_openings`/`change_requests` no metadata:
    a migração 0022 vira cada entrada em evento e limpa as chaves. Sem isso a
    única trilha que o balcão tinha até aqui morreria na troca de casa."""
    import importlib

    from django.apps import apps

    migration = importlib.import_module("shopman.backstage.migrations.0022_posevent")
    shift = CashShift.objects.create(
        terminal=POSTerminal.default(),
        operator=operator,
        opening_amount_q=10000,
        metadata={
            "drawer_openings": [{"at": "2026-08-18T10:00:00-03:00", "by": "marina", "reason": "Troco"}],
            "change_requests": [
                {
                    "ref": "ab12", "kind": "coins", "amount_q": 0, "note": "", "status": "served",
                    "requested_by": "marina", "requested_at": "2026-08-18T11:00:00-03:00",
                    "served_by": "pablo", "served_at": "2026-08-18T11:05:00-03:00", "cancelled_at": "",
                },
                {
                    "ref": "cd34", "kind": "amount", "amount_q": 5000, "note": "notas de 10", "status": "pending",
                    "requested_by": "marina", "requested_at": "2026-08-18T12:00:00-03:00",
                    "served_by": "", "served_at": "", "cancelled_at": "",
                },
            ],
            "outra_chave": {"fica": True},
        },
    )

    migration.carry_metadata_trails_into_the_log(apps, None)

    shift.refresh_from_db()
    assert shift.metadata == {"outra_chave": {"fica": True}}
    assert _kinds(shift) == [
        POSEvent.Kind.DRAWER_OPENED,
        POSEvent.Kind.CHANGE_REQUESTED,
        POSEvent.Kind.CHANGE_SERVED,
        POSEvent.Kind.CHANGE_REQUESTED,
    ]
    opening = POSEvent.objects.get(shift=shift, kind=POSEvent.Kind.DRAWER_OPENED)
    assert opening.operator == operator
    assert opening.payload == {"reason": "Troco"}
    assert opening.at.isoformat().startswith("2026-08-18T13:00:00+00:00")
    # A dobra reconstrói o mesmo estado que a lista tinha: um atendido, um pendente.
    requests = {r["ref"]: r for r in pos_events.change_requests(shift)}
    assert requests["ab12"]["status"] == "served"
    assert requests["ab12"]["served_by"] == "pablo"
    assert requests["cd34"]["status"] == "pending"
    assert requests["cd34"]["amount_q"] == 5000
