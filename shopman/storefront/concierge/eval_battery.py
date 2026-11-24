"""O ensaio do leitor da Nice no ar: a bateria de pedidos pela IA do perfil, sem efeito e sem escrita.

Passo 5 do pedido pelo motor (dono, 23/11/2026: a bateria roda no app do ar, pela conexão DeepSeek que
já existe, sem chave em máquina nenhuma). Cada caso é uma conversa: as falas da cliente, na ordem, e o
que a leitura precisa ter entendido no fim (os produtos e as quantidades, o dia, retirada ou entrega, e
a janela da grade da casa que cobre a hora dita).

O que roda é o leitor de verdade (``NiceReader``: o portão do Jev e a extração pela rota ``intents``,
com o freio e o medidor de gasto da casa). A sacola e o recebimento são acumulados em memória, numa
conversa que não é gravada: nenhum efeito, nenhuma mensagem, nenhuma linha nova no banco (o medidor de
gasto da casa registra as chamadas, como toda chamada paga). O produto é conferido pelo NOME do item no
catálogo do ar, não pelo SKU de um teste.

A leitura vai com a conversa em volta, como o motor a passa (ADR-051): as falas anteriores e, nos grupos
"continuidade" e "ruptura", a pergunta da Nice no ar antes da última fala. A conferência de coerência e o
verificador rodam como no motor; na dúvida, nada se aplica (o turno perguntaria), e o caso mede isso.

O texto da resposta não entra aqui: ele depende do motor ligado (linha P08) e da decisão da #3374.
"""

from __future__ import annotations

import calendar
import time
import unicodedata
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta

#: O produto esperado, pelo nome no catálogo (dobrado: sem acento, minúsculo).
#: O "pão de campanha" é, no cardápio, o "Pain de Campagne": a busca não acha "campanha" (#3484), então a bateria
#: pede pelo nome do cardápio. O produto que o cardápio do ar não tem pula o caso (``sem_produto``).
C, P, B, CA, PF, S = "croissant", "pain au chocolat", "baguete", "campagne", "pao frances", "sonho"


@dataclass(frozen=True)
class Caso:
    id: str
    falas: tuple[str, ...]
    sacola: dict[str, int]
    dia: object = None  # deslocamento em dias, "sabado", "dia25", ou None (não confere)
    recebe: str | None = None  # "pickup" / "delivery" / None (não confere)
    janela: str | None = None  # ref da janela da grade, ou None (não confere)
    grupo: str = ""
    # A pergunta da Nice no ar antes da ÚLTIMA fala (ADR-051): o código da condição, ou "terms" (o resumo).
    pergunta: str | None = None
    pagamento: str | None = None  # a forma lida ("pix"), ou None (não confere)
    atos: tuple[str, ...] = ()  # a última fala precisa ter UM destes atos (vazio: não confere)


def _c(id, falas, sacola, **kw):
    return Caso(id=id, falas=(falas,) if isinstance(falas, str) else tuple(falas), sacola=sacola, **kw)


CASOS = (
    # ── Tudo numa frase, retirada ──
    _c("frase-cartao-1", "quero 2 croissants para retirar amanhã às 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-cartao-1-sem-acento", "quero 2 croissants para retirar amanha as 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-busco-16h", "2 croissant pra amanha, busco 16h", {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="uma frase"),
    _c("frase-pegar-10h", "quero 3 pain au chocolat pra pegar amanhã às 10h", {P: 3}, dia=1, recebe="pickup", janela="slot-09", grupo="uma frase"),
    _c("frase-passo-ai", "me separa 2 baguetes pra amanhã, passo aí às 13h", {B: 2}, dia=1, recebe="pickup", janela="slot-12", grupo="uma frase"),
    _c("frase-a-tarde", "quero 1 pain de campagne para retirar amanhã à tarde", {CA: 1}, dia=1, recebe="pickup", grupo="uma frase"),
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
    _c("entrega-entregar", "quero 1 pain de campagne pra entregar amanhã", {CA: 1}, dia=1, recebe="delivery", grupo="entrega"),
    _c("entrega-em-casa", "me manda 2 baguetes em casa amanhã", {B: 2}, dia=1, recebe="delivery", grupo="entrega"),
    # ── Espalhado em várias falas ──
    _c("espalhado-tres", ["quero 2 croissants", "pra amanhã", "vou buscar às 16h"], {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="espalhado"),
    _c("espalhado-oi-primeiro", ["oi", "quero 2 croissants", "amanhã às 16h, retirada"], {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="espalhado"),
    _c("espalhado-dia-depois-hora", ["quero 2 croissants pra amanhã", "busco às 16h"], {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="espalhado"),
    _c("espalhado-telegrafico", ["2 croissants", "retirada amanhã 16h"], {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="espalhado"),
    _c("espalhado-sabado", ["quero 3 baguetes", "é pra sábado", "passo aí às 10h"], {B: 3}, dia="sabado", recebe="pickup", janela="slot-09", grupo="espalhado"),
    _c("espalhado-dois-produtos", ["quero 2 croissants", "e 1 pain de campagne", "pra amanhã às 16h, vou retirar"], {C: 2, CA: 1}, dia=1, recebe="pickup", janela="slot-15", grupo="espalhado"),
    _c("espalhado-so-a-hora", ["quero 2 croissants pra retirar amanhã", "às 16h"], {C: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="espalhado"),
    # ── Correção no meio ──
    _c("corrige-na-verdade-3", ["quero 2 croissants", "na verdade 3"], {C: 3}, grupo="correção"),
    _c("corrige-sao-3-com-data", ["quero 2 croissants pra amanhã às 16h, vou buscar", "na verdade são 3"], {C: 3}, dia=1, recebe="pickup", janela="slot-15", grupo="correção"),
    _c("corrige-nao-quero-4", ["quero 2 croissants", "não, quero 4"], {C: 4}, grupo="correção"),
    _c("corrige-hora", ["quero 2 croissants pra retirar amanhã às 16h", "melhor às 10h"], {C: 2}, dia=1, recebe="pickup", janela="slot-09", grupo="correção"),
    _c("corrige-dia", ["quero 2 croissants pra retirar amanhã", "na verdade depois de amanhã"], {C: 2}, dia=2, recebe="pickup", grupo="correção"),
    _c("corrige-tira-um-produto", ["quero 2 croissants e 2 pain au chocolat", "tira o pain au chocolat"], {C: 2}, grupo="correção"),
    _c("corrige-troca-produto", ["quero 2 croissants", "troca por pain au chocolat"], {P: 2}, grupo="correção"),
    _c("corrige-tira-um", ["quero 3 croissants", "tira 1"], {C: 2}, grupo="correção"),
    _c("corrige-retira-o-croissant", ["quero 2 croissants pra amanhã às 16h, vou buscar", "retira o croissant"], {}, grupo="correção"),
    # ── Produto que não tem (na data, ou nunca) ──
    _c("sem-fora-de-venda", "quero 2 brioches pra amanhã", {}, grupo="não tem"),
    _c("sem-hoje-tem-amanha", "quero 2 sonhos pra retirar amanhã às 16h", {S: 2}, dia=1, recebe="pickup", janela="slot-15", grupo="não tem"),
    _c("sem-fornada-na-data", "quero 2 sonhos pra retirar amanhã às 16h", {}, grupo="não tem"),
    _c("sem-no-cardapio", "quero 2 empadas pra amanhã", {}, grupo="não tem"),
    # ── Continuidade: a resposta curta à pergunta da Nice no ar (ADR-051) ──
    _c("cont-16h", ["quero 2 croissants pra amanhã", "16h"], {C: 2}, dia=1, janela="slot-15", pergunta="delivery_time_slot", grupo="continuidade"),
    _c("cont-as-10", ["quero 2 croissants pra amanhã", "às 10"], {C: 2}, dia=1, janela="slot-09", pergunta="delivery_time_slot", grupo="continuidade"),
    _c("cont-vou-buscar-16h", ["quero 2 croissants pra amanhã", "vou buscar às 16h"], {C: 2}, dia=1, recebe="pickup", janela="slot-15", pergunta="delivery_time_slot", grupo="continuidade"),
    _c("cont-amanha", ["quero 2 croissants", "amanhã"], {C: 2}, dia=1, pergunta="fulfillment_date", grupo="continuidade"),
    _c("cont-retirada", ["quero 2 croissants pra amanhã", "retirada"], {C: 2}, dia=1, recebe="pickup", pergunta="fulfillment_type", grupo="continuidade"),
    _c("cont-pix", ["quero 2 croissants", "pix"], {C: 2}, pagamento="pix", pergunta="payment_method", grupo="continuidade"),
    _c("cont-o-do-trabalho", ["quero 2 croissants com entrega amanhã", "o do trabalho"], {C: 2}, dia=1, recebe="delivery", atos=("give_address", "affirm"), pergunta="delivery_address_saved", grupo="continuidade"),
    _c("cont-sim-resumo", ["quero 2 croissants", "sim"], {C: 2}, atos=("affirm",), pergunta="terms", grupo="continuidade"),
    _c("cont-na-verdade-3", ["quero 2 croissants", "na verdade 3"], {C: 3}, pergunta="terms", grupo="continuidade"),
    # ── Ruptura: o cliente muda de assunto no meio do fechamento ──
    _c("rupt-pao-de-queijo", ["quero 2 croissants pra amanhã", "tem pão de queijo?"], {C: 2}, dia=1, atos=("ask_item",), pergunta="delivery_time_slot", grupo="ruptura"),
    _c("rupt-que-horas-fecham", ["quero 2 croissants pra amanhã", "que horas vocês fecham?"], {C: 2}, dia=1, atos=("ask_hours",), pergunta="delivery_time_slot", grupo="ruptura"),
    _c("rupt-mais-um", ["quero 2 croissants", "põe mais um croissant"], {C: 3}, pergunta="payment_method", grupo="ruptura"),
    _c("rupt-cancela", ["quero 2 croissants", "cancela"], {C: 2}, atos=("deny", "cancel_order"), pergunta="payment_method", grupo="ruptura"),
)



def fold(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", str(text or "").casefold())
                   if not unicodedata.combining(ch))


def dia(spec, today: date) -> str:
    if isinstance(spec, int):
        return (today + timedelta(days=spec)).isoformat()
    if spec == "sabado":
        return (today + timedelta(days=(5 - today.weekday()) % 7 or 7)).isoformat()
    if spec == "dia25":
        if today.day < 25:
            return today.replace(day=25).isoformat()
        year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        return date(year, month, min(25, calendar.monthrange(year, month)[1])).isoformat()
    raise ValueError(spec)


def texto(fala: str, today: date) -> str:
    """``{dm+2}`` vira a data de daqui a dois dias em dd/mm (a bateria roda em qualquer dia)."""
    for offset in range(8):
        fala = fala.replace(f"{{dm+{offset}}}", (today + timedelta(days=offset)).strftime("%d/%m"))
    return fala


def janela_da_hora(hora: str) -> str:
    """A janela da grade da casa que cobre a hora dita (a mesma regra do executor da loja)."""
    from shopman.shop.services.fulfillment_window import canonical_slots

    from .order_closing import _match_slot

    hours, minutes = (int(part) for part in hora.split(":"))
    slots = [{"ref": s["ref"], "label": s.get("label", "")} for s in canonical_slots()]
    chosen = _match_slot(slots, hours * 60 + minutes)
    return str(chosen["ref"]) if chosen else ""


@dataclass
class Fala:
    texto: str
    leitor: str
    atos: list
    ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    erro: str = ""  # o erro verdadeiro da IA, quando a fala caiu para a regra local
    verificador: str = ""  # a conferência (ADR-051): "escolheu 1", "dúvida: confirmar", "dúvida: perguntar de novo"


@dataclass
class Resultado:
    caso: Caso
    passou: bool
    erros: list[str]
    falas: list[Fala] = field(default_factory=list)
    sacola: dict[str, int] = field(default_factory=dict)
    recebimento: dict[str, str] = field(default_factory=dict)
    pulado: str = ""  # o produto esperado não está no cardápio do ar: o caso não mede a leitura


def sem_produto(caso: Caso) -> list[str]:
    """Os produtos esperados pelo caso que o cardápio publicado não tem (pelo nome dobrado).

    O caso que espera um produto fora do cardápio reprovaria pelo dado, não pela leitura (#3484): ele sai
    pulado, com o nome do que falta, e nenhuma chamada à IA é feita para ele.
    """
    from shopman.offerman.models import Product

    nomes = [fold(nome) for nome in Product.objects.filter(is_published=True, is_sellable=True)
             .values_list("name", flat=True)]
    return [produto for produto in caso.sacola if not any(produto in nome for nome in nomes)]


def _nomes(skus) -> dict[str, str]:
    from shopman.offerman.models import Product

    return {p.sku: p.name for p in Product.objects.filter(sku__in=list(skus))}


def conferir(caso: Caso, sacola: dict[str, int], recebimento: dict[str, str], today: date,
             pagamento: str = "", ultimos: tuple[str, ...] = ()) -> list[str]:
    """O que a leitura entendeu, contra o esperado. Lista vazia: passou."""
    erros: list[str] = []
    nomes = {sku: fold(nome) for sku, nome in _nomes(sacola).items()}
    restante = dict(sacola)
    for produto, quantidade in caso.sacola.items():
        sku = next((sku for sku in restante if produto in nomes.get(sku, fold(sku))), None)
        if sku is None:
            erros.append(f"faltou {produto} x{quantidade}")
            continue
        if restante.pop(sku) != quantidade:
            erros.append(f"{produto}: {sacola[sku]}, esperado {quantidade}")
    erros.extend(f"sobrou {nomes.get(sku, sku)} x{q}" for sku, q in restante.items())
    if caso.dia is not None and recebimento.get("date") != dia(caso.dia, today):
        erros.append(f"dia {recebimento.get('date') or '-'}, esperado {dia(caso.dia, today)}")
    # A hora dita sem o modo é a de buscar: a regra da casa no executor (``effect_site._set_fulfillment``, a mesma
    # do fechamento de hoje), e a Nice diz "Combinado: retirada amanhã às 16h". O leitor não inventa o modo; a
    # bateria confere o recebimento que a casa grava (#5 do ensaio no ar, 24/11: "frase-so-horario").
    modo = recebimento.get("mode") or ("pickup" if recebimento.get("time") else "")
    if caso.recebe and modo != caso.recebe:
        erros.append(f"recebimento {modo or '-'}, esperado {caso.recebe}")
    if caso.janela:
        lida = janela_da_hora(recebimento["time"]) if recebimento.get("time") else ""
        if lida != caso.janela:
            erros.append(f"janela {lida or '-'} (hora {recebimento.get('time') or '-'}), esperado {caso.janela}")
    if caso.pagamento and pagamento != caso.pagamento:
        erros.append(f"pagamento {pagamento or '-'}, esperado {caso.pagamento}")
    if caso.atos and not set(caso.atos) & set(ultimos):
        erros.append(f"última fala lida como {', '.join(ultimos) or '-'}, esperado {' ou '.join(caso.atos)}")
    return erros


def contexto(caso: Caso, anteriores: list[str], ultima: bool):
    """A conversa em volta da fala, como o motor a passa ao leitor (ADR-051): as falas anteriores do cliente e,
    na última, a pergunta da Nice no ar."""
    from conversational_commerce.engine.moves import expected_acts
    from conversational_commerce.engine.turn import TERMS_OFFER_ACTS
    from conversational_commerce.ports import PendingQuestion, ReadingContext, RecentTurn

    recentes = tuple(RecentTurn(role="customer", content_ref=f"text:{fala}") for fala in anteriores)
    if not (ultima and caso.pergunta):
        return ReadingContext(recent=recentes)
    if caso.pergunta == "terms":
        return ReadingContext(pending=PendingQuestion(kind="terms_offer", code="terms"),
                              expected_acts=TERMS_OFFER_ACTS, recent=recentes)
    return ReadingContext(pending=PendingQuestion(kind="condition", code=caso.pergunta),
                          expected_acts=expected_acts(caso.pergunta), recent=recentes)


@contextmanager
def leitura_do_cardapio() -> Iterator[None]:
    """A busca do cardápio no ensaio, sem a trava de posse do turno.

    No ar, a busca (``search_storefront``) só roda dentro de um turno com posse (``assert_turn_authority``),
    e o leitor acha o produto por ela. A conversa do ensaio é de memória, nunca gravada, e não tem posse:
    sem isto, TODA leitura de produto do ensaio voltava vazia (``claim_required``), e a bateria e os
    cartões reprovavam por um motivo que o ar não tem. Os testes do ensaio não viam, porque trocam a
    ferramenta inteira (``tools.execute``). Só a busca, que é leitura, e só enquanto o ensaio roda.
    """
    from . import tools

    guarded = tools._HANDLERS["search_storefront"]
    tools._HANDLERS["search_storefront"] = guarded.__wrapped__
    try:
        yield
    finally:
        tools._HANDLERS["search_storefront"] = guarded


def rodar(reader_for: Callable, *, channel_ref: str, today: date, max_calls: int, max_usd: float = 0.0,
          model: str = "", only: str = "") -> tuple[list[Resultado], dict]:
    """A bateria pelo leitor. ``reader_for(conversa, linhas)`` monta o leitor com a sacola em memória."""
    with leitura_do_cardapio():
        return _rodar(reader_for, channel_ref=channel_ref, today=today, max_calls=max_calls, max_usd=max_usd,
                      model=model, only=only)


def _rodar(reader_for: Callable, *, channel_ref: str, today: date, max_calls: int, max_usd: float,
           model: str, only: str) -> tuple[list[Resultado], dict]:
    from conversational_commerce.engine.acts import ACTS
    from conversational_commerce.ports import InterpretRequest, ModelRequest, TrustedContext

    from shopman.shop import ai_governor
    from shopman.shop.models import Conversation

    totais = {"chamadas": 0, "tokens_in": 0, "tokens_out": 0, "usd": 0.0, "interrompido": "", "erros": []}
    resultados: list[Resultado] = []
    for caso in CASOS:
        if only and only not in caso.id:
            continue
        faltam = sem_produto(caso)
        if faltam:
            resultados.append(Resultado(caso, False, [], pulado=f"sem produto no cardápio: {', '.join(faltam)}"))
            continue
        sacola: dict[str, int] = {}
        recebimento: dict[str, str] = {}
        pagamento = ""
        ultimos: tuple[str, ...] = ()
        conversa = Conversation(channel_ref=channel_ref)  # nunca gravada

        def linhas(_conversa, sacola=sacola):
            return [{"sku": sku, "qty": qty} for sku, qty in sacola.items()]

        reader = reader_for(conversa, linhas)
        ctx = TrustedContext(tenant="eval", environment="shadow", subject=None)
        falas: list[Fala] = []
        for numero, bruta in enumerate(caso.falas, 1):
            if totais["chamadas"] >= max_calls:
                totais["interrompido"] = f"teto de {max_calls} chamadas"
                break
            if max_usd and totais["usd"] >= max_usd:
                totais["interrompido"] = f"teto de US$ {max_usd:.2f}"
                break
            fala = texto(bruta, today)
            request = InterpretRequest(
                request=ModelRequest(purpose="interpret", data_class="redacted",
                                     budget={"max_calls": 1, "max_spend": {"amount_minor": 0, "currency": "BRL"}}),
                event_id=f"eval-{caso.id}-{numero}", content_ref=f"text:{fala}", allowed_acts=ACTS,
                context=contexto(caso, [texto(anterior, today) for anterior in caso.falas[:numero - 1]],
                                 numero == len(caso.falas)))
            started = time.perf_counter()
            reader.last_usage, reader.last_error = None, ""
            understanding, consumption = reader.interpret(ctx, request)
            ms = (time.perf_counter() - started) * 1000
            totais["chamadas"] += int(consumption.calls)
            usage = reader.last_usage
            tin, tout = int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0)
            totais["tokens_in"] += tin
            totais["tokens_out"] += tout
            if model:
                totais["usd"] += ai_governor.estimate_usd(model, tokens_in=tin, tokens_out=tout)
            acts, verificador = conferencia(reader, ctx, request, understanding, totais, model)
            if reader.last_error:
                totais["erros"].append(f"{caso.id} #{numero}: {reader.last_error}")
            atos = []
            for act in acts:
                fields = dict(act.fields)
                atos.append({"act": act.act, "fields": fields})
                if act.act == "change_quantity" and fields.get("item") and fields.get("quantity") is not None:
                    quantidade = int(str(fields["quantity"]))
                    if quantidade:
                        sacola[str(fields["item"])] = quantidade
                    else:
                        sacola.pop(str(fields["item"]), None)
                elif act.act == "choose_fulfillment":
                    recebimento.update({k: str(v) for k, v in fields.items() if k in ("date", "mode", "time")})
                elif act.act == "choose_payment" and fields.get("method"):
                    pagamento = str(fields["method"])
            ultimos = tuple(a["act"] for a in atos)
            falas.append(Fala(fala, understanding.reader.name, atos, ms, tin, tout, reader.last_error, verificador))
        erros = (conferir(caso, sacola, recebimento, today, pagamento, ultimos) if not totais["interrompido"]
                 else ["não rodou inteiro"])
        resultados.append(Resultado(caso, not erros, erros, falas, sacola, recebimento))
        if totais["interrompido"]:
            break
    return resultados, totais


def conferencia(reader, ctx, request, understanding, totais: dict, model: str) -> tuple[list, str]:
    """A conferência do motor sobre a leitura (ADR-051), com o verificador de verdade: os atos que o turno
    aplicaria e o que a conferência fez. Na dúvida, nada se aplica (o turno pergunta), e o caso mede isso."""
    from conversational_commerce.engine.turn import in_doubt, plan_conference
    from conversational_commerce.ports import AdjudicateRequest, ModelRequest, PortError

    from .profile import ADJUDICATIONS_PER_TURN

    acts = list(understanding.acts)
    plan = plan_conference(acts, understanding.alternatives, request.context)
    if plan is None or not ADJUDICATIONS_PER_TURN or not reader.capabilities().supports("adjudicate"):
        return acts, ""
    candidates = list(plan.candidates)
    adjudicate = AdjudicateRequest(
        request=ModelRequest(purpose="adjudicate", data_class="redacted",
                             budget={"max_calls": 1, "max_spend": {"amount_minor": 0, "currency": "BRL"}}),
        event_id=request.event_id, content_ref=request.content_ref, context=request.context,
        candidates=tuple(candidates))
    reader.last_usage = None
    try:
        adjudication = reader.adjudicate(ctx, adjudicate)
        choice = adjudication.choice
        totais["chamadas"] += int(adjudication.consumption.calls)
    except PortError:
        choice = None
    usage = reader.last_usage
    tin, tout = int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0)
    totais["tokens_in"] += tin
    totais["tokens_out"] += tout
    if model:
        from shopman.shop import ai_governor

        totais["usd"] += ai_governor.estimate_usd(model, tokens_in=tin, tokens_out=tout)
    if choice is not None:
        return list(candidates[choice].acts), f"{plan.found}: escolheu {choice}"
    doubt = in_doubt(plan)
    return [], f"{plan.found}: dúvida, " + ("confirmar" if "confirm" in doubt else "perguntar de novo")


def relatorio(resultados: list[Resultado], totais: dict) -> str:
    """O placar e a transcrição, em texto puro, para o console."""
    linhas = []
    passou = sum(r.passou for r in resultados)
    pulados = [r for r in resultados if r.pulado]
    usd = totais.get("usd", 0.0)
    tempos = sorted(f.ms for r in resultados for f in r.falas)
    p95 = tempos[max(0, int(len(tempos) * 0.95) - 1)] if tempos else 0.0
    linhas.append(f"bateria: {passou} / {len(resultados) - len(pulados)} passaram"
                  + (f" ({len(pulados)} pulados: produto fora do cardápio)" if pulados else ""))
    linhas.append(f"chamadas à IA: {totais['chamadas']} | tokens: {totais['tokens_in']} in, {totais['tokens_out']} out"
                  f" | custo estimado: US$ {usd:.4f} | latência p95: {p95:.0f} ms")
    if totais.get("interrompido"):
        linhas.append(f"INTERROMPIDO: {totais['interrompido']}")
    quedas = sum(1 for r in resultados for f in r.falas if f.leitor == "concierge-local-rules")
    if quedas:
        linhas.append(f"ATENÇÃO: {quedas} falas caíram para a regra local (a IA não respondeu)")
    linhas.extend(f"ERRO DA IA: {erro}" for erro in totais.get("erros", [])[:10])
    for r in resultados:
        linhas.append("")
        if r.pulado:
            linhas.append(f"[pulado] {r.caso.id} ({r.caso.grupo}): {r.pulado}")
            continue
        linhas.append(f"[{'ok' if r.passou else 'FALHOU'}] {r.caso.id} ({r.caso.grupo})")
        for f in r.falas:
            atos = "; ".join(a["act"] + (f" {a['fields']}" if a["fields"] else "") for a in f.atos)
            linhas.append(f"  > {f.texto}")
            linhas.append(f"    {f.leitor} · {f.ms:.0f} ms · {atos}")
            if f.verificador:
                linhas.append(f"    conferência: {f.verificador}")
            if f.erro:
                linhas.append(f"    erro da IA: {f.erro}")
        if not r.passou:
            linhas.extend(f"    ✗ {erro}" for erro in r.erros)
    return "\n".join(linhas)
