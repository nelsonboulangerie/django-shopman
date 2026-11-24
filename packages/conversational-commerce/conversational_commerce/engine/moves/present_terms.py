"""Apresentar os termos: cotar pela porta e mostrar o total, com lastro (A1).

Proposto para o pedido de fechar (``place_order``) e para a confirmação que não
valeu mais (termos que mudaram ou venceram, concessão vencida, confirmação
anterior aos termos): termos novos, confirmação nova (K07). Só com termos
cotados neste turno; o total entra por espaço travado, vindo da cotação.
Escolhido, o episódio vai a ``waiting_authorization`` e a pergunta que pede a
confirmação fica no ar, presa ao hash dos termos (``authority.Offer``).
"""

from __future__ import annotations

from conversational_commerce.policy import Proposal
from conversational_commerce.reply import PartSpec, SlotSpec, Template

MOVE = "present_terms"
TEMPLATES = (
    # Os termos apresentados são o documento canônico inteiro (v2 4.7): as linhas, o recebimento e as
    # condições, não só o total. O "sim" responde ao que o cliente viu.
    Template("present_terms.confirm", "2", MOVE,
             "{items}\nTotal: {total}\n{fulfillment}\n{conditions}\nShall I place the order?",
             {"items": SlotSpec(("fact",), "items"), "total": SlotSpec(("fact",), "total"),
              "fulfillment": SlotSpec(("fact",), "fulfillment"), "conditions": SlotSpec(("fact",), "conditions")}),
    # Condição obrigatória dos termos ausente: os termos não se apresentam (nenhuma pergunta de confirmação
    # nasce), e a parte pergunta pela condição, com as opções do canal num espaço de lista lastreado no fato
    # ``requirements.<carrinho>``. Um molde por condição; o genérico diz só o que falta.
    Template("present_terms.needs_payment_method", "1", MOVE, "How would you like to pay? {payment_method}",
             {"payment_method": SlotSpec(("fact",), "payment_method")}),
    # A entrega (spec 08 §6): o endereço, o que falta nele (lista lastreada no fato) e o complemento.
    Template("present_terms.needs_delivery_address", "1", MOVE,
             "What is the delivery address? Send your location or write street, number and district."),
    Template("present_terms.needs_delivery_address_details", "1", MOVE,
             "For the delivery, tell me {delivery_address_details}.",
             {"delivery_address_details": SlotSpec(("fact",), "delivery_address_details")}),
    Template("present_terms.needs_delivery_complement", "1", MOVE,
             "Is there a complement (apartment, block)? If not, just say \"no complement\"."),
    # A entrega de quem tem endereço no cadastro: o cadastro primeiro (sim ou não), por referência opaca (P17).
    Template("present_terms.needs_delivery_address_saved", "1", MOVE,
             "Shall we deliver to your saved address, {delivery_address_saved}?",
             {"delivery_address_saved": SlotSpec(("fact",), "delivery_address_saved")}),
    Template("present_terms.needs_delivery_address_saved_many", "1", MOVE,
             "Shall we deliver to your saved address, {delivery_address_saved}? If you prefer another saved "
             "address, tell me which.",
             {"delivery_address_saved": SlotSpec(("fact",), "delivery_address_saved")}),
    Template("present_terms.needs_delivery_address_saved_declined", "1", MOVE, "What is the delivery address?"),
    Template("present_terms.needs", "1", MOVE, "Before I can place the order I still need: {missing}.",
             {"missing": SlotSpec(("fact",), "missing")}),
    Template("present_terms.changed", "1", MOVE,
             "The terms changed before I could place the order. The new total is {total}. Shall I place it?",
             {"total": SlotSpec(("fact",), "total")}),
)


def propose(state, need):
    target = state.subject.cart_ref
    if target is None or target not in state.terms or not state.wants_terms(need):
        return None
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE,
                    content={"terms": state.terms[target].hash},
                    situation=state.situation(need, conditions_known=state.conditions_known()))


def reply(state, need):
    # "Os termos mudaram" só quando o ponto de efeito recusou; termos vencidos ou "sim" fora de ordem: termos de novo.
    missing = state.missing_conditions()
    if missing:
        code, known = missing[0], {t.template_id for t in TEMPLATES}
        needs = ("fact", state.requirements_key(state.subject.cart_ref))
        if state.declines_condition(need) and f"present_terms.needs_{code}_declined" in known:
            return PartSpec(MOVE, f"present_terms.needs_{code}_declined")  # recusou a opção: o que falta, sem ela
        if len(state.offered(state.subject.cart_ref, code)) > 1 and f"present_terms.needs_{code}_many" in known:
            return PartSpec(MOVE, f"present_terms.needs_{code}_many", {code: needs})  # mais de uma opção
        if f"present_terms.needs_{code}" in known:
            return PartSpec(MOVE, f"present_terms.needs_{code}", {code: needs})
        return PartSpec(MOVE, "present_terms.needs", {"missing": needs})
    key = ("fact", state.terms_key(state.subject.cart_ref))
    if need.need_id in state.refused:
        return PartSpec(MOVE, "present_terms.changed", {"total": key})
    return PartSpec(MOVE, "present_terms.confirm", dict.fromkeys(("items", "total", "fulfillment", "conditions"), key))
