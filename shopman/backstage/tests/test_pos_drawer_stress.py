"""Bateria de estresse da gaveta: *se não pudermos evitar a fraude, pelo menos
temos que reconhecê-la*.

Essa frase do dono é a especificação desta suíte, e ela muda o alvo: não basta
provar que a trava bloqueia. O que se prova aqui é que **toda tentativa deixa
rastro íntegro no livro** — inclusive as tentativas que a trava não consegue
impedir.

⚠️ **O que é indefensável, e por que ainda assim há defesa.**

O agente do balcão roda NA máquina do caixa. Quem tem a máquina tem o canal:
dá para derrubar o agente, puxar o cabo da gaveta da impressora, ou — com
trabalho — pôr na loopback um programa que responda ``open: false`` para sempre.
Nenhuma trava do PDV alcança isso, e prometer o contrário seria mentira: o
navegador não tem como distinguir o agente verdadeiro de um impostor na mesma
porta, porque o token que autentica o agente é entregue AO navegador.

O que é garantível é o **reconhecimento depois**. Cada uma dessas manobras deixa
uma assinatura no livro, e a assinatura costuma ser a AUSÊNCIA do que deveria
estar lá — por isso o B.I. lê silêncio como sinal (`_DrawerForensics`).

O adversário aqui é o funcionário interno: tem tempo, tem acesso físico, tem
motivo, e não precisa de nenhuma ferramenta além das mãos.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.cashman import services as cash
from shopman.cashman.exceptions import CashError
from shopman.cashman.models import Entry, Shift, Terminal
from shopman.doorman.models import PinCredential

from shopman.backstage.projections.bi_cash import build_bi_cash
from shopman.backstage.services import pos as pos_service
from shopman.backstage.services.exceptions import POSError
from shopman.shop.services.pos_intent import PosIntentError

pytestmark = pytest.mark.django_db

MANAGER_PIN = "4321"


def _grant(user, codename: str) -> None:
    ct = ContentType.objects.get_for_model(Shift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))


@pytest.fixture
def caixa():
    user = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    _grant(user, "operate_pos")
    cash.open_shift(operator=user, float_q=10000)
    return user


@pytest.fixture
def gerente():
    user = get_user_model().objects.create_user(username="pablo", password="x", is_staff=True)
    _grant(user, "adjust_shift")
    PinCredential.set_for(user, MANAGER_PIN)
    return user


def _shift():
    return cash.open_shift_for_terminal(Terminal.default())


def _notes(event: str) -> list[Entry]:
    return [
        e for e in Entry.objects.filter(shift=_shift(), kind=Entry.Kind.NOTE).order_by("at", "id")
        if (e.payload or {}).get("event") == event
    ]


def _hoje():
    return timezone.localdate()


def _relatorio():
    return build_bi_cash(date_from=_hoje(), date_to=_hoje())


# ── Ataque ao sensor ──────────────────────────────────────────────────────


def test_cabo_puxado_com_a_trava_ativa_deixa_rastro(caixa):
    """O gesto mais barato contra a trava: puxar o cabo e seguir vendendo.

    A trava CAI (falhar aberto é a regra — fila de cliente não para por sensor
    ruim), mas cai gritando: alerta ao gerente e linha no livro.
    """
    pos_service.report_drawer_blind(operator=caixa, reason="impressora não respondeu")
    pos_service.record_drawer_block(operator=caixa, duration_ms=4000, outcome="sensor_lost")

    assert len(_notes("drawer_sensor_blind")) == 1
    assert _notes("drawer_blocked")[0].payload["outcome"] == "sensor_lost"

    linha = _relatorio().drawer_by_operator[0]
    assert linha.sensor_blind == 1
    assert [a.code for a in _relatorio().drawer_anomalies] == ["sensor_went_blind"]


def test_sensor_que_some_e_volta_toda_tarde_vira_anomalia(caixa):
    """Cabo solto acontece uma vez. Toda tarde é outra coisa."""
    for _ in range(3):
        pos_service.report_drawer_blind(operator=caixa, reason="sem resposta")

    (anomalia,) = [a for a in _relatorio().drawer_anomalies if a.code == "sensor_went_blind"]
    assert "3×" in anomalia.detail


def test_agente_forjado_respondendo_SEMPRE_fechada_e_denunciado_pelo_SILENCIO(caixa):
    """⚠️ O ataque que a trava NÃO consegue impedir — e como ele aparece.

    Um programa na loopback que responda `open: false` sempre desliga a trava
    por completo: o PDV nunca vê a gaveta aberta, nunca bloqueia, nunca grava um
    episódio. Não há defesa possível no navegador — quem controla a máquina
    controla a resposta.

    O que sobra, e é o que este teste trava: o turno fica com dinheiro andando e
    ZERO bloqueio. Numa loja onde a gaveta abre a cada venda em dinheiro, isso é
    impossível por hábito. O B.I. lê essa ausência e aponta o turno.
    """
    for _ in range(5):
        pos_service.register_drawer_opening(operator=caixa, reason="troco")
    # Nenhum `drawer_blocked` — é exatamente o que o agente forjado produz.

    assert _notes("drawer_blocked") == []
    (anomalia,) = [a for a in _relatorio().drawer_anomalies if a.code == "drawer_never_blocked"]
    assert anomalia.operator == "marina"
    assert "NENHUM bloqueio" in anomalia.detail


def test_balcao_calmo_e_honesto_NAO_vira_anomalia(caixa):
    """A régua tem que poupar o balcão de verdade, senão vira alarme ignorado."""
    for _ in range(2):
        pos_service.register_drawer_opening(operator=caixa, reason="troco")

    assert [a for a in _relatorio().drawer_anomalies if a.code == "drawer_never_blocked"] == []


def test_quem_fecha_a_gaveta_direito_nao_e_acusado_de_nada(caixa):
    """Muitos movimentos COM bloqueios registrados é o padrão saudável."""
    for _ in range(6):
        pos_service.register_drawer_opening(operator=caixa, reason="troco")
        pos_service.record_drawer_block(operator=caixa, duration_ms=3000, outcome="closed")

    assert _relatorio().drawer_anomalies == ()


# ── Relógio adulterado ────────────────────────────────────────────────────


@pytest.mark.parametrize("mentira", [10**12, -5000, "muito tempo", None, [], 2**63])
def test_relogio_adulterado_nao_envenena_o_BI(caixa, mentira):
    """A duração nasce no relógio do NAVEGADOR do balcão: nunca é confiável.

    Um kiosk com a hora errada — ou um operador que sabe disso — poderia lançar
    uma duração absurda e destruir qualquer média. O teto de 24h e o piso de
    zero fazem o número ser inútil como arma sem precisar confiar na estação.
    """
    pos_service.record_drawer_block(operator=caixa, duration_ms=mentira, outcome="closed")

    duracao = _notes("drawer_blocked")[0].payload["duration_ms"]
    assert 0 <= duracao <= 24 * 60 * 60 * 1000


def test_duracao_no_teto_ainda_conta_como_episodio(caixa):
    """Truncar o número não pode apagar o fato de que houve um bloqueio."""
    pos_service.record_drawer_block(operator=caixa, duration_ms=10**12, outcome="closed")

    assert _relatorio().drawer_by_operator[0].blocks == 1


# ── Abuso do PIN de emergência ────────────────────────────────────────────


def test_rajada_de_tentativas_de_PIN_vira_anomalia(caixa):
    """A saída é escondida (Esc). Procurá-la em rajada é procurar alguma coisa."""
    for _ in range(4):
        pos_service.record_unlock_attempt(operator=caixa, outcome="opened")

    (anomalia,) = [a for a in _relatorio().drawer_anomalies if a.code == "hunting_for_the_exit"]
    assert "4×" in anomalia.detail


def test_a_DESISTENCIA_tambem_conta_porque_e_ela_que_revela_a_procura(caixa):
    """Registrar só o destrave bem-sucedido apagaria quem tenta e desiste."""
    pos_service.record_unlock_attempt(operator=caixa, outcome="opened")
    pos_service.record_unlock_attempt(operator=caixa, outcome="abandoned")
    pos_service.record_unlock_attempt(operator=caixa, outcome="denied")

    assert [n.payload["outcome"] for n in _notes("drawer_unlock_attempt")] == [
        "opened", "abandoned", "denied",
    ]
    assert _relatorio().drawer_by_operator[0].unlock_attempts == 3


def test_gerente_destravando_repetidamente_vira_anomalia(caixa, gerente):
    for _ in range(3):
        pos_service.unlock_drawer(
            operator=caixa, manager_approval={"username": "pablo", "pin": MANAGER_PIN},
        )

    (anomalia,) = [a for a in _relatorio().drawer_anomalies if a.code == "too_many_overrides"]
    assert "3 destraves" in anomalia.detail


def test_PIN_errado_em_rajada_nao_destrava_nem_UMA_vez(caixa, gerente):
    for _ in range(8):
        with pytest.raises(PosIntentError):
            pos_service.unlock_drawer(
                operator=caixa, manager_approval={"username": "pablo", "pin": "0000"},
            )

    assert Entry.objects.filter(kind=Entry.Kind.DRAWER_UNLOCK).count() == 0


def test_auto_aprovacao_e_recusada_mesmo_com_o_gerente_operando(caixa):
    """O caso real: quem opera o balcão TAMBÉM é gerente (a Joyce do seed)."""
    caixa.user_permissions.clear()
    _grant(caixa, "operate_pos")
    _grant(caixa, "adjust_shift")
    PinCredential.set_for(caixa, "1111")
    caixa = get_user_model().objects.get(pk=caixa.pk)  # limpa o cache de permissões

    with pytest.raises(PosIntentError) as exc:
        pos_service.unlock_drawer(
            operator=caixa, manager_approval={"username": "marina", "pin": "1111"},
        )

    assert exc.value.code == "manager_approval_invalid"
    assert Entry.objects.filter(kind=Entry.Kind.DRAWER_UNLOCK).count() == 0


def test_auto_aprovacao_pelo_CRACHA_tambem_e_recusada(caixa):
    """A porta nova não pode reabrir a fraude que a porta velha fechou."""
    caixa.user_permissions.clear()
    _grant(caixa, "operate_pos")
    _grant(caixa, "adjust_shift")
    caixa = get_user_model().objects.get(pk=caixa.pk)

    with pytest.raises(PosIntentError):
        pos_service.unlock_drawer(operator=caixa, manager_approval={"badge": "marina"})

    assert Entry.objects.filter(kind=Entry.Kind.DRAWER_UNLOCK).count() == 0


def test_PIN_correto_com_a_gaveta_AINDA_aberta_libera_e_registra(caixa, gerente):
    """É o caso legítimo: gaveta emperrada. Libera, mas fica marcado como exceção."""
    entry = pos_service.unlock_drawer(
        operator=caixa,
        manager_approval={"username": "pablo", "pin": MANAGER_PIN},
        drawer_raw="0x12",
        duration_ms=90000,
    )

    assert entry.approved_by == gerente
    assert entry.payload["outcome"] == "manager_override"
    assert entry.payload["duration_ms"] == 90000
    assert entry.payload["drawer_raw"] == "0x12"


# ── Integridade do rastro ─────────────────────────────────────────────────


def test_o_livro_recusa_edicao_do_rastro(caixa):
    """Rastro que se edita não é rastro. O livro é append-only por construção."""
    pos_service.record_drawer_block(operator=caixa, duration_ms=5000, outcome="closed")
    linha = _notes("drawer_blocked")[0]

    # O livro recusa pelos TRÊS caminhos, e cada um tem que ser recusado: editar
    # a instância, atualizar em massa (que não passa por `save()`), e apagar.
    linha.payload = {"event": "drawer_blocked", "outcome": "closed", "duration_ms": 1}
    with pytest.raises(ValueError, match="imutáve"):
        linha.save()

    with pytest.raises(ValueError, match="imutáve"):
        Entry.objects.filter(pk=linha.pk).update(amount_q=999)

    with pytest.raises(ValueError, match="imutáve"):
        linha.delete()

    assert Entry.objects.get(pk=linha.pk).payload["duration_ms"] == 5000


def test_nenhum_evento_da_gaveta_mexe_em_dinheiro(caixa, gerente):
    """Rastro que altera saldo seria uma arma; estes são todos de efeito zero."""
    antes = cash.balance(_shift())
    pos_service.record_drawer_block(operator=caixa, duration_ms=1000, outcome="closed")
    pos_service.record_unlock_attempt(operator=caixa, outcome="opened")
    pos_service.report_drawer_blind(operator=caixa, reason="cabo")
    pos_service.report_drawer_left_open(operator=caixa, minutes=9)
    pos_service.unlock_drawer(operator=caixa, manager_approval={"username": "pablo", "pin": MANAGER_PIN})

    assert cash.balance(_shift()) == antes


def test_turno_fechado_nao_aceita_rastro_retroativo(caixa):
    """Fechada a contagem, ninguém 'lembra' de um bloqueio que faltava."""
    cash.close_shift(_shift(), counted_q=10000, actor=caixa)

    with pytest.raises((CashError, POSError)):
        pos_service.record_drawer_block(operator=caixa, duration_ms=1000, outcome="closed")


def test_todo_desfecho_gravado_pertence_ao_vocabulario(caixa):
    """Payload vem da tela: string livre no livro viraria dado inútil no B.I."""
    pos_service.record_drawer_block(operator=caixa, duration_ms=1, outcome="tudo certo, pode passar")

    assert _notes("drawer_blocked")[0].payload["outcome"] == "closed"


# ── O rastro chega ao B.I. inteiro ────────────────────────────────────────


def test_o_pior_episodio_nao_se_perde_na_media(caixa):
    """Três bloqueios curtos e um longo: a média esconde, o máximo não."""
    for ms in (2000, 3000, 2500, 600000):
        pos_service.record_drawer_block(operator=caixa, duration_ms=ms, outcome="closed")

    linha = _relatorio().drawer_by_operator[0]
    assert linha.blocks == 4
    assert linha.longest_open_seconds == 600
    assert linha.open_seconds == (2000 + 3000 + 2500 + 600000) // 1000


def test_a_hora_do_dia_mostra_quando_a_gaveta_fica_aberta(caixa):
    pos_service.record_drawer_block(operator=caixa, duration_ms=30000, outcome="closed")

    hora = timezone.localtime().hour
    (linha,) = [h for h in _relatorio().drawer_by_hour if h.hour == hora]
    assert linha.blocks == 1
    assert linha.open_seconds == 30


# ── A anomalia aponta a PESSOA, não o turno ───────────────────────────────


def test_a_anomalia_acusa_quem_fez_nao_quem_abriu_o_caixa(caixa, gerente):
    """Várias mãos trabalham na mesma gaveta.

    Achado na tela: a anomalia saía no nome de quem abriu o turno, não de quem
    caçou a saída. Acusar a pessoa errada é pior que não acusar ninguém — queima
    a confiança no sinal inteiro, e o gerente para de olhar.
    """
    outro = get_user_model().objects.create_user(username="bruno", password="x", is_staff=True)
    _grant(outro, "operate_pos")

    # A marina só trabalha; o bruno é quem procura a saída.
    pos_service.record_drawer_block(operator=caixa, duration_ms=3000, outcome="closed")
    for _ in range(4):
        pos_service.record_unlock_attempt(operator=outro, outcome="opened")

    caçadores = [a for a in _relatorio().drawer_anomalies if a.code == "hunting_for_the_exit"]
    assert [a.operator for a in caçadores] == ["bruno"]


def test_o_silencio_suspeito_tambem_e_por_pessoa(caixa):
    """Quem mexeu em dinheiro sem nunca travar é a pessoa apontada."""
    outro = get_user_model().objects.create_user(username="bruno", password="x", is_staff=True)
    _grant(outro, "operate_pos")

    for _ in range(6):
        pos_service.register_drawer_opening(operator=outro, reason="troco")
    # A marina trabalha direito, no mesmo turno.
    pos_service.register_drawer_opening(operator=caixa, reason="troco")
    pos_service.record_drawer_block(operator=caixa, duration_ms=2000, outcome="closed")

    silencios = [a for a in _relatorio().drawer_anomalies if a.code == "drawer_never_blocked"]
    assert [a.operator for a in silencios] == ["bruno"]


# ── Desistir é desfecho, e desistir demais é sinal ────────────────────────
#
# ⚠️ Buraco achado OLHANDO A TELA, não pelos testes: o X do canto do diálogo
# encerrava o bloqueio sem gerar linha. A trava segurava (a próxima tentativa
# trava de novo), mas o episódio evaporava — dava para esbarrar na trava e
# desistir a manhã inteira sem deixar rastro.


def _blocks() -> list[Entry]:
    return _notes("drawer_blocked")


def test_desistencia_e_um_desfecho_aceito_pelo_servidor(caixa):
    """Se o servidor recusasse `dismissed`, a tela reportaria e o livro mentiria."""
    pos_service.record_drawer_block(operator=caixa, duration_ms=4200, outcome="dismissed", drawer_raw="0x12")

    (bloco,) = _blocks()
    assert bloco.payload["outcome"] == "dismissed"
    assert bloco.payload["duration_ms"] == 4200


def test_endpoint_aceita_a_desistencia(client, caixa):
    _grant(caixa, "operate_pos")
    client.force_login(caixa)
    response = client.post(
        reverse("api-backstage-pos-cash-drawer-block"),
        data={"duration_ms": 2000, "outcome": "dismissed"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert _blocks()[0].payload["outcome"] == "dismissed"


def test_desistir_demais_no_mesmo_turno_vira_anomalia(caixa):
    """Cliente que vai embora acontece; acontecer o dia inteiro é outra coisa."""
    for _ in range(4):
        pos_service.record_drawer_block(operator=caixa, duration_ms=3000, outcome="dismissed")

    (anomalia,) = [a for a in _relatorio().drawer_anomalies if a.code == "gave_up_repeatedly"]
    assert anomalia.operator == "marina"
    assert "4×" in anomalia.detail


def test_desistir_de_vez_em_quando_nao_acusa_ninguem(caixa):
    for _ in range(2):
        pos_service.record_drawer_block(operator=caixa, duration_ms=3000, outcome="dismissed")

    assert [a for a in _relatorio().drawer_anomalies if a.code == "gave_up_repeatedly"] == []


def test_a_desistencia_aparece_na_coluna_do_operador(caixa):
    pos_service.record_drawer_block(operator=caixa, duration_ms=3000, outcome="dismissed")
    pos_service.record_drawer_block(operator=caixa, duration_ms=1000, outcome="closed")

    linha = _relatorio().drawer_by_operator[0]
    assert linha.dismissals == 1
    assert linha.blocks == 2, "desistir também é um bloqueio que aconteceu"


def test_desistencia_repetida_e_por_PESSOA_como_as_outras(caixa):
    outro = get_user_model().objects.create_user(username="bruno", password="x", is_staff=True)
    _grant(outro, "operate_pos")
    for _ in range(4):
        pos_service.record_drawer_block(operator=outro, duration_ms=3000, outcome="dismissed")
    pos_service.record_drawer_block(operator=caixa, duration_ms=1000, outcome="closed")

    desistentes = [a for a in _relatorio().drawer_anomalies if a.code == "gave_up_repeatedly"]
    assert [a.operator for a in desistentes] == ["bruno"]
