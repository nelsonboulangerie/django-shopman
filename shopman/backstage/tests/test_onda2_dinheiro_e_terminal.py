"""Onda 2: o typo que derrubava o servidor, o fundo que sumia, e a segunda gaveta.

Três achados independentes, com a mesma raiz: **em dinheiro, a omissão vinha
degradando para o permissivo em silêncio** — zero, 500, ou a gaveta errada.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from shopman.cashman.models import Entry, Shift, Terminal

from shopman.backstage.services import orders as orders_service
from shopman.backstage.services import pos as pos_service
from shopman.backstage.services.exceptions import OrderError, POSError


@pytest.fixture
def operador(db):
    user = User.objects.create_user("op-onda2", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get_for_model(Shift), codename="operate_pos"
        )
    )
    return User.objects.get(pk=user.pk)


# ── O fundo de troco que sumia ───────────────────────────────────────────────


@pytest.mark.django_db
def test_abrir_caixa_com_valor_NEGATIVO_e_recusado(operador):
    """O `max(0, ...)` engolia o sinal e o turno abria SEM lançar fundo nenhum.

    A assimetria era gritante: o fechamento recusa negativo. O operador achava que
    tinha declarado o fundo, e a contagem cega no fim do dia acusava o fundo real
    como diferença sem explicação.
    """
    Terminal.objects.get_or_create(ref="balcao", defaults={"label": "Balcão"})

    with pytest.raises(POSError):
        pos_service.open_cash_shift(
            operator=operador, opening_amount_raw="-10,00", terminal_ref="balcao"
        )

    assert not Shift.objects.filter(status=Shift.Status.OPEN).exists()


@pytest.mark.django_db
def test_abrir_caixa_vazio_continua_valendo_zero(operador):
    """Assert-positivo: "não declarei fundo" é resposta legítima do balcão."""
    Terminal.objects.get_or_create(ref="balcao", defaults={"label": "Balcão"})

    turno = pos_service.open_cash_shift(
        operator=operador, opening_amount_raw="", terminal_ref="balcao"
    )

    assert turno.status == Shift.Status.OPEN
    assert not Entry.objects.filter(shift=turno, kind=Entry.Kind.FLOAT_IN).exists()


@pytest.mark.django_db
def test_abrir_caixa_com_fundo_lanca_a_linha(operador):
    Terminal.objects.get_or_create(ref="balcao", defaults={"label": "Balcão"})

    turno = pos_service.open_cash_shift(
        operator=operador, opening_amount_raw="100,00", terminal_ref="balcao"
    )

    assert Entry.objects.get(shift=turno, kind=Entry.Kind.FLOAT_IN).amount_q == 10000


# ── O typo que virava 500 ────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("digitado", ["12,,30", "abc", "R$ vinte"])
def test_typo_no_troco_do_entregador_vira_erro_de_pedido_e_nao_500(digitado):
    """`POSError` é IRMÃ de `OrderError`, não subclasse — e a view só captura a segunda.

    Com o parser fora do `try`, o campo livre "Troco para o entregador" derrubava o
    servidor: 500, stacktrace no log, e a tela dizendo "Falha na ação" sem ninguém
    saber que foi o campo.
    """
    from shopman.orderman.models import Order

    pedido = Order.objects.create(ref=f"ONDA2-{digitado[:3]}", channel_ref="web", total_q=1000)

    # O que importa é o TIPO: `OrderError` é o que a view sabe traduzir em 400.
    with pytest.raises(OrderError):
        orders_service.advance_order(pedido, actor="op", change_out_raw=digitado)


@pytest.mark.django_db
@pytest.mark.parametrize("digitado", ["12,,30", "abc"])
def test_typo_no_acerto_da_entrega_tambem_nao_derruba(digitado, operador):
    from shopman.orderman.models import Order

    Terminal.objects.get_or_create(ref="balcao", defaults={"label": "Balcão"})
    pos_service.open_cash_shift(operator=operador, opening_amount_raw="0", terminal_ref="balcao")
    pedido = Order.objects.create(ref=f"ONDA2S-{digitado[:3]}", channel_ref="web", total_q=1000)

    with pytest.raises(OrderError):
        orders_service.settle_delivery_cash(
            pedido, actor="op", operator=operador, amount_raw=digitado
        )


# ── A segunda gaveta ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_uma_gaveta_resolve_sozinha(db):
    """O caso de hoje não muda: com uma gaveta ativa, nada precisa ser dito."""
    Terminal.objects.all().delete()
    Terminal.objects.create(ref="balcao", label="Balcão", is_active=True)

    assert pos_service.resolve_terminal("").ref == "balcao"


@pytest.mark.django_db
def test_estacao_com_terminal_que_sumiu_NAO_derruba_o_PDV(db):
    """O ref do cookie é contexto ambiente, não afirmação de quem chama.

    Um dispositivo provisionado como estação `balcao` cujo `Terminal` foi depois
    desativado ou renomeado passava a receber 500 no PDV inteiro — trocar um problema
    por outro maior. Ref explícito no PAYLOAD continua sendo recusado (é afirmação).
    """
    Terminal.objects.all().delete()
    Terminal.objects.create(ref="balcao", label="Balcão", is_active=True)

    assert pos_service.resolve_terminal("sumiu", strict=False).ref == "balcao"
    with pytest.raises(POSError):
        pos_service.resolve_terminal("sumiu")


@pytest.mark.django_db
def test_duas_gavetas_COM_estacao_resolvem_a_certa(db):
    """A estação já sabe qual gaveta é: o cookie de confiança carrega o ref.

    É isto que impede a falha fechada de virar uma loja de duas gavetas paralisada.
    """
    Terminal.objects.all().delete()
    Terminal.objects.create(ref="balcao-1", label="Balcão 1", is_active=True)
    Terminal.objects.create(ref="balcao-2", label="Balcão 2", is_active=True)

    assert pos_service.resolve_terminal("balcao-2").ref == "balcao-2"


@pytest.mark.django_db
def test_a_projection_e_a_mutacao_resolvem_a_MESMA_gaveta(db, operador):
    """Eram dois resolvers, e a divergência paralisava o PDV.

    A projection usava `Terminal.default()` (→ `pdv-main`) e as mutações o primeiro
    ativo em ordem alfabética (→ `balcao-2`). O turno abria num, tudo o mais falava
    com o outro: "Caixa não aberto" em toda mutação, 409 na venda, e o turno aberto
    não podia nem ser fechado pela tela. Não havia saída pela UI.
    """
    from shopman.backstage.projections.pos import build_pos

    Terminal.objects.all().delete()
    Terminal.objects.create(ref="pdv-main", label="Principal", is_active=True)

    projecao = build_pos(operator=operador, terminal_ref="")

    assert projecao.terminal_ref == pos_service.resolve_terminal("").ref
