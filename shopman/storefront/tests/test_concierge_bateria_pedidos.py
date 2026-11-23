# ruff: noqa: F401, F811
"""A bateria de pedidos como a cliente escreve no WhatsApp (DEV-2026-076, ensaio de 22/11/2026).

O dono, depois do ensaio: "Não passou da primeira pergunta!!! Gravíssimo". Cada caso aqui é uma
conversa: as falas da cliente, na ordem, e o que a casa precisa ter feito no fim (a sacola, o
dia, retirada ou entrega, o horário) e o que ela nunca pode ter dito ("tirei" o que a cliente
pediu, "vou verificar com a equipe" para quem só disse quando busca, "Indisponível" para o que
tem na data). Quantidade, produto, data ("hoje", "amanhã", "sábado", "dia 25", dd/mm), retirada
ou entrega e horário; tudo numa frase ou espalhado; sem acento, com erro de digitação e
abreviado; correção no meio; produto sem fornada na data.

**A leitura é a da casa, sem o modelo** (``intents.build_client`` sem cliente): o porteiro e a
divisão local, o caminho que roda quando o leitor de IA não responde, e o único que dá a mesma
resposta toda vez, como uma trava de CI precisa. A leitura pelo modelo (o Haiku do turno vivo)
não entra aqui: ela muda de uma chamada para outra e custa a cada rodada.

Caso que ainda falha fica em ``LACUNAS``, com a issue que o carrega: ele roda como ``xfail``
estrito, e o conserto que o fizer passar obriga a tirá-lo da lista. Nada falha em silêncio, e
o que passa não volta a quebrar.

``BATERIA_RELATORIO=<arquivo>`` grava, por caso, se passou, o porquê e a transcrição de cada
turno (para a medição antes e depois de um conserto).
"""

from __future__ import annotations

import calendar
import json
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

import pytest
from shopman.orderman.models import Session

from shopman.shop.models import ConversationMessage as Message
from shopman.storefront.concierge import intents
from shopman.storefront.tests.test_concierge_engine import (
    CONCIERGE_SETTINGS,
    _listed,
    conversation,
    customer,
    outbox,
    surface,
)
from shopman.storefront.tests.test_concierge_fechar_pedido import _turn

pytestmark = pytest.mark.django_db

#: O que a casa nunca diz numa conversa de pedido que deu certo.
NUNCA = (
    "tirei",  # tirou da sacola o que a cliente pediu
    "não tenho essa informação",  # "vou verificar" para quem só disse quando busca
    "deixei a pergunta com a equipe",
    "Indisponível",  # medido para agora o que tem na data
    "não entendi",
    "Sua sacola está vazia",
)


@dataclass(frozen=True)
class Caso:
    id: str
    falas: tuple[str, ...]
    sacola: dict[str, int]
    dia: object = None  # deslocamento em dias, "sabado", "dia25", ou None (não confere)
    recebe: str | None = None  # "pickup" / "delivery" / None (não confere)
    janela: str | None = None  # ref do horário de retirada, ou None (não confere)
    precisa: tuple[str, ...] = ()  # trechos que a resposta da casa precisa ter
    nunca: tuple[str, ...] = NUNCA
    cenario: str = ""  # estoque especial do caso
    grupo: str = ""


def _hoje() -> date:
    from django.utils import timezone

    return timezone.localdate()


def _dia(spec) -> str:
    today = _hoje()
    if isinstance(spec, int):
        return (today + timedelta(days=spec)).isoformat()
    if spec == "sabado":
        ahead = (5 - today.weekday()) % 7 or 7
        return (today + timedelta(days=ahead)).isoformat()
    if spec == "dia25":
        if today.day < 25:
            return today.replace(day=25).isoformat()
        year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        return date(year, month, min(25, calendar.monthrange(year, month)[1])).isoformat()
    raise ValueError(spec)


def _texto(fala: str) -> str:
    """``{dm+2}`` vira a data de daqui a dois dias em dd/mm (a bateria roda em qualquer dia)."""
    today = _hoje()
    for offset in range(0, 8):
        fala = fala.replace(f"{{dm+{offset}}}", (today + timedelta(days=offset)).strftime("%d/%m"))
    return fala


def _c(id, falas, sacola, **kw):
    return Caso(id=id, falas=(falas,) if isinstance(falas, str) else tuple(falas), sacola=sacola, **kw)


C, P, B, CA, PF, S = "CROISSANT", "PAIN-CHOCO", "BAGUETE", "PAO-CAMPANHA", "PAO-FRANCES", "SONHO"

CASOS = (
    # ── Tudo numa frase, retirada ──
    _c("frase-cartao-1", "quero 2 croissants para retirar amanhã às 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-cartao-1-sem-acento", "quero 2 croissants para retirar amanha as 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-busco-16h", "2 croissant pra amanha, busco 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-pegar-10h", "quero 3 pain au chocolat pra pegar amanhã às 10h", {P: 3}, dia=1, recebe="pickup", janela="slot-09", grupo="uma frase"),
    _c("frase-passo-ai", "me separa 2 baguetes pra amanhã, passo aí às 13h", {B: 2}, dia=1, recebe="pickup", janela="slot-12", grupo="uma frase"),
    _c("frase-a-tarde", "quero 1 pão de campanha para retirar amanhã à tarde", {CA: 1}, dia=1, recebe="pickup", grupo="uma frase"),
    _c("frase-vou-buscar-no-fim", "vou querer 4 croissants amanhã às 15h, vou buscar", {C: 4}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-dois-produtos", "queria 2 croissants e 2 pain au chocolat pra retirar amanhã às 16h", {C: 2, P: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-sabado", "quero 2 croissants pra retirar sábado às 10h", {C: 2}, dia="sabado", recebe="pickup", janela="slot-09", grupo="uma frase"),
    _c("frase-dia-25", "quero 2 croissants para retirar dia 25 às 16h", {C: 2}, dia="dia25", recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-dd-mm", "quero 2 croissants para retirar {dm+2} às 16h", {C: 2}, dia=2, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-depois-de-amanha", "quero 2 croissants pra depois de amanhã, retiro às 9h", {C: 2}, dia=2, recebe="pickup", janela="slot-09", grupo="uma frase"),
    _c("frase-numero-por-extenso", "dois croissants pra amanhã, vou buscar às 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-uma-baguete", "quero uma baguete pra amanhã, retiro 16h", {B: 1}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-telegrafica", "2 croissants amanhã 16h retirada", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-com-saudacao", "Oi! Quero 2 croissants pra retirar amanhã às 16h, por favor", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-bom-dia-encomendar", "bom dia, queria encomendar 6 croissants pra amanhã, busco às 9h", {C: 6}, dia=1, recebe="pickup", janela="slot-09", grupo="uma frase"),
    _c("frase-so-horario", "quero 2 croissant pra amanhã às 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-erro-digitacao", "quero 2 croisants pra amanhã, busco 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="digitação"),
    _c("frase-abreviada", "qro 2 croissants p amanha 16h retirada", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="digitação"),
    _c("frase-16h30", "quero 2 croissants pra buscar amanhã às 16h30", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-16-00", "quero 2 croissants pra amanhã 16:00 retirada", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-dez-unidades", "quero 10 croissants pra retirar amanhã às 16h", {C: 10}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-meia-duzia", "quero meia dúzia de croissants pra amanhã, busco às 16h", {C: 6}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    # ── Buscar, pegar, passo aí ──
    _c("verbo-pegar", "quero 2 croissants, vou pegar amanhã às 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="verbos"),
    _c("verbo-passo-ai", "quero 2 croissants, passo aí amanhã às 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="verbos"),
    _c("verbo-reserva-pego", "reserva 2 croissants pra mim pra amanhã, pego às 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="verbos"),
    _c("verbo-separa-passo-pra-pegar", "separa 2 croissants pra amanhã às 16h que eu passo pra pegar", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="verbos"),
    _c("verbo-de-manha", "quero 2 croissants pra amanhã de manhã, retiro às 9h", {C: 2}, dia=1, recebe="pickup", janela="slot-09", grupo="verbos"),
    _c("verbo-cartao-1-segunda-frase",
       "voce nao entendeu... quero 2 croissants para amanha e eu vou ai buscar (retirada) as 16h... entendeu?",
       {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="verbos"),
    # ── Só o pedido, sem quando ──
    _c("so-pedido", "quero 2 croissants", {C: 2}, grupo="só o pedido"),
    _c("so-pedido-hoje", "quero 2 croissants hoje", {C: 2}, grupo="só o pedido"),
    _c("so-pedido-pra-amanha", "quero 2 croissants para amanhã", {C: 2}, grupo="só o pedido"),
    # ── Entrega ──
    _c("entrega-com", "quero 2 croissants com entrega amanhã", {C: 2}, dia=1, recebe="delivery", grupo="entrega"),
    _c("entrega-entregar", "quero 1 pão de campanha pra entregar amanhã", {CA: 1}, dia=1, recebe="delivery", grupo="entrega"),
    _c("entrega-em-casa", "me manda 2 baguetes em casa amanhã", {B: 2}, dia=1, recebe="delivery", grupo="entrega"),
    # ── Espalhado em várias falas ──
    _c("espalhado-tres", ["quero 2 croissants", "pra amanhã", "vou buscar às 16h"], {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="espalhado"),
    _c("espalhado-oi-primeiro", ["oi", "quero 2 croissants", "amanhã às 16h, retirada"], {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="espalhado"),
    _c("espalhado-dia-depois-hora", ["quero 2 croissants pra amanhã", "busco às 16h"], {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="espalhado"),
    _c("espalhado-telegrafico", ["2 croissants", "retirada amanhã 16h"], {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="espalhado"),
    _c("espalhado-sabado", ["quero 3 baguetes", "é pra sábado", "passo aí às 10h"], {B: 3}, dia="sabado", recebe="pickup", janela="slot-09", grupo="espalhado"),
    _c("espalhado-dois-produtos", ["quero 2 croissants", "e 1 pão de campanha", "pra amanhã às 16h, vou retirar"], {C: 2, CA: 1}, dia=1, recebe="pickup", janela="slot-15", grupo="espalhado"),
    _c("espalhado-so-a-hora", ["quero 2 croissants pra retirar amanhã", "às 16h"], {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="espalhado"),
    # ── Correção no meio ──
    _c("corrige-na-verdade-3", ["quero 2 croissants", "na verdade 3"], {C: 3}, grupo="correção"),
    _c("corrige-sao-3-com-data", ["quero 2 croissants pra amanhã às 16h, vou buscar", "na verdade são 3"], {C: 3}, dia=1, recebe="pickup", janela="slot-15", grupo="correção"),
    _c("corrige-nao-quero-4", ["quero 2 croissants", "não, quero 4"], {C: 4}, grupo="correção"),
    _c("corrige-hora", ["quero 2 croissants pra retirar amanhã às 16h", "melhor às 10h"], {C: 2}, dia=1, recebe="pickup", janela="slot-09", grupo="correção"),
    _c("corrige-dia", ["quero 2 croissants pra retirar amanhã", "na verdade depois de amanhã"], {C: 2}, dia=2, recebe="pickup", grupo="correção"),
    _c("corrige-tira-um-produto", ["quero 2 croissants e 2 pain au chocolat", "tira o pain au chocolat"], {C: 2},
       nunca=tuple(n for n in NUNCA if n != "tirei"), grupo="correção"),
    _c("corrige-troca-produto", ["quero 2 croissants", "troca por pain au chocolat"], {P: 2},
       nunca=tuple(n for n in NUNCA if n != "tirei"), grupo="correção"),
    _c("corrige-tira-um", ["quero 3 croissants", "tira 1"], {C: 2}, nunca=tuple(n for n in NUNCA if n != "tirei"), grupo="correção"),
    _c("corrige-retira-o-croissant", ["quero 2 croissants pra amanhã às 16h, vou buscar", "retira o croissant"], {},
       nunca=tuple(n for n in NUNCA if n not in ("tirei", "Sua sacola está vazia")), grupo="correção"),
    # ── Produto que não tem (na data, ou nunca) ──
    _c("sem-fora-de-venda", "quero 2 brioches pra amanhã", {}, nunca=("tirei", "deixei a pergunta com a equipe"), grupo="não tem"),
    _c("sem-hoje-tem-amanha", "quero 2 sonhos pra retirar amanhã às 16h", {S: 2}, dia=1, recebe="pickup", janela="slot-15",
       cenario="sonho_amanha", grupo="não tem"),
    _c("sem-fornada-na-data", "quero 2 sonhos pra retirar amanhã às 16h", {},
       precisa=("Não há fornada de Sonho", "A próxima sai"), cenario="sonho_daqui_3", grupo="não tem"),
    _c("sem-no-cardapio", "quero 2 empadas pra amanhã", {}, nunca=("tirei", "deixei a pergunta com a equipe"), grupo="não tem"),
)

#: Caso que ainda falha → a issue que o carrega. Roda como xfail estrito: passou, sai daqui.
LACUNAS: dict[str, int] = {}


@pytest.fixture
def bateria(surface, settings, monkeypatch):
    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS
    # A leitura da casa, sem o modelo: o mesmo resultado a cada rodada.
    monkeypatch.setattr(intents, "build_client", lambda: None)
    _listed(C, "Croissant", description="Folhado amanteigado", stock="50")
    _listed(P, "Pain au Chocolat", description="Folhado com chocolate", stock="50")
    _listed(B, "Baguete", description="Pão francês longo", stock="50")
    _listed(CA, "Pão de Campanha", description="Fermentação natural", stock="50")
    _listed("BRIOCHE", "Brioche", description="Pão doce amanteigado", stock="0")
    from shopman.offerman.models import ListingItem

    ListingItem.objects.filter(product__sku="BRIOCHE").update(is_sellable=False)


def _cenario(nome: str) -> None:
    if not nome:
        return
    from shopman.stockman.models import Position, Quant

    _listed(S, "Sonho", description="Recheado de creme", stock="0")
    days = {"sonho_amanha": 1, "sonho_daqui_3": 3}[nome]
    Quant.objects.create(sku=S, position=Position.objects.get(ref="loja"), target_date=_hoje() + timedelta(days=days),
                         _quantity=Decimal("20"))


def _sessao(conversation):
    conversation.refresh_from_db()
    return Session.objects.filter(session_key=conversation.session_key).first() if conversation.session_key else None


def conversar(conversation, caso: Caso) -> tuple[list[str], list[dict]]:
    """Roda o caso e devolve (o que deu errado, a transcrição turno a turno)."""
    _cenario(caso.cenario)
    transcricao, respostas = [], []
    for fala in caso.falas:
        texto = _texto(fala)
        replies = _turn(conversation, texto)
        transcricao.append({"cliente": texto, "concierge": replies})
        respostas.extend(replies)
    erros = []
    sessao = _sessao(conversation)
    sacola = {item["sku"]: int(Decimal(str(item["qty"]))) for item in (sessao.items if sessao else [])}
    if sacola != caso.sacola:
        erros.append(f"sacola {sacola} (esperada {caso.sacola})")
    data = (sessao.data or {}) if sessao else {}
    if caso.dia is not None and str(data.get("delivery_date") or "") != _dia(caso.dia):
        erros.append(f"dia {data.get('delivery_date') or '(nenhum)'} (esperado {_dia(caso.dia)})")
    if caso.recebe is not None and data.get("fulfillment_type") != caso.recebe:
        erros.append(f"recebimento {data.get('fulfillment_type') or '(nenhum)'} (esperado {caso.recebe})")
    if caso.janela is not None and data.get("delivery_time_slot") != caso.janela:
        erros.append(f"horário {data.get('delivery_time_slot') or '(nenhum)'} (esperado {caso.janela})")
    tudo = "\n".join(respostas)
    erros += [f"disse {proibido!r}" for proibido in caso.nunca if proibido.casefold() in tudo.casefold()]
    erros += [f"não disse {preciso!r}" for preciso in caso.precisa if preciso.casefold() not in tudo.casefold()]
    if not respostas:
        erros.append("nenhuma resposta")
    return erros, transcricao


def _relatar(caso: Caso, erros: list[str], transcricao: list[dict]) -> None:
    destino = os.environ.get("BATERIA_RELATORIO")
    if not destino:
        return
    linha = {"id": caso.id, "grupo": caso.grupo, "passou": not erros, "erros": erros, "transcricao": transcricao}
    with open(destino, "a", encoding="utf-8") as saida:
        saida.write(json.dumps(linha, ensure_ascii=False) + "\n")


def _parametros():
    for caso in CASOS:
        marks = []
        if caso.id in LACUNAS:
            marks.append(pytest.mark.xfail(strict=True, reason=f"lacuna conhecida, #{LACUNAS[caso.id]}"))
        yield pytest.param(caso, id=caso.id, marks=marks)


def test_a_bateria_tem_pelo_menos_cinquenta_pedidos_e_ids_unicos():
    assert len(CASOS) >= 50
    assert len({caso.id for caso in CASOS}) == len(CASOS)
    assert set(LACUNAS) <= {caso.id for caso in CASOS}


@pytest.mark.parametrize("caso", list(_parametros()))
def test_pedido_como_a_cliente_escreve(conversation, outbox, bateria, caso):
    erros, transcricao = conversar(conversation, caso)
    _relatar(caso, erros, transcricao)
    assert not erros, "; ".join(erros) + "\n" + json.dumps(transcricao, ensure_ascii=False, indent=1)
