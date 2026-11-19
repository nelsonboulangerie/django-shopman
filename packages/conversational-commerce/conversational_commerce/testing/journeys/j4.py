"""J4 · Pedido com efeito: necessidade → cotação → termos → confirmação → pedido → recibo (v2 10).

Prova o contrato de efeito de ponta a ponta. A mudança de carrinho (A2) sai pela
concessão da linha do perfil; o fechamento (A3) só com termos apresentados, um
"sim" posterior a eles, do mesmo sujeito, na mesma época de posse, e a guarda no
ponto de efeito. Toda afirmação de efeito tem recibo de sucesso como lastro.

O adaptador diz quem fala e qual é o carrinho dele (``subject``): no domínio
sintético, ``customer-1`` com o ``cart-1``, identidade verificada pelo adaptador.
"""

from __future__ import annotations

from conversational_commerce.contracts import IdentityEvidence
from conversational_commerce.engine.state import Subject
from conversational_commerce.ports import TrustedContext

from .runner import JourneyStep

CTX = TrustedContext(tenant="tenant-a", environment="test", subject="customer-1")
VERIFIED = IdentityEvidence(kind="adapter_login", ref="customer-1", assurance="weak_verified")


def subject(ctx: TrustedContext, event) -> Subject:
    """O sujeito do contexto confiável, verificado pelo adaptador, com o carrinho dele."""
    if ctx.subject is None:
        return Subject(identity_evidence=tuple(event.identity_evidence))
    return Subject(subject_ref=ctx.subject, identity_evidence=(VERIFIED,), cart_ref="cart-1")


def message(mid: str, text: str, **extra):
    return {"id": mid, "from": "addr-j4", "conversation": "conv-j4", "content_ref": f"text:{text}", **extra}


CHANGE = JourneyStep(
    message=message("j4-m1", "make it three of item a"),
    understanding={"acts": [{"act": "change_quantity", "fields": {"item": "ITEM-A", "quantity": "3"}}]},
    expect_moves=("change_cart",),
    expect_text=("Done: your cart is updated",),
    expect_state="active",
)
QUOTE = JourneyStep(
    message=message("j4-m2", "place the order"),
    understanding={"acts": [{"act": "place_order"}]},
    expect_moves=("present_terms",),
    expect_text=("Your total is XTS 13.50. Shall I place the order?",),
    expect_state="waiting_authorization",
    advance_seconds=30,
)
CONFIRM = JourneyStep(
    message=message("j4-m3", "yes"),
    understanding={"acts": [{"act": "affirm"}]},
    expect_moves=("commit_order",),
    expect_text=("Your order order-0001 is placed.",),
    expect_state="active",
    advance_seconds=30,
)

STEPS = (CHANGE, QUOTE, CONFIRM)
