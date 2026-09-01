"""A janela combinada do pedido — o encontro entre o expediente e a fornada.

Duas perguntas moram aqui, e as duas precisam da MESMA resposta em toda
superfície:

1. *Quais janelas eu posso oferecer para o dia X, com este carrinho?* → ``annotate``
2. *Esta janela que chegou no payload pode ser aceita?* → ``validate``

A prontidão vem de ``product_readiness`` (a que horas cada SKU fica pronto). Uma
janela só é oferecível quando **começa** depois de tudo estar pronto: prometer
11:30 para um pão que sai às 12h é quebrar contrato na porta, e o cliente que
chega às 11:30 tem razão.

## Duas grades, e a data escolhe qual

- **HOJE** → as meias horas do expediente (``business_calendar.delivery_slots_for``).
  É a janela de quem vai buscar ou de quem vai entregar hoje, e ela precisa da
  granularidade fina: "14:00 às 14:30" é o que o operador combina com o
  entregador.
- **OUTRO DIA (encomenda)** → os slots canônicos da casa
  (``Shop.defaults["pickup_slots"]``: *A partir das 09h / 12h / 15h*, editáveis
  no Admin). Encomenda não é hora marcada, é fornada: o cliente escolhe o TURNO,
  e é assim que a loja já pergunta. Oferecer meia hora para daqui a três dias
  seria uma precisão que a padaria não tem como cumprir — e faria a loja e o
  balcão prometerem coisas diferentes sobre o mesmo pedido.

A prontidão corta as DUAS grades do mesmo jeito. A mediana do histórico é mais
precisa que o slot (11:37), mas na hora da encomenda ela é arredondada PARA CIMA
até o slot que a cobre (11:37 → *A partir das 12h*).

## Por que anotar em vez de filtrar

A janela impossível **aparece**, desabilitada, com o motivo em português de
balcão: *"A Baguette de Tradition sai às 12:00."* Sumir com ela deixa o operador
sem resposta para a pergunta que o cliente faz ("e às 9h não dá?"), e ele acaba
prometendo por fora do sistema.

## O que fecha a porta, e o que não fecha

``validate`` recusa **só** o eixo da prontidão — o único em que a casa promete
algo que não pode cumprir. A grade do expediente molda o que se OFERECE
(``annotate``), não o que se aceita: transformá-la em recusa faria a dona no
balcão às 18h05 não conseguir agendar a retirada de amanhã, e faria uma loja com
``opening_hours`` em branco recusar toda venda com horário. Ver a docstring de
``validate``.

E o silêncio não vira restrição: SKU sem prontidão conhecida (nem declarada, nem
observada) não segura nada — não há o que prometer errado sobre uma hora que
ninguém sabe. É a declaração (``Product.metadata["ready_from"]``) que existe
justamente para tirar produto desse limbo.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time

logger = logging.getLogger(__name__)


def _window_start(slot: dict) -> time | None:
    """A que horas esta janela COMEÇA.

    Duas grades, dois formatos, e por isso a hora sai do próprio slot:
    ``starts_at`` quando ele traz (os canônicos: ``{"ref": "slot-09",
    "starts_at": "09:00"}``), senão o ref, que nas meias horas já é o par de
    horas (``"14:00-14:30"``) e por isso se lê sozinho — inclusive num pedido
    antigo, depois de a casa mudar o expediente.

    ⚠️ Ler só o ref quebraria os canônicos em silêncio: ``"slot-09"`` partido no
    hífen dá ``"slot"``, que não é hora nenhuma — a janela passaria a não ter
    início e NENHUM corte de prontidão se aplicaria a ela.
    """
    from shopman.shop.services.product_readiness import parse_clock

    if not isinstance(slot, dict):
        return None
    declared = parse_clock(slot.get("starts_at"))
    if declared is not None:
        return declared
    return parse_clock(str(slot.get("ref") or "").split("-")[0])


#: Os slots de encomenda quando a casa ainda não configurou os dela.
DEFAULT_CANONICAL_SLOTS = [
    {"ref": "slot-09", "label": "A partir das 09h", "starts_at": "09:00"},
    {"ref": "slot-12", "label": "A partir das 12h", "starts_at": "12:00"},
    {"ref": "slot-15", "label": "A partir das 15h", "starts_at": "15:00"},
]


def canonical_slots() -> list[dict]:
    """Os slots de ENCOMENDA da casa — ``Shop.defaults["pickup_slots"]``.

    Editáveis no Admin (5 linhas de ref/rótulo/início). Esta é a ÚNICA fonte:
    o storefront lê daqui também. Dois vocabulários para o mesmo pedido seria o
    cliente ouvindo "12:00 às 12:30" no telefone e lendo "a partir das 12h" no
    acompanhamento — e ninguém sabendo qual das duas a casa vai cumprir.

    Mora em ``shop`` e não no storefront porque **backstage não importa
    storefront**: era isso que deixava o balcão sem acesso à grade da loja.
    """
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        if shop:
            slots = (shop.defaults or {}).get("pickup_slots")
            if slots:
                return [s for s in slots if isinstance(s, dict) and s.get("ref")]
    except Exception:
        logger.debug("fulfillment_window: could not load canonical slots", exc_info=True)
    return list(DEFAULT_CANONICAL_SLOTS)


def _grid_for(day: date, *, now: datetime | None = None, shop=None) -> list[dict]:
    """A grade que vale para ``day``: meia hora hoje, slot canônico no resto.

    ⚠️ Dia FECHADO não tem grade nenhuma, e isso vale para as duas. A meia hora
    já nascia vazia (``delivery_slots_for`` lê o expediente), mas o slot canônico
    é configuração da casa e não sabe de calendário: sem esta guarda, uma
    encomenda para um domingo em que a loja não abre voltaria com "A partir das
    09h" oferecido — promessa que ninguém tem como cumprir, para um dia em que
    não há ninguém na padaria.
    """
    from shopman.shop.services import business_calendar

    if day == _local_today(now=now, shop=shop):
        return list(business_calendar.delivery_slots_for(day, now=now, shop=shop))
    try:
        if not business_calendar.is_open_on(day, shop=shop):
            return []
        janela = business_calendar.selling_hours_for(day, shop=shop)
    except Exception:
        logger.debug("fulfillment_window: could not read the calendar for %s", day, exc_info=True)
        return canonical_slots()

    slots = canonical_slots()
    if janela is None:
        return slots
    # ⚠️ O slot canônico é configuração da casa e não sabe do expediente DAQUELE
    # dia. Numa loja que fecha às 11h, "A partir das 15h" seria oferecido para
    # uma padaria vazia. Fica só o que cabe entre abrir e fechar.
    abre, fecha = janela
    dentro = []
    for slot in slots:
        inicio = _window_start(slot)
        if inicio is None or (abre <= inicio < fecha):
            dentro.append(slot)
    return dentro


def _local_today(*, now: datetime | None = None, shop=None) -> date:
    """Hoje pelo relógio da LOJA — um tablet com fuso errado agendaria para ontem."""
    from django.utils import timezone

    if now is not None:
        return timezone.localtime(now).date() if timezone.is_aware(now) else now.date()
    return timezone.localdate()


#: Frase única para "não consegui apurar a prontidão". Não é "sem restrição".
UNKNOWN_READINESS = "Não deu para conferir o preparo agora. Tente de novo."


def readiness_for(skus: list[str]) -> tuple[time | None, str, str]:
    """``(hora, sku, nome)`` do item que segura o pedido — ou ``(None, "", "")``.

    O nome vem junto porque o motivo tem que falar do PRODUTO. "BF sai às 12:00"
    manda o operador abrir o Admin com o cliente na frente.

    ⚠️ Propaga ``ReadinessUnavailable``. "Não sei a hora deste SKU" e "não
    consegui perguntar" são estados DIFERENTES, e o primeiro libera enquanto o
    segundo não pode. Quem chama trata os dois separado.
    """
    from shopman.shop.services import product_readiness

    ready_at, sku = product_readiness.bottleneck(skus)
    if ready_at is None:
        return None, "", ""
    try:
        name = product_readiness.product_names([sku]).get(sku, sku)
    except Exception:
        logger.debug("fulfillment_window: could not name the bottleneck", exc_info=True)
        name = sku
    return ready_at, sku, name


def annotate(
    day: date,
    skus: list[str] | None = None,
    *,
    now: datetime | None = None,
    shop=None,
) -> dict:
    """As janelas de ``day``, anotadas para este carrinho.

    Devolve::

        {
            "windows": [{"ref", "label", "enabled", "reason"}, …],
            "earliest_ref": "12:00-12:30",   # a primeira oferecível, ou ""
            "ready_at": "12:00",             # a prontidão que manda, ou ""
            "bottleneck_sku": "BF",
            "bottleneck_name": "Baguette de Tradition",
        }

    A grade sai de ``_grid_for``: meia hora para HOJE, slot canônico para
    encomenda. ``is_today`` volta junto para a tela poder dizer a frase certa.

    ``windows`` vazio significa "não há expediente neste dia" — fechado, feriado,
    ou (para hoje) o expediente já acabou. Todas as janelas desabilitadas com
    motivo de preparo significa outra coisa bem diferente: **há** expediente, mas
    este carrinho não cabe neste dia. Quem consome precisa saber distinguir os
    dois para dizer a frase certa.
    """
    from shopman.shop.services.product_readiness import ReadinessUnavailable, format_clock

    is_today = day == _local_today(now=now, shop=shop)
    raw = _grid_for(day, now=now, shop=shop)
    try:
        ready_at, sku, name = readiness_for(list(skus or []))
    except ReadinessUnavailable:
        # Não deu para apurar: NENHUMA janela é oferecida, e a tela diz por quê.
        # Oferecer todas seria transformar uma falha de leitura em permissão.
        logger.warning("fulfillment_window: readiness unavailable for %s", skus, exc_info=True)
        return {
            "windows": [
                {**slot, "enabled": False, "reason": UNKNOWN_READINESS} for slot in raw
            ],
            "earliest_ref": "",
            "ready_at": "",
            "bottleneck_sku": "",
            "bottleneck_name": "",
            "is_today": is_today,
            "grid": "half_hour" if is_today else "canonical",
            "readiness_unavailable": True,
        }

    windows: list[dict] = []
    earliest_ref = ""
    for slot in raw:
        ref = str(slot.get("ref") or "")
        start = _window_start(slot)
        enabled = True
        reason = ""
        # O corte é o mesmo nas duas grades. Numa meia hora ele apaga
        # "09:00 às 09:30"; num slot canônico apaga "A partir das 09h". A
        # mediana precisa (11:37) vira o slot que a cobre porque a comparação é
        # com o INÍCIO da janela — 09:00 < 11:37 apaga, 12:00 >= 11:37 fica.
        if ready_at is not None and start is not None and start < ready_at:
            enabled = False
            reason = f"{name} sai às {format_clock(ready_at)}."
        if enabled and not earliest_ref:
            earliest_ref = ref
        windows.append({**slot, "enabled": enabled, "reason": reason})

    return {
        "windows": windows,
        "earliest_ref": earliest_ref,
        "ready_at": format_clock(ready_at),
        "bottleneck_sku": sku,
        "bottleneck_name": name,
        # Qual grade veio: a tela fala "horário" numa e "turno" na outra.
        "is_today": is_today,
        "grid": "half_hour" if is_today else "canonical",
    }


def validate(
    day: date,
    window_ref: str,
    skus: list[str] | None = None,
    *,
    now: datetime | None = None,
    shop=None,
) -> str | None:
    """Erro em português de balcão, ou ``None`` quando a janela pode ser aceita.

    ## Dois eixos, e só um deles fecha a porta

    **Prontidão fecha.** Prometer 09:00 para um pão que sai às 12:00 é quebra de
    contrato com quem aparece às 9h. Não há gesto do operador que conserte isso
    depois, então a recusa é no commit e vale para toda superfície.

    **O expediente NÃO fecha.** A grade de meias horas do ``business_calendar``
    existe para dizer o que a casa OFERECE — a antecedência mínima, o
    fechamento, o dia sem escala. Transformá-la em recusa aqui é outra coisa: a
    dona no balcão às 18h05 combinando a retirada de amanhã, o operador acertando
    uma hora fora da grade com um cliente conhecido, e — pior — uma loja com
    ``opening_hours`` em branco, onde a grade é vazia e TODA venda com horário
    seria recusada. Nenhum desses é promessa quebrada; são a casa exercendo a
    própria agenda no próprio balcão.

    Janela em branco passa: "a combinar" é resposta legítima, e exigir hora aqui
    inventaria uma fricção que a casa não tem. Ref em formato livre ("manhã")
    também passa — sem eixo de hora não há o que conferir.
    """
    ref = str(window_ref or "").strip()
    if not ref:
        return None
    context = annotate(day, skus, now=now, shop=shop)

    # A hora de início vem da GRADE do dia, não do ref cru. Um canônico
    # ("slot-09") não carrega hora no nome: quem sabe que ele começa às 09:00 é
    # a configuração da casa. Só quando o ref não está na grade é que ele tenta
    # se explicar sozinho — o que funciona para a meia hora ("14:00-14:30") e é
    # justamente o caso do pedido antigo, depois de a casa mudar o expediente.
    from shopman.shop.services.product_readiness import format_clock

    conhecido = next((w for w in context["windows"] if w.get("ref") == ref), None)
    start = _window_start(conhecido) if conhecido else _window_start({"ref": ref})

    # ⚠️ Janela de HOJE que já começou NÃO é recusada, e a decisão é deliberada.
    #
    # A auditoria adversarial pediu a recusa (uma fila offline reenviando o
    # rascunho da manhã às 17h). Mas a suíte do repo mostrou o preço: uma comanda
    # aberta às 13h40 com "14:00 às 14:30", fechada às 14h35 — almoço movimentado,
    # cliente que voltou para pegar mais um pão — seria RECUSADA com o cliente na
    # frente, e o operador sem gesto para salvar a venda.
    #
    # É o mesmo eixo do expediente: a grade de hoje já não OFERECE a janela
    # passada (`delivery_slots_for` corta pela antecedência), e isso basta. Uma
    # janela vencida num pedido de hoje é cosmética — o KDS e a baixa disparam na
    # hora de qualquer jeito. Só a PRONTIDÃO fecha a porta.

    if context.get("readiness_unavailable"):
        # Falha FECHADO. Uma venda recusada se refaz em segundos; um horário
        # prometido errado só aparece com o cliente na porta.
        return UNKNOWN_READINESS

    ready_at, _sku, name = readiness_for(list(skus or []))
    if ready_at is None:
        # Nada no carrinho tem hora conhecida: não há promessa a proteger, e
        # inventar restrição a partir do silêncio recusaria venda por nada.
        return None

    if start is None:
        # ⚠️ Ref que a grade não conhece E que não se lê como hora, com o
        # carrinho tendo prontidão: RECUSA.
        #
        # Isto já passou livre, e o caminho era constrangedor: "09:00-09:30" era
        # recusado, mas "09:00 às 09:30" — o RÓTULO que a própria tela mostra —
        # passava e era gravado. A guarda era derrotável pela string que o
        # sistema exibe. Uma fila offline, um cliente novo ou um copiar-colar
        # bastavam.
        #
        # "A combinar" continua livre porque ele é a AUSÊNCIA de ref (tratada
        # bem antes, no `if not ref`), não um ref ilegível.
        return (
            "Horário combinado não reconhecido. Escolha um da lista "
            f"({name} sai às {format_clock(ready_at)})."
        )

    if start >= ready_at:
        return None

    erro = f"{name} sai às {format_clock(ready_at)}."
    earliest = context.get("earliest_ref")
    if earliest:
        label = next(
            (w.get("label") for w in context["windows"] if w.get("ref") == earliest), earliest
        )
        return f"{erro} Escolha {label} ou mais tarde."
    return f"{erro} Escolha outra data."
