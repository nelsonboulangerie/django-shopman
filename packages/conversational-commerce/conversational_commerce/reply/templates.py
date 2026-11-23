"""Moldes: a frase da casa preenchida pelo código. Prova por construção.

Um molde tem texto com espaços ``{nome}`` e, para cada espaço, o lastro que ele
aceita (``fact``, ``fact:factual``, ``receipt:success``, ``commitment``,
``policy``...) e o campo do valor. O texto fixo do molde nunca leva número:
preço, quantidade, horário e prazo só entram por espaço, vindos de fato,
recibo, compromisso ou política (N03). Os valores dos espaços são blocos
travados: o reparo da verificação nunca os altera.

A redação da casa (a voz, a língua) é do perfil e do adaptador. O pacote traz
só moldes genéricos mínimos, para os testes e como exemplo da forma.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

SLOT = re.compile(r"\{([a-z][a-z0-9_]*)\}")
DIGIT = re.compile(r"\d")


@dataclass(frozen=True, slots=True)
class SlotSpec:
    accepts: tuple[str, ...]
    field: str | None = None


@dataclass(frozen=True, slots=True)
class Template:
    template_id: str
    version: str
    move: str
    text: str
    slots: Mapping[str, SlotSpec] = field(default_factory=dict)

    def __post_init__(self) -> None:
        named = SLOT.findall(self.text)
        if sorted(set(named)) != sorted(self.slots):
            raise ValueError(f"{self.template_id}: espaços do texto {sorted(set(named))} ≠ declarados "
                             f"{sorted(self.slots)}")
        literal = SLOT.sub("", self.text)
        if DIGIT.search(literal):
            raise ValueError(f"{self.template_id}: número no texto fixo; preço, prazo e quantidade entram por espaço")
        for name, spec in self.slots.items():
            if not spec.accepts:
                raise ValueError(f"{self.template_id}: espaço {name} sem lastro aceito")

    @property
    def slot_names(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(SLOT.findall(self.text)))


# Moldes genéricos mínimos. A casa troca todos pelos dela.
GENERIC_TEMPLATES: tuple[Template, ...] = (
    Template("acknowledge.basic", "1", "acknowledge", "Thank you for your message."),
    Template("inform.fact", "1", "inform", "{answer}", {"answer": SlotSpec(("fact",))}),
    Template("inform_limitation.basic", "1", "inform_limitation",
             "I can't do that here. I can hand you to the team."),
    Template("verify_with_staff.promise", "1", "verify_with_staff",
             "I'll check with the team and answer by {deadline}.",
             {"deadline": SlotSpec(("commitment:promise",), "at")}),
    # A sacola depois da mudança: o efeito pelo recibo (``done`` é o estado dele) e a sacola pelos termos
    # cotados de novo depois do recibo de sucesso (v2 4.7, propriedade 2: mudança material, termos novos).
    Template("change_cart.done", "2", "change_cart", "{done} Your cart now has:\n{items}\nTotal: {total}.",
             {"done": SlotSpec(("receipt:success",)), "items": SlotSpec(("fact",), "items"),
              "total": SlotSpec(("fact",), "total")}),
    # Degrau de baixo: o efeito aconteceu, mas os termos novos não vieram (a leitura falhou ou o carrinho
    # ficou vazio). Diz-se o efeito pelo recibo, e nada da sacola que não se leu.
    Template("change_cart.done_receipt", "1", "change_cart", "{done} Your cart is updated.",
             {"done": SlotSpec(("receipt:success",))}),
    # Recebimento: o molde mais completo que o recibo sustenta (``engine/moves/set_fulfillment.py``).
    # Os valores saem do recibo (o estado do alvo depois do efeito); a casa formata data, modo e janela.
    Template("set_fulfillment.done", "1", "set_fulfillment", "Done: {mode} on {date}, {window}.",
             {"mode": SlotSpec(("receipt:success",), "mode"), "date": SlotSpec(("receipt:success",), "date"),
              "window": SlotSpec(("receipt:success",), "window")}),
    Template("set_fulfillment.done_time", "1", "set_fulfillment", "Done: {mode} on {date} at {time}.",
             {"mode": SlotSpec(("receipt:success",), "mode"), "date": SlotSpec(("receipt:success",), "date"),
              "time": SlotSpec(("receipt:success",), "time")}),
    Template("set_fulfillment.done_day", "1", "set_fulfillment", "Done: {mode} on {date}.",
             {"mode": SlotSpec(("receipt:success",), "mode"), "date": SlotSpec(("receipt:success",), "date")}),
    Template("set_fulfillment.done_date", "1", "set_fulfillment", "Done: noted for {date}.",
             {"date": SlotSpec(("receipt:success",), "date")}),
    Template("set_fulfillment.done_mode", "1", "set_fulfillment", "Done: noted as {mode}.",
             {"mode": SlotSpec(("receipt:success",), "mode")}),
    Template("set_fulfillment.updated", "1", "set_fulfillment", "Done: your order details are updated ({ref}).",
             {"ref": SlotSpec(("receipt:success",), "effect")}),
    # O pedido pelo recibo, o total pelo pedido lido depois do efeito, e onde acompanhar (o mesmo recibo,
    # que a casa formata como o caminho dela para o pedido).
    Template("commit_order.done", "2", "commit_order", "Your order {order} is placed. Total: {total}. Track it: {track}.",
             {"order": SlotSpec(("receipt:success",), "effect"), "total": SlotSpec(("fact",), "total"),
              "track": SlotSpec(("receipt:success",), "effect")}),
    # Degrau de baixo: o pedido existe (recibo), mas a leitura dele não deu o total.
    Template("commit_order.done_order", "1", "commit_order", "Your order {order} is placed. Track it: {track}.",
             {"order": SlotSpec(("receipt:success",), "effect"), "track": SlotSpec(("receipt:success",), "effect")}),
    # Efeito pendente não é efeito: a parte é uma espera, não a confirmação do pedido.
    Template("commit_order.pending", "1", "wait",
             "Your order is being processed; I'll confirm by {deadline}.",
             {"deadline": SlotSpec(("commitment:promise",), "at")}),
    Template("inform.promise", "1", "inform", "We can have {quantity} ready for the requested time.",
             {"quantity": SlotSpec(("fact:promisable",))}),
    # "Em mãos agora" exige a leitura factual; o que se pode prometer não serve (K27).
    Template("inform.on_hand", "1", "inform", "We have {quantity} in stock right now.",
             {"quantity": SlotSpec(("fact:factual",))}),
)

TEMPLATES_BY_ID: dict[str, Template] = {t.template_id: t for t in GENERIC_TEMPLATES}
