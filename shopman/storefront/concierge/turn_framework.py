"""O turno da Nice pelo motor do framework, atrás da chave e por classe de ação (N9a, #3199).

Aqui o motor do framework conversacional é montado com as portas e os livros do Shopman, e
``run`` decide, turno a turno, se a entrada sai pelo motor ou pelo caminho de hoje. Ninguém
chama ``run`` no turno vivo ainda: a troca no ``service.run_turn`` é o N9b.

As regras (decisão de 22/11/2026, "o motor fala"):

1. **A chave é da loja, por classe** (``Shop.conversational_live_*``, ADR-042), e todas nascem
   desligadas. Desligar "pedido" é o freio da escrita: informar e passar à equipe continuam.
2. **O motor só fala onde a casa tem a frase de hoje.** Os moldes da Nice (``nice_templates``)
   saem da copy da casa: a MESMA do caminho de hoje ou a frase nova que o dono aprovou na
   prévia ``previa-n9-frases`` (#3298). Molde sem frase aprovada fica fora, e o turno que
   precisaria dele cai no caminho de hoje, nunca numa frase genérica do pacote.
3. **Primeiro a sombra, depois o vivo.** O turno roda antes em ``environment=shadow`` (sem
   enviar, sem efeito, sem equipe). Só se todos os movimentos escolhidos são de classes
   ligadas e todos os moldes usados (``Composed.template_ids``) são da Nice, o turno roda de
   verdade, com o envio pelo mesmo caminho da resposta (``NiceChannel``). A mesma entrada dá a
   mesma decisão (K40), então o vivo repete o que a sombra conferiu.
4. **Nada derruba o turno.** Qualquer falha aqui devolve ``None``, e o caminho de hoje segue.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from conversational_commerce.engine import Engine, Ports
from conversational_commerce.engine.moves import templates
from conversational_commerce.engine.state import Subject
from conversational_commerce.ports import TrustedContext
from conversational_commerce.reply import Template

logger = logging.getLogger(__name__)

#: Classe de ação → movimentos. Movimento fora daqui (desconto, cancelamento, acréscimo, os
#: que o perfil não liga) nunca sai pelo motor no N9.
ACTION_CLASSES = {
    "inform": ("acknowledge", "inform", "cover_readings", "inform_limitation", "ask_clarification"),
    "handoff": ("handoff", "wait"),  # o aviso de prazo vencido é do compromisso com a equipe
    "order": ("present_terms", "change_cart", "set_fulfillment", "set_delivery_address", "set_payment",
              "commit_order"),
}
SWITCH_FIELD = {"inform": "conversational_live_inform", "handoff": "conversational_live_handoff",
                "order": "conversational_live_order"}
CLASS_OF_MOVE = {move: name for name, moves in ACTION_CLASSES.items() for move in moves}

#: Molde do motor → a chave de copy com a frase da Nice. As duas primeiras são a MESMA frase do
#: caminho de hoje (prévia de 22/11: "Igual"); as cinco seguintes são as frases novas que o dono
#: aprovou na prévia frase a frase (22/11, #3298). As que ele recusou (``ask_clarification.which``,
#: ``inform.price``, ``cover_readings.prices``) ficam de fora de propósito: o turno que precisaria
#: delas segue o caminho de hoje, com a frase de hoje.
NICE_TEMPLATE_COPY = {
    "acknowledge.got_it": "CONCIERGE_MEMORY_DECLINED",
    "acknowledge.thanks": "CONCIERGE_SMALL_TALK_THANKS",
    "ask_clarification.more": "CONCIERGE_ENGINE_ASK_MORE",
    "effect.failed": "CONCIERGE_ENGINE_EFFECT_FAILED",
    "handoff.routed": "CONCIERGE_ENGINE_HANDOFF_ROUTED",
    "handoff.routed_no_deadline": "CONCIERGE_ENGINE_HANDOFF_ROUTED_NO_DEADLINE",
    "handoff.not_accepted": "CONCIERGE_ENGINE_HANDOFF_NOT_ACCEPTED",
    # Aprovadas pelo dono em 23/11 (cartão do motor): o "total mudou" diz o total novo (substitui o
    # "Não" de 22/11, porque a frase de antes pedia o código), e o pedido registrado traz o link.
    "present_terms.changed": "CONCIERGE_ENGINE_TOTAL_CHANGED",
    "commit_order.done": "CONCIERGE_ENGINE_ORDER_PLACED",
    # Com os termos inteiros no motor (PR do Core, opção 1 aprovada em 23/11): a sacola e o resumo
    # com a frase de hoje; o resumo termina em "Posso registrar?" (aprovada no lugar do código).
    "change_cart.done": "CONCIERGE_ENGINE_CART_UPDATED",
    "present_terms.confirm": "CONCIERGE_ENGINE_TERMS_CONFIRM",
    # "Deixa pra lá" no resumo, sem efeito no turno: a MESMA frase do fechamento de hoje (#3388, "Igual").
    "acknowledge.terms_declined": "CONCIERGE_CLOSE_GAVE_UP",
    # A forma de pagamento escolhida pelo motor (cartão 5): "Combinado: Pix.", no molde do "Combinado".
    "set_payment.done": "CONCIERGE_ENGINE_PAYMENT_SET",
    # A entrega (cartão 2): as perguntas de hoje (o endereço, o que falta nele, o complemento) e o
    # "Combinado: entrega na Rua das Flores, 120." aprovado pelo dono em 23/11.
    "set_delivery_address.done": "CONCIERGE_ENGINE_ADDRESS_SET",
    "present_terms.needs_delivery_address": "CONCIERGE_CLOSE_ASK_ADDRESS",
    # O quando (#3482), com as perguntas de hoje do fechamento e na mesma ordem: o dia e retirar ou entregar.
    # O horário, com as opções do dia, está em ``PAYMENT_TEMPLATES`` (o espaço da casa troca de nome).
    "present_terms.needs_fulfillment_date": "CONCIERGE_CLOSE_ASK_DATE",
    "present_terms.needs_fulfillment_type": "CONCIERGE_CLOSE_ASK_FULFILLMENT",
    # A janela da entrega, depois do endereço: derivada da pergunta do horário (coordenação, 24/11).
    "present_terms.needs_delivery_window": "CONCIERGE_ENGINE_ASK_DELIVERY_WINDOW",
    "present_terms.needs_delivery_address_details": "CONCIERGE_ENGINE_ADDRESS_DETAILS",
    "present_terms.needs_delivery_complement": "CONCIERGE_ENGINE_ADDRESS_COMPLEMENT",
    # As recusas do endereço com as frases de hoje: fora da área (a frase do ``set_fulfillment`` e a
    # pergunta do endereço, como o fechamento junta) e endereço que não se localiza.
    "set_delivery_address.not_delivered": "CONCIERGE_ENGINE_ADDRESS_NOT_DELIVERED",
    "set_delivery_address.not_located": "CONCIERGE_ENGINE_ADDRESS_NOT_LOCATED",
    # O endereço sem a entrega combinada: a pergunta de hoje do fechamento, "retirada ou entrega?".
    "set_delivery_address.ask_mode": "CONCIERGE_CLOSE_ASK_FULFILLMENT",
    # O endereço do cadastro primeiro (dono, 25/09): a MESMA oferta de hoje (``address.saved_offer``), com uma
    # opção ou mais; o "não" a ela pergunta o endereço com a frase de hoje (#3421).
    "present_terms.needs_delivery_address_saved": "CONCIERGE_ENGINE_SAVED_ADDRESS_OFFER",
    "present_terms.needs_delivery_address_saved_many": "CONCIERGE_ENGINE_SAVED_ADDRESS_OFFER_MANY",
    "present_terms.needs_delivery_address_saved_declined": "CONCIERGE_CLOSE_ASK_ADDRESS",
    # O "outro" à oferta (#3454): a MESMA lista de hoje (``address.saved_listing``), cada endereço pela referência.
    "present_terms.needs_delivery_address_saved_options": "CONCIERGE_ENGINE_SAVED_ADDRESS_LIST",
    # A limitação: recusada em 22/11, com frase nova aprovada pelo dono em 23/11 (#3408). No ar, o efeito
    # recusado (sacola, recebimento, pagamento) refaz a decisão, e quem responde é este molde; a sombra
    # não executa efeito e não o vê, por isso ele precisa de frase da Nice (sem ela, sairia o inglês do pacote).
    "inform_limitation.offer_team": "CONCIERGE_ENGINE_OFFER_TEAM",
    # Os degraus de baixo dos efeitos (#3412): o efeito aconteceu, mas o que se diria depois dele não se leu.
    # Aprovadas pelo dono em 23/11 ("Pronto, a sacola foi atualizada." e "Pedido {order} registrado.
    # Acompanhar: {track}"); a do recebimento derivada das aprovadas, acatada por ele.
    "change_cart.done_receipt": "CONCIERGE_ENGINE_CART_UPDATED_SHORT",
    # A mudança com uma pergunta do fechamento no ar (#3488): decidida pela coordenação em 24/11 (a aprovada
    # acima, com o total novo).
    "change_cart.done_total": "CONCIERGE_ENGINE_CART_UPDATED_TOTAL",
    "set_fulfillment.updated": "CONCIERGE_ENGINE_FULFILLMENT_UPDATED",
    "commit_order.done_order": "CONCIERGE_ENGINE_ORDER_PLACED_SHORT",
    # As esperas (#3328), aprovadas em 23/11 ("decidido, pode reverter"): o efeito ainda em andamento (o pedido
    # também: o ``commit_order`` pendente responde pelo ``effect.pending``) e o aviso de prazo vencido
    # (``Engine.tick``), com prazo novo ou sem ele.
    "effect.pending": "CONCIERGE_ENGINE_EFFECT_PENDING",
    "wait.overdue": "CONCIERGE_ENGINE_WAIT_OVERDUE",
    "wait.overdue_no_deadline": "CONCIERGE_ENGINE_WAIT_OVERDUE_NO_DEADLINE",
}

#: As frases da forma de pagamento: as MESMAS de hoje, com o espaço do motor (``{payment_method}``, as
#: opções do canal) no lugar de ``{options}``. A pergunta (``CONCIERGE_CLOSE_ASK_PAYMENT``) e a forma que
#: o canal não oferece (``CONCIERGE_CLOSE_NO_CASH``): a conversa oferece as formas do canal sem dinheiro
#: (``conversation_payment_methods``, D-003), e o leitor só lê pix, cartão e dinheiro (``model_reader.PAYMENTS``),
#: por isso a forma não oferecida que chega ao motor é o dinheiro.
PAYMENT_TEMPLATES = (
    ("present_terms.needs_payment_method", "CONCIERGE_CLOSE_ASK_PAYMENT", "{options}", "{payment_method}"),
    ("set_payment.not_offered", "CONCIERGE_CLOSE_NO_CASH", "{options}", "{payment_method}"),
    # O horário da retirada (#3482): a pergunta de hoje, com os horários do dia no lugar de ``{options}``.
    ("present_terms.needs_delivery_time_slot", "CONCIERGE_CLOSE_ASK_SLOT", "{options}", "{delivery_time_slot}"),
)

#: Os moldes do pedido com a frase de hoje (prévia de 22/11, "Igual"; passo 4 do pedido pelo motor).
#: O recebimento é o MESMO "Combinado" do caminho de hoje (``CONCIERGE_CART_FULFILLMENT_NOTED``,
#: ``order_closing.noted``), com os espaços do motor no lugar de ``{how}`` e ``{when}``.
FULFILLMENT_TEMPLATES = {
    "set_fulfillment.done": ("{mode}", "{date}, {window}"),
    "set_fulfillment.done_day": ("{mode}", "{date}"),
    # Derivada das aprovadas (coordenação, 23/11): a hora sem janela da grade.
    "set_fulfillment.done_time": ("{mode}", "{date} às {time}"),
    "set_fulfillment.done_date": ("para", "{date}"),
    "set_fulfillment.done_mode": ("{mode}", ""),
}
FULFILLMENT_COPY = "CONCIERGE_CART_FULFILLMENT_NOTED"

#: Quem atende, dito ao cliente. O dono do compromisso é um papel interno ("operator_on_duty",
#: a fila): o cliente lê só que pediu a alguém da equipe, nunca o nome do papel.
OWNER_TEXT = "alguém da equipe"


def owner_text(value) -> str:
    return OWNER_TEXT


def deadline_text(value) -> str:
    """O prazo em hora local, como a casa fala: "hoje às 15h", "amanhã às 7h10", "24/11 às 9h"."""
    from datetime import UTC, datetime, timedelta

    from django.utils import timezone

    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment, UTC)
    local = timezone.localtime(moment)
    today = timezone.localdate()
    day = {today: "hoje", today + timedelta(days=1): "amanhã"}.get(local.date()) or local.strftime("%d/%m")
    from shopman.utils.formatting import format_clock

    return f"{day} às {format_clock(local)}"


def date_text(value) -> str:
    """O dia do recebimento como no "Combinado" de hoje: "hoje", "amanhã", "24/11"."""
    from datetime import date

    from .order_closing import day_word

    return day_word(date.fromisoformat(str(value)))


def mode_text(value) -> str:
    from .order_closing import mode_word

    return mode_word(str(value))


def window_text(value) -> str:
    """A janela pela grade da casa ("slot-15" → "a partir das 15h"); ref que a grade não conhece não vaza."""
    from shopman.shop.services.fulfillment_window import window_label

    from .order_closing import window_phrase

    return window_phrase(window_label(str(value), for_customer=True))


def time_text(value) -> str:
    """ "16:00" → "16h", "16:30" → "16h30": a hora como a casa diz (``format_clock``)."""
    from shopman.utils.formatting import format_clock

    return format_clock(str(value))


def money_text(value) -> str:
    """ "R$ 24,00": o dinheiro como a casa escreve (o neutro do pacote é "BRL 24.00")."""
    from collections.abc import Mapping

    from shopman.utils.monetary import format_money

    # O valor do fato chega como ``FrozenMap`` (um ``Mapping``, não um ``dict``).
    if not isinstance(value, Mapping) or "price_minor" not in value:
        raise ValueError("valor sem price_minor")
    return f"R$ {format_money(int(value['price_minor']))}"


def track_text(value) -> str:
    """Onde acompanhar o pedido: a página dele no site, determinística a partir do número (nenhum fato novo)."""
    from .tools import _storefront_base_url

    return f"{_storefront_base_url()}/pedido/{value}/"


def method_text(value) -> str:
    """A forma escolhida como a casa a escreve: "Pix", "Cartão (link seguro)"."""
    from .tools import PAYMENT_LABELS

    if str(value) not in PAYMENT_LABELS:
        raise ValueError("forma de pagamento que a casa não conhece")
    return PAYMENT_LABELS[str(value)]


def payment_options_text(value) -> str:
    """As formas do canal para a pergunta: "Pix ou Cartão (link seguro)".

    Sem os números do fechamento de hoje ("1) Pix; 2) …"): pelo motor, o "1" não é lido como a
    primeira opção (o leitor não vê a pergunta), e lista numerada que não se responde por número
    seria promessa falsa.
    """
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("opções sem lista")
    labels = [method_text(option) for option in value]
    return labels[0] if len(labels) == 1 else f"{', '.join(labels[:-1])} ou {labels[-1]}"


def done_text(value) -> str:
    """O recibo de sucesso dito como a casa diz: "Pronto"."""
    return "Pronto" if str(value) == "success" else str(value)


def noted_text(value) -> str:
    """O recebimento anotado, dito como a casa diz o "Combinado" do recebimento."""
    return "Combinado" if str(value) == "success" else str(value)


def items_text(value) -> str:
    """As linhas da sacola como hoje (``tools.render_result``): "2 × “Croissant”: R$ 24,00"."""
    from decimal import Decimal

    from .tools import _display_name

    rows = []
    for line in value:
        quantity = Decimal(str(line["quantity"]))
        shown = int(quantity) if quantity == quantity.to_integral_value() else quantity
        rows.append(f"{shown} × {_display_name(line.get('name') or line['ref'])}: {money_text(line['line_total'])}")
    return "\n".join(rows)


def fulfillment_text(value) -> str:
    """O começo da linha do recebimento: "Retirada" ou "Entrega" (o dia e a janela vêm das condições)."""
    from collections.abc import Mapping

    mode = value.get("mode") if isinstance(value, Mapping) else None
    return {"pickup": "Retirada", "delivery": "Entrega"}.get(str(mode), "")


def _no_address(ref) -> dict:
    """Sem conversa, nenhuma referência de endereço se resolve (o motor segura a mensagem)."""
    from conversational_commerce.reply import UnresolvedReference

    raise UnresolvedReference(str(ref))


def address_resolver(conversation):
    """O endereço da entrega pela referência, SÓ o da sacola desta conversa (spec 06, formatador de referência).

    Devolve o endereço estruturado gravado na sacola; outra referência, sacola sem endereço ou leitura
    que falha levantam ``UnresolvedReference``, e a verificação segura a mensagem. O texto existe só aqui,
    no envio.
    """
    from conversational_commerce.reply import UnresolvedReference

    def resolve(ref) -> dict:
        from shopman.orderman.models import Session

        from shopman.shop.conversational.commerce_read import address_ref

        key = getattr(conversation, "session_key", "") or ""
        if not key or not str(ref).startswith(f"address:{key}:"):
            raise UnresolvedReference(str(ref))
        try:
            session = Session.objects.filter(session_key=key).first()
        except Exception as exc:  # noqa: BLE001 - a fonte que falha segura a mensagem
            raise UnresolvedReference(str(ref)) from exc
        data = (session.data if session is not None else None) or {}
        if str(ref) != address_ref(key, data):
            raise UnresolvedReference(str(ref))  # o endereço mudou desde a referência: nunca diz o novo no lugar
        structured = data.get("delivery_address_structured")
        if not isinstance(structured, dict) or not data.get("delivery_address"):
            raise UnresolvedReference(str(ref))
        return {**structured, "formatted_address": str(data["delivery_address"])}

    return resolve


def address_text(resolve):
    """ "Rua das Flores, 120": a rua e o número, como o cliente reconhece o endereço que deu."""
    def text(value) -> str:
        from .tools import _display_text

        found = resolve(value)
        street = ", ".join(part for part in (str(found.get("route") or ""), str(found.get("street_number") or ""))
                           if part)
        return _display_text(street or found["formatted_address"])

    return text


def conditions_text(value, resolve=_no_address) -> str:
    """O resto do recebimento e o pagamento, como no resumo de hoje.

    ": segunda-feira, 23/11, a partir das 15h" (o dia e a janela da grade da casa); na entrega, o
    endereço e a taxa em linhas próprias; e "Pagamento: Pix.". Sem dia, sem o dia.
    """
    from shopman.shop.services.fulfillment_window import window_label

    from .tools import PAYMENT_LABELS, _summary_when

    found = dict(value or {})
    text = ""
    if found.get("fulfillment_date"):
        slot = found.get("fulfillment_window")
        label = window_label(str(slot), for_customer=True) if slot else ""
        text = f": {_summary_when(str(found['fulfillment_date']), label)}"
    if found.get("delivery_address"):
        from .tools import _display_text

        text += f"\n{_display_text(resolve(found['delivery_address'])['formatted_address'])}"
    if found.get("delivery_fee"):
        text += f"\nEntrega: {money_text({'price_minor': int(found['delivery_fee'])})}"
    method = PAYMENT_LABELS.get(str(found.get("payment_method") or ""), "")
    if method:
        text += f"\nPagamento: {method}."
    return text


def nice_formatters(conversation=None) -> dict:
    """Os formatadores da Nice. Com a conversa, os de referência resolvem o endereço DELA (e só dela)."""
    from functools import partial

    from conversational_commerce.engine.format import DEFAULT_FORMATTERS

    money = dict.fromkeys(("price", "price_a", "price_b", "total"), money_text)  # o dinheiro do pacote, em reais
    return {**DEFAULT_FORMATTERS, **money, "track": track_text, "done": done_text, "noted": noted_text,
            "items": items_text,
            "fulfillment": fulfillment_text, "conditions": conditions_text, "owner": owner_text,
            "deadline": deadline_text,
            "date": date_text,
            "mode": mode_text, "window": window_text, "time": time_text,
            "method": method_text, "payment_method": payment_options_text,
            "delivery_address_details": address_words_text, "delivery_time_slot": pickup_slots_text(conversation),
            "delivery_window": delivery_windows_text(conversation),
            **_address_formatters(conversation, partial)}


def _options_text(labels: list[str]) -> str:
    """Os rótulos da grade numa frase: "a partir das 9h, a partir das 12h ou a partir das 15h". Dentro da frase a
    primeira letra é minúscula (regra do dono: maiúscula só em valor isolado); o rótulo da grade e o site não mudam."""
    lowered = [label[:1].lower() + label[1:] for label in labels]
    return lowered[0] if len(lowered) == 1 else f"{', '.join(lowered[:-1])} ou {lowered[-1]}"


def delivery_windows_text(conversation):
    """As janelas de entrega do dia, as mesmas da loja on-line (``annotate_delivery_windows_for_checkout``), sem
    números. Sem janela que sirva, segura (``UnresolvedReference``) e o caminho de hoje responde."""
    def text(value) -> str:
        from collections.abc import Mapping

        from conversational_commerce.reply import UnresolvedReference
        from shopman.orderman.models import Session

        from shopman.storefront.services.pickup_slots import annotate_delivery_windows_for_checkout

        if isinstance(value, (list, tuple)):
            labels = [str(label) for label in value if label]
        else:
            day = str(value.get("date") or "") if isinstance(value, Mapping) else ""
            if not day or conversation is None:
                raise UnresolvedReference("janela sem dia")
            session = Session.objects.filter(session_key=getattr(conversation, "session_key", "") or "").first()
            skus = [str(item.get("sku")) for item in ((session.items if session is not None else None) or [])]
            windows = annotate_delivery_windows_for_checkout(skus, delivery_date=day,
                                                             channel_ref=conversation.channel_ref).get("windows") or []
            labels = [str(w.get("label")) for w in windows if w.get("enabled") and w.get("label")]
        if not labels:
            raise UnresolvedReference("nenhuma janela no dia")
        return _options_text(labels)

    return text


def pickup_slots_text(conversation):
    """Os horários de retirada do dia, como a pergunta de hoje os oferece: os da grade anotada do checkout que
    a sacola ainda alcança, sem números ("9h às 12h ou 15h às 18h"; o "1" não se lê como a primeira opção).

    Sem horário que sirva, levanta ``UnresolvedReference``: a mensagem segura e o caminho de hoje diz que não há
    horário no dia. A lista já pronta (o fato do ensaio, de memória) se diz como veio.
    """
    def text(value) -> str:
        from collections.abc import Mapping

        from conversational_commerce.reply import UnresolvedReference
        from shopman.orderman.models import Session

        from shopman.storefront.services.pickup_slots import annotate_slots_for_checkout

        if isinstance(value, (list, tuple)):
            labels = [str(label) for label in value if label]
        else:
            day = str(value.get("date") or "") if isinstance(value, Mapping) else ""
            if not day or conversation is None:
                raise UnresolvedReference("horário sem dia")
            session = Session.objects.filter(session_key=getattr(conversation, "session_key", "") or "").first()
            skus = [str(item.get("sku")) for item in ((session.items if session is not None else None) or [])]
            annotated = annotate_slots_for_checkout(skus, delivery_date=day, channel_ref=conversation.channel_ref)
            labels = [str(slot.get("label")) for slot in annotated.get("pickup_slots", [])
                      if slot.get("enabled") and slot.get("label")]
        if not labels:
            raise UnresolvedReference("nenhum horário no dia")
        return _options_text(labels)

    return text


def address_words_text(value) -> str:
    """ "o número (ou S/N) e o CEP": o que falta no endereço, como a pergunta de hoje (``address.question``)."""
    from shopman.shop.services.delivery_fiscal_identity import join_words

    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("lacunas sem lista")
    return join_words([str(word) for word in value])


def _address_formatters(conversation, partial) -> dict:
    resolve = address_resolver(conversation) if conversation is not None else _no_address
    return {"address": address_text(resolve), "conditions": partial(conditions_text, resolve=resolve),
            "delivery_address_saved": saved_address_text(conversation),
            "delivery_address_saved_options": saved_addresses_text(conversation)}


def _saved_of(conversation, ref: str):
    """O endereço do cadastro pela referência opaca: só o desta conversa (a referência presa à sacola dela, o
    cadastro do cliente dela) e só se ainda é o que a referência resume. Qualquer outra coisa levanta
    ``UnresolvedReference``, e a mensagem segura (spec 06)."""
    from conversational_commerce.reply import UnresolvedReference

    from shopman.shop.conversational.commerce_read import parse_saved_address_ref, saved_address_digest

    from .address import saved_addresses, short_line

    key = getattr(conversation, "session_key", "") or ""
    parsed = parse_saved_address_ref(ref, key) if conversation is not None else None
    if parsed is None:
        raise UnresolvedReference(ref)
    chosen = next((saved for saved in saved_addresses(conversation.customer_ref or "")
                   if str(saved.pk) == parsed[0]), None)
    if chosen is not None and saved_address_digest(key, chosen) != parsed[1]:
        chosen = None  # o endereço mudou: nunca se diz outro no lugar
    if chosen is None or not short_line(chosen):
        raise UnresolvedReference(ref)
    return chosen


def saved_address_text(conversation):
    """O endereço do cadastro que a oferta diz ("Rua X, 120 - Centro"), pela referência opaca da primeira opção.
    O texto existe só no envio."""
    def text(value) -> str:
        from .address import short_line

        options = list(value) if isinstance(value, (list, tuple)) else [value]
        return short_line(_saved_of(conversation, str(options[0]) if options else ""))

    return text


def saved_addresses_text(conversation):
    """Todos os endereços do cadastro que o fato oferece, como a lista de hoje (``address.saved_listing``): a
    etiqueta (se houver) e a rua, separados por ponto e vírgula. Um que não se resolve segura a mensagem inteira."""
    def text(value) -> str:
        from .address import saved_tag, short_line

        options = list(value) if isinstance(value, (list, tuple)) else [value]
        rows = []
        for ref in options:
            saved = _saved_of(conversation, str(ref))
            rows.append(f"{saved_tag(saved)}: {short_line(saved)}" if saved_tag(saved) else short_line(saved))
        if not rows:
            from conversational_commerce.reply import UnresolvedReference

            raise UnresolvedReference("")
        return "; ".join(rows)

    return text

ENVIRONMENT = "live"


def live_classes() -> frozenset[str]:
    """As classes de ação ligadas na loja. Sem loja, nenhuma."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    if shop is None:
        return frozenset()
    return frozenset(name for name, field in SWITCH_FIELD.items() if getattr(shop, field, False))


def nice_templates() -> dict[str, Template]:
    """Os moldes da Nice, com a frase da copy de hoje. A copy que não vira molde válido fica fora."""
    from .service import copy_message

    package = templates()
    found: dict[str, Template] = {}
    for template_id, key in NICE_TEMPLATE_COPY.items():
        base = package[template_id]
        text = (copy_message(key) or "").strip()
        try:
            found[template_id] = Template(template_id, f"nice:{key}", base.move, text, dict(base.slots))
        except ValueError:
            logger.warning("concierge.turn_framework.template_refused template=%s key=%s", template_id, key)
    found.update(_order_templates(package, copy_message))
    for template_id, key, today_slot, slot in PAYMENT_TEMPLATES:
        text = (copy_message(key) or "").strip()
        if today_slot not in text:
            continue
        try:
            base = package[template_id]
            found[template_id] = Template(template_id, f"nice:{key}", base.move, text.replace(today_slot, slot),
                                          dict(base.slots))
        except (KeyError, ValueError):
            logger.warning("concierge.turn_framework.template_refused template=%s key=%s", template_id, key)
    return found


def _order_templates(package, copy_message) -> dict[str, Template]:
    """Os moldes do pedido com a frase de hoje. Copy que não vira molde válido fica fora (e o turno, no caminho de hoje).

    O molde da casa tem os MESMOS espaços do pacote (``Engine.__post_init__``). Por isso o "total
    mudou" de hoje, que não diz o total, não vira molde: o do pacote mostra ``{total}``.
    """
    import re

    found: dict[str, Template] = {}
    noted = (copy_message(FULFILLMENT_COPY) or "").strip()
    for template_id, (how, when) in FULFILLMENT_TEMPLATES.items():
        base = package.get(template_id)
        text = re.sub(r"\s+([.,])", r"\1", noted.replace("{how}", how).replace("{when}", when)).strip()
        if base is None or "{how}" not in noted or "{when}" not in noted:
            continue
        try:
            found[template_id] = Template(template_id, f"nice:{FULFILLMENT_COPY}", base.move, text, dict(base.slots))
        except ValueError:
            logger.warning("concierge.turn_framework.template_refused template=%s key=%s", template_id, FULFILLMENT_COPY)
    return found


class NiceRules:
    """As regras locais da Nice no lugar das de teste do pacote (que são em inglês).

    O motor lê a mensagem por estas regras só no portão (cortesia sozinha não chama o leitor) e
    na queda (teto de chamadas, leitor fora). É a MESMA leitura por regra do caminho de hoje
    (``intents.local_acts``), no vocabulário fechado do framework (``ports.ACT_MAP``). Só dá
    o nome do ato: produto, quantidade e dia vêm do leitor da Nice (``model_reader.NiceReader``).
    """

    def read(self, text: str) -> tuple[str, ...]:
        from .intents import local_acts
        from .ports import ACT_MAP

        found = tuple(dict.fromkeys(ACT_MAP.get(act.act, "unknown") for act in local_acts(text or "")))
        return tuple(act for act in found if act != "unknown")

    def risk_acts(self, text: str) -> tuple[str, ...]:
        return tuple(act for act in self.read(text) if act == "complain")


def subject_for(conversation):
    """O sujeito do turno: a conversa, com a sacola dela. Identidade nunca acima do transporte."""
    from .ports import new_cart_ref, subject_of

    def subject(ctx: TrustedContext, event) -> Subject:
        # Sem sacola ainda, o alvo é a sacola nova da conversa: o primeiro pedido pelo motor tem
        # onde cair, e ela só nasce no efeito (nunca na leitura nem na sombra).
        return Subject(subject_ref=subject_of(conversation.pk), identity_evidence=tuple(event.identity_evidence),
                       cart_ref=conversation.session_key or new_cart_ref(conversation.pk))

    return subject


def build_engine(conversation, *, environment: str = ENVIRONMENT, channel=None) -> Engine | None:
    """O motor com as portas e os livros duráveis do Shopman para esta conversa, ou ``None``."""
    from shopman.shop.conversational.clock import ShopmanClock
    from shopman.shop.conversational.commerce_execute import ShopmanCommerceExecute
    from shopman.shop.conversational.commerce_read import ShopmanCommerceRead
    from shopman.shop.conversational.ledgers import (
        commitment_ledger,
        exposure_ledger,
        memory_store,
        receipt_ledger,
    )
    from shopman.shop.conversational.outcomes import ShopmanOutcomes
    from shopman.shop.conversational.store import ShopmanStore

    from .effect_site import ConciergeEffectSite
    from .model_reader import NiceReader
    from .ports import ConversationOwnership, nice_channel, resolve_text, subject_of
    from .profile import build_profile
    from .staff_port import NiceStaff
    from .tools import ToolContext

    channel = channel or nice_channel()
    if channel is None:
        return None
    profile = build_profile(environment=environment)
    ctx = TrustedContext(tenant=profile.tenant, environment=environment, subject=subject_of(conversation.pk))
    bodies: dict[str, str] = {}
    channel = replace(channel, bodies=bodies, handoffs=[])
    channel_ref = conversation.channel_ref or "whatsapp"
    ports = Ports(
        channel=channel, model=NiceReader(),
        commerce_read=ShopmanCommerceRead(channel_ref=channel_ref, ownership=ConversationOwnership()),
        commerce_execute=ShopmanCommerceExecute(site=ConciergeEffectSite(
            ToolContext(conversation=conversation, channel_ref=channel_ref))),
        staff=NiceStaff(), store=ShopmanStore(), clock=ShopmanClock(ctx), outcomes=ShopmanOutcomes())
    return Engine(ports, profile, rules=NiceRules(), resolve_content=resolve_text, subject_of=subject_for(conversation),
                  house_templates=nice_templates(), house_voice_only=True, bodies=bodies,
                  formatters=nice_formatters(conversation),
                  ledger=receipt_ledger(ctx), commitments=commitment_ledger(ctx),
                  memory=memory_store(ctx, subject_of(conversation.pk)), exposures=exposure_ledger(ctx))


@dataclass(frozen=True)
class Verdict:
    """O que a sombra disse: se o turno pode sair pelo motor, e por quê não, quando não."""

    eligible: bool
    reason: str = ""
    moves: tuple[str, ...] = ()
    template_ids: tuple[str | None, ...] = ()


#: O que a sombra não consegue preencher na parte de um efeito que ela não executa (``shadow:effect_not_executed``):
#: o recibo que não existe, o "feito" sem recibo e o fato lido depois do efeito. Só isso se tolera, e só na
#: parte do próprio efeito; o resto segura como sempre.
SHADOW_EFFECT_GAPS = frozenset({"receipt_not_in_evidence", "action_without_receipt", "fact_not_in_evidence"})
#: A recusa no ponto de efeito refaz a decisão, e quem responde é a limitação comum.
REFUSAL_TEMPLATE = "inform_limitation.offer_team"


#: Os moldes aprovados que só valem em parte dos casos em que o motor os usa. Fora deles, o turno vai pelo
#: caminho de hoje, que responde certo (calibragem do básico, 23/11). Sem frase nova: só quem responde.
#:
#: - ``acknowledge.thanks`` é o agradecimento de hoje ("Nós que agradecemos!"). O motor o usa também para o
#:   cumprimento; "oi" respondido com "Nós que agradecemos" é falso. O cumprimento de hoje (``small_talk``)
#:   devolve o "Bom dia" e se apresenta. Só o cumprimento: o "sim" e o "não" se julgam na sombra sem a
#:   pergunta do turno vivo, e lá viram agradecimento mesmo quando, ao vivo, respondem aos termos.
THANKS_TEMPLATE = "acknowledge.thanks"
GREETING_ACT = "greet"
#: - ``inform_limitation.offer_team`` pergunta "Quer que eu chame alguém da equipe?", e o "sim" a ela não
#:   chama ninguém pelo motor (o "sim" não se liga à oferta): a frase promete o que o turno seguinte não faz.
#:   O caminho de hoje diz o que falta (o produto que não tem, a sacola vazia) e chama a equipe de verdade.
#: - ``ask_clarification.more`` diz "não entendi bem" a falas que o caminho de hoje responde: a pergunta
#:   da casa (endereço, Wi-Fi, horário de entrega), "quanto deu?" e "vou pagar".
TODAY_ANSWERS = frozenset({"inform_limitation.offer_team", "ask_clarification.more"})


def today_answers_better(result, template_ids) -> str:
    """O molde aprovado que, neste turno, diria algo falso ou inútil; vazio quando não há."""
    found = sorted(str(t) for t in template_ids if t in TODAY_ANSWERS)
    if found:
        return found[0]
    understanding = getattr(result, "understanding", None)
    acts = {act.act for act in (understanding.acts if understanding is not None else ())}
    if THANKS_TEMPLATE in template_ids and GREETING_ACT in acts:
        return THANKS_TEMPLATE
    return ""


def effect_outcomes(move: str) -> frozenset[str]:
    """Os moldes de todos os desfechos do efeito: o sucesso, os degraus, a falha e as recusas próprias."""
    from conversational_commerce.engine.moves import registry

    module = registry().get(move)
    if module is None or not getattr(module, "EFFECT", False):
        return frozenset()
    return frozenset({template.template_id for template in module.TEMPLATES} | {REFUSAL_TEMPLATE})


def judge(result, *, enabled: frozenset[str], approved: frozenset[str]) -> Verdict:
    """O turno em sombra pode ir ao vivo? Classe ligada para cada movimento, molde da Nice para cada parte.

    O turno com efeito se julga pelos MOLDES (#3410): a sombra não executa o efeito, e a parte dele sai
    sem o recibo. Pode ir ao vivo se cada desfecho possível do efeito tem frase da Nice e se o que falta
    na sombra é só o que ela não pode ter (``SHADOW_EFFECT_GAPS``, na parte do efeito). No ar, o porteiro
    de voz (``house_voice_only``) segura o que sair fora disso.
    """
    moves = tuple(result.chosen_moves)
    reply = getattr(result, "reply", None)
    template_ids = tuple(reply.template_ids) if reply is not None else ()
    if not moves or reply is None:
        return Verdict(False, "no_reply", moves, template_ids)
    off = sorted({move for move in moves if CLASS_OF_MOVE.get(move) not in enabled})
    if off:
        return Verdict(False, f"class_off:{','.join(off)}", moves, template_ids)
    better = today_answers_better(result, template_ids)
    if better:
        return Verdict(False, f"today_answers:{better}", moves, template_ids)
    effects = sorted({move for move in moves if effect_outcomes(move)})
    needed = set(template_ids).union(*(effect_outcomes(move) for move in effects))
    missing = sorted({str(t) for t in needed if t not in approved})
    if missing:
        return Verdict(False, f"no_nice_template:{','.join(missing)}", moves, template_ids)
    if reply.text:
        return Verdict(True, "", moves, template_ids)
    if not effects:
        return Verdict(False, "no_reply", moves, template_ids)
    parts = list(reply.verification.parts)
    blocking = sorted({f.code for f in reply.verification.findings
                       if f.code not in SHADOW_EFFECT_GAPS or f.part is None or f.part >= len(parts)
                       or parts[f.part].move not in effects})
    if blocking:
        return Verdict(False, f"held:{','.join(blocking)}", moves, template_ids)
    return Verdict(True, "", moves, template_ids)



#: O recuo da casa depois de um efeito feito cuja resposta segurou: diz só o que o recibo sustenta (foi
#: anotado) e promete a confirmação, que a equipe cumpre pelo cartão (``EFFECT_HELD_ALERT``).
EFFECT_HELD_COPY = "CONCIERGE_ENGINE_EFFECT_HELD"
EFFECT_HELD_ALERT = "concierge_effect_unconfirmed"
#: O prazo da promessa "já te confirmo": o cartão conta até ele no sino do Gestor.
EFFECT_HELD_MINUTES = 10


def send_voiced_parts(conversation, result, voice: frozenset[str]) -> bool:
    """Rede de segurança: depois do efeito, a parte cujo molde não tem frase da Nice CAI, e o resto sai.

    Só quando o único achado é esse (``template_not_in_voice``) e há parte com voz. Qualquer outro achado
    (referência que não resolve, número sem lastro) segura a mensagem inteira, e quem responde é o recuo.
    """
    from . import house_rules, service

    reply = getattr(result, "reply", None)
    findings = list(reply.verification.findings) if reply is not None else []
    if not findings or any(f.code != "template_not_in_voice" for f in findings):
        return False
    voiced = [part for part in reply.verification.parts if part.template_id in voice]
    if not voiced:
        return False
    actions = {command.action for command in result.commands}
    receipts = frozenset({house_rules.ORDER} if "commit_order" in actions else {house_rules.CART})
    decision = getattr(result.decision, "decision_id", "") or ""
    logger.warning("concierge.turn_framework.voiced_parts conversation=%s dropped=%s", conversation.pk,
                   [part.template_id for part in reply.verification.parts if part.template_id not in voice])
    sent = service.send_out_of_turn(conversation, "\n\n".join(part.text for part in voiced), receipts=receipts,
                                    send_key=f"voiced:{decision}")
    return sent is not None


def send_house_extras(conversation, result, engine) -> None:
    """As mensagens que a casa monta ao lado do efeito, como no caminho de hoje (``ToolContext.extra_replies``).

    O pedido com Pix: o ``place_order`` põe o copia-e-cola numa mensagem SEPARADA, para o cliente copiar sem
    ruído (``tools._placed_result``). Pelo motor, quem chama o ``place_order`` é o sítio, com o contexto dele, e
    a resposta do motor é só o texto do molde; sem isto, o Pix ficava no contexto e o cliente nunca o recebia.
    Saem depois da resposta, pelo envio de hoje, uma chave por mensagem (o reenvio nunca duplica).
    """
    from . import house_rules, service

    site = getattr(getattr(engine.ports, "commerce_execute", None), "site", None)
    extras = [str(text) for text in getattr(getattr(site, "tool_context", None), "extra_replies", None) or []
              if str(text or "").strip()]
    decision = getattr(result.decision, "decision_id", "") or ""
    for index, text in enumerate(extras):
        sent = service.send_out_of_turn(conversation, text, receipts=frozenset({house_rules.ORDER}),
                                        send_key=f"extra:{decision}:{index}")
        if sent is None:
            logger.warning("concierge.turn_framework.extra_unsent conversation=%s index=%s", conversation.pk, index)


def answer_after_effect(conversation, result) -> None:
    """Efeito feito e resposta segurada: o cliente ouve o recuo, e a equipe recebe o cartão com prazo."""
    from datetime import timedelta

    from django.utils import timezone

    from shopman.shop.services.observability import create_operator_alert

    from . import house_rules, service

    actions = sorted({command.action for command in result.commands})
    decision = getattr(result.decision, "decision_id", "") or ""
    text = (service.copy_message(EFFECT_HELD_COPY) or "").strip()
    sent = None
    if text:
        receipts = frozenset({house_rules.ORDER} if "commit_order" in actions else {house_rules.CART})
        sent = service.send_out_of_turn(conversation, text, receipts=receipts, send_key=f"held:{decision}")
    create_operator_alert(
        type=EFFECT_HELD_ALERT, severity="warning",
        message=(f"A Concierge fez {', '.join(actions)} e não conseguiu confirmar ao cliente. "
                 "Confirme os detalhes por aqui."),
        stamp_dedupe=False, order_ref=getattr(conversation, "last_order_ref", "") or "",
        conversation_id=conversation.pk, owner_role="atendimento",
        respond_by=timezone.now() + timedelta(minutes=EFFECT_HELD_MINUTES),
    )
    if sent is None:
        logger.warning("concierge.turn_framework.held_after_effect_unsent conversation=%s", conversation.pk)


def _findings(result) -> list[str]:
    reply = getattr(result, "reply", None)
    return [f.code for f in reply.verification.findings] if reply is not None else []


def _raw(message) -> dict:
    return {**(message.envelope or {}), "message_ref": message.pk}


def run(conversation, message, *, channel=None, interrupted=None):
    """O turno pelo motor, ou ``None`` (o caminho de hoje segue). Nunca levanta.

    Só conta como feito o turno que o motor respondeu E enviou (``answered`` com exposição).
    Segurado, revogado (``interrupted``: a conversa mudou de dono no meio) ou com o envio
    falhado, nada chegou ao cliente pelo motor, e o caminho de hoje responde.
    """
    try:
        enabled = live_classes()
        if not enabled:
            return None
        shadow = build_engine(conversation, environment="shadow", channel=channel)
        if shadow is None:
            return None
        rehearsal = shadow.turn(TrustedContext(tenant=shadow.profile.tenant, environment="shadow",
                                               subject=shadow.ports.clock.ctx.subject), _raw(message))
        verdict = judge(rehearsal, enabled=enabled, approved=frozenset(shadow.house_templates))
        if not verdict.eligible:
            logger.info("concierge.turn_framework.legacy conversation=%s reason=%s", conversation.pk, verdict.reason)
            return None
        live = build_engine(conversation, environment=ENVIRONMENT, channel=channel)
        if live is None:
            return None
        result = live.turn(live.ports.clock.ctx, _raw(message), interrupted=interrupted)
        if result.outcome != "answered" or getattr(result, "exposure", None) is None:
            if any(receipt.status == "success" for receipt in result.receipts):
                # O efeito aconteceu e a mensagem segurou (o porteiro de voz, uma referência que não resolve, o
                # verificador que segura). O caminho de hoje NÃO responde, porque refaria o que já foi feito; e nunca
                # termina em silêncio: o recuo da casa, lastreado só no recibo, e um cartão para a equipe cumprir.
                logger.warning("concierge.turn_framework.held_after_effect conversation=%s outcome=%s findings=%s",
                               conversation.pk, result.outcome, _findings(result))
                if not send_voiced_parts(conversation, result, frozenset(live.house_templates)):
                    answer_after_effect(conversation, result)
                send_house_extras(conversation, result, live)
                return result
            logger.info("concierge.turn_framework.not_sent conversation=%s outcome=%s fallbacks=%s",
                        conversation.pk, result.outcome, list(result.fallbacks))
            return None
        send_house_extras(conversation, result, live)
        handoffs = list(getattr(live.ports.channel, "handoffs", None) or [])
        if handoffs:
            # A resposta ("Solicitei atendimento a alguém da equipe…") já saiu; o serviço entrega a conversa à
            # equipe ao fechar o turno (``service.run_turn``), pelo caminho de hoje, uma vez só.
            conversation._framework_handoff = handoffs[0]
        return result
    except Exception:  # noqa: BLE001 — o motor que cai nunca derruba o turno: segue o caminho de hoje
        logger.warning("concierge.turn_framework.failed conversation=%s", getattr(conversation, "pk", None),
                       exc_info=True)
        return None


#: O aviso de prazo vencido sai pelos moldes ``wait.*`` (``Engine.tick``, ``only=("wait",)``).
TICK_MOVE = "wait"


def tick_templates_missing() -> tuple[str, ...]:
    """Os moldes do aviso de prazo sem frase da Nice. Enquanto houver um, o tick não fala."""
    approved = set(NICE_TEMPLATE_COPY)
    return tuple(sorted(t.template_id for t in templates().values()
                        if t.move == TICK_MOVE and t.template_id not in approved))


def _due_conversations(ctx: TrustedContext) -> list[int]:
    """As conversas com compromisso do motor aberto e vencido, no inquilino e ambiente do turno vivo."""
    from conversational_commerce.contracts import Commitment
    from django.utils import timezone

    from shopman.shop.conversational.store import _scope, instant
    from shopman.shop.models import Conversation, ConversationalCommitment, ConversationalEpisode


    now = instant(timezone.now())
    episodes = set()
    for row in ConversationalCommitment.objects.filter(**_scope(ctx), is_open=True).exclude(episode_id=""):
        deadline = getattr(Commitment.from_document(row.commitment).deadline, "at", None)
        if deadline and str(deadline) <= now:
            episodes.add(row.episode_id)
    subjects = set(ConversationalEpisode.objects.filter(**_scope(ctx), episode_id__in=episodes)
                   .values_list("subject", flat=True))
    pks = sorted({pk for subject in subjects for pk in _conversations_of_subject(subject)})
    # A frase do encaminhamento promete "te aviso por aqui até {deadline}": com a conversa na equipe e NINGUÉM
    # tendo assumido, o aviso sai (a Nice nunca afirma falso). Se alguém da equipe assumiu, o tick cala.
    found = Conversation.objects.filter(pk__in=pks, state__in=(Conversation.State.ACTIVE, Conversation.State.HANDOFF))
    return [conversation.pk for conversation in found
            if conversation.state == Conversation.State.ACTIVE or not team_took_over(conversation)]


def team_took_over(conversation) -> bool:
    """Alguém da equipe assumiu o atendimento depois do encaminhamento: o cartão de "cliente esperando atendente"
    (``concierge_handoff``) reconhecido ou resolvido por uma pessoa.

    É o único sinal que a casa registra: a resposta pelo Live Chat do provedor não chega aqui. Sem ele, o prazo
    prometido ao cliente vale, e o aviso sai."""
    from shopman.shop.adapters import alert as alert_adapter

    pk = ((conversation.flags or {}).get("alerts") or {}).get("concierge_handoff")
    return bool(pk) and alert_adapter.handled_since(int(pk), conversation.handoff_at)


def _conversations_of_subject(subject: str) -> set[int]:
    """As conversas do sujeito do episódio: ``binding:<canal>:<assinante>`` (o vínculo de transporte, como o
    motor o chave, ``workflow.correlation.subject_key``), ou ``conversation:<pk>``."""
    from shopman.shop.models import ConversationBinding

    from .ports import SUBJECT_PREFIX

    if subject.startswith(SUBJECT_PREFIX) and subject[len(SUBJECT_PREFIX):].isdigit():
        return {int(subject[len(SUBJECT_PREFIX):])}
    kind, _, rest = subject.partition(":")
    channel, _, subscriber = rest.partition(":")
    if kind != "binding" or not channel or not subscriber:
        return set()
    return set(ConversationBinding.objects.filter(transport_channel=channel, subject=subscriber)
               .values_list("conversation_id", flat=True))


def _only_this_conversation(engine, conversation) -> None:
    """O livro do motor carrega todo compromisso aberto do inquilino; o tick desta conversa só vê os dela."""
    from shopman.shop.conversational.store import _scope
    from shopman.shop.models import ConversationalEpisode

    from .ports import subject_of

    ctx = engine.ports.clock.ctx
    from shopman.shop.models import ConversationBinding

    subjects = {f"binding:{channel}:{subscriber}" for channel, subscriber in ConversationBinding.objects.filter(
        conversation=conversation).values_list("transport_channel", "subject")} | {subject_of(conversation.pk)}
    mine = set(ConversationalEpisode.objects.filter(**_scope(ctx), subject__in=subjects)
               .values_list("episode_id", flat=True))
    ledger = engine.commitments
    ledger.entries = {cid: entry for cid, entry in ledger.entries.items() if entry.commitment.episode_id in mine}


def tick(*, channel=None) -> dict:
    """Os prazos do motor vencidos, conversa a conversa: avisa o cliente UMA vez (K22), pelo envio de hoje.

    Roda no ``maintenance_worker`` (``concierge_engine_tick``). Não faz nada com as classes
    desligadas, nem enquanto algum molde do aviso (``wait.*``) não tem frase da Nice: aviso em
    frase genérica do pacote nunca sai (condição 1 da decisão de 22/11/2026). Cada conversa tem
    o próprio motor, com o contexto e o envio dela; a falha numa não derruba as outras.
    """
    from shopman.shop.models import Conversation

    counts = {"conversations": 0, "notices": 0, "failed": 0, "skipped": ""}
    if not live_classes():
        counts["skipped"] = "classes_off"
        return counts
    missing = tick_templates_missing()
    if missing:
        counts["skipped"] = f"no_nice_template:{','.join(missing)}"
        return counts
    from .profile import build_profile

    profile = build_profile(environment=ENVIRONMENT)
    # A busca dos vencidos é do inquilino inteiro: contexto sem sujeito (``subject=""`` o contrato recusa, e o tick
    # caía na primeira vez que podia falar, #3328).
    for pk in _due_conversations(TrustedContext(tenant=profile.tenant, environment=ENVIRONMENT)):
        conversation = Conversation.objects.filter(pk=pk).first()
        if conversation is None:
            continue
        counts["conversations"] += 1
        try:
            engine = build_engine(conversation, environment=ENVIRONMENT, channel=channel)
            if engine is None:
                continue
            _only_this_conversation(engine, conversation)
            results = engine.tick(engine.ports.clock.ctx)
            counts["notices"] += sum(1 for result in results if getattr(result, "reply", None) is not None)
        except Exception:  # noqa: BLE001 — uma conversa que falha não derruba o tick das outras
            counts["failed"] += 1
            logger.warning("concierge.turn_framework.tick_failed conversation=%s", pk, exc_info=True)
    return counts
