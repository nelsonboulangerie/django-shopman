"""Os efeitos da Concierge como sítio do executor do framework (N6; a sacola, #3198).

O executor (``shopman/shop/conversational/commerce_execute.py``) abre a transação, chama
``lock``, entrega o estado à ``EffectGuard`` e só então chama ``apply``. Este sítio não
inventa efeito nenhum: chama os executores que já existem, com as conferências deles.

| Ação do framework | Efeito que já existe | Alvo |
|---|---|---|
| ``change_cart`` | ``tools.set_item`` (quantidade absoluta; zero tira) | a sacola (``session_key``) |
| ``commit_order`` | ``tools.place_order`` (revisão ``quote_token``, confirmação posterior, ``run_idempotent_mutation``) | a sacola (``session_key``) |
| ``grant_discount`` | ``discount.handle_request`` → ``discount._grant`` | a sacola |
| ``cancel_order`` | ``cancellation._execute`` | o pedido do cliente |
| ``amend_order`` | ``order_addition.apply`` | o pedido do cliente |

``lock`` reusa o ponto do N2 (#2625): ``effect_authority.lock_turn_authority`` trava a linha
da conversa, a mesma que ``service.mark_handoff`` trava antes de subir o ``turn_fence``, e
reconfere a posse. A época de posse que a guarda confere é esse ``turn_fence``. A sacola é
travada também, e a versão dela é a ``Session.rev``; pedido não tem versão no Orderman, e o
efeito reconfere o estado dele (``self_cancellable``, a cotação nova do acréscimo).

O sítio é do turno: nasce com o ``ToolContext`` da conversa reivindicada. Ligá-lo no turno
da Nice é o N9.
"""

from __future__ import annotations

from dataclasses import dataclass

from conversational_commerce.contracts import ActionCommand
from conversational_commerce.contracts.errors import ErrorCode
from conversational_commerce.ports import PortError, TrustedContext

from shopman.shop.conversational.commerce_execute import TERMS_REF, Done, Reading

from .tools import ToolContext

ACTIONS = ("change_cart", "commit_order", "grant_discount", "cancel_order", "amend_order")
CART_ACTIONS = frozenset({"change_cart", "commit_order", "grant_discount"})

#: O código de recusa do ``place_order`` no vocabulário do framework.
ORDER_REFUSALS = {
    "identity_required": ErrorCode.IDENTITY_INSUFFICIENT,
    "invalid_input": ErrorCode.INVALID_CONTENT,
    "invalid_payment_method": ErrorCode.INVALID_CONTENT,
    "quote_stale": ErrorCode.TERMS_CHANGED,
    "revision_conflict": ErrorCode.REVISION_CONFLICT,
    "confirmation_required": ErrorCode.CONFIRMATION_REQUIRED,
    "intent_conflict": ErrorCode.IDEMPOTENCY_CONFLICT,
    "in_progress": ErrorCode.EFFECT_PENDING,
    "no_cart": ErrorCode.FACT_UNAVAILABLE,
    "authority_unavailable": ErrorCode.AUTHORITY_REVOKED,
}
DISCOUNT_REFUSALS = {"no_cart": ErrorCode.FACT_UNAVAILABLE}
#: O código de recusa do ``set_item``. O resto (estoque, escolha que se faz pela loja) é o
#: produto indisponível agora: fato, não erro de quem pediu.
CART_REFUSALS = {
    "missing_sku": ErrorCode.INVALID_CONTENT,
    "unknown_sku": ErrorCode.INVALID_CONTENT,
    "invalid_qty": ErrorCode.INVALID_CONTENT,
}


@dataclass
class ConciergeEffectSite:
    """Pedido, desconto, cancelamento e acréscimo da conversa de ``tool_context``."""

    tool_context: ToolContext
    actions: tuple[str, ...] = ACTIONS

    def lock(self, ctx: TrustedContext, command: ActionCommand) -> Reading:
        from shopman.orderman.models import Session

        from .effect_authority import lock_turn_authority
        from .order_addition import own_order
        from .service import TurnRevoked

        conversation = self.tool_context.conversation
        cart = command.action in CART_ACTIONS
        try:
            current = lock_turn_authority(conversation, channel_ref=self.tool_context.channel_ref if cart else None)
        except TurnRevoked as revoked:
            raise PortError(ErrorCode.AUTHORITY_REVOKED, f"a posse da conversa mudou ({revoked})") from revoked
        target = command.targets[0]
        if not cart:
            if own_order(conversation, target) is None:
                raise PortError(ErrorCode.OBJECT_FORBIDDEN, "pedido que não é do cliente da conversa")
            return Reading(ownership_epoch=current.turn_fence)
        if not current.session_key or target != current.session_key:
            raise PortError(ErrorCode.OBJECT_FORBIDDEN, "sacola que não é a da conversa")
        session = (
            Session.objects.select_for_update()
            .filter(session_key=target, channel_ref=self.tool_context.channel_ref)
            .first()
        )
        if session is None:
            raise PortError(ErrorCode.OBJECT_FORBIDDEN, "sacola que não é a da conversa")
        terms_ref = str((current.quote or {}).get("token") or "") or None if command.action == "commit_order" else None
        return Reading(ownership_epoch=current.turn_fence, versions={target: session.rev}, terms_ref=terms_ref)

    def apply(self, ctx: TrustedContext, command: ActionCommand) -> Done:
        from .service import TurnRevoked

        try:
            return getattr(self, f"_{command.action}")(command)
        except TurnRevoked:
            # A conferência do próprio efeito (o N2) recusou: nada nasceu.
            return Done(False, refusal=ErrorCode.AUTHORITY_REVOKED.value)

    # ── os efeitos ───────────────────────────────────────────────────────────
    def _change_cart(self, command: ActionCommand) -> Done:
        from . import tools

        sku, quantity = command.parameters.get("item"), command.parameters.get("quantity")
        if not isinstance(sku, str) or not sku or not isinstance(quantity, str) or not quantity.isdigit():
            return Done(False, refusal=ErrorCode.INVALID_CONTENT.value)
        result = tools.set_item(self.tool_context, sku, int(quantity))
        if result.get("ok"):
            return Done(True, domain_refs={"cart": command.targets[0], "item": sku})
        code = CART_REFUSALS.get(str(result.get("code") or ""), ErrorCode.FACT_UNAVAILABLE)
        return Done(False, refusal=code.value)

    def _commit_order(self, command: ActionCommand) -> Done:
        from . import tools

        parameters = command.parameters
        token, method = parameters.get(TERMS_REF), parameters.get("payment_method")
        notes = parameters.get("order_notes") or ""
        if not isinstance(token, str) or not token or not isinstance(method, str) or not isinstance(notes, str):
            return Done(False, refusal=ErrorCode.INVALID_CONTENT.value)
        result = tools.place_order(self.tool_context, token, method, notes)
        if result.get("ok") and result.get("order_ref"):
            return Done(True, domain_refs={"order": str(result["order_ref"])})
        code = ORDER_REFUSALS.get(str(result.get("code") or ""), ErrorCode.PROVIDER_UNAVAILABLE)
        return Done(False, refusal=code.value)

    def _grant_discount(self, command: ActionCommand) -> Done:
        from . import discount

        outcome = discount.handle_request(
            conversation=self.tool_context.conversation,
            channel_ref=self.tool_context.channel_ref,
            customer_text=str(command.parameters.get("customer_text") or ""),
        )
        if outcome.code == "granted" and outcome.coupon_code:
            return Done(True, domain_refs={"coupon": outcome.coupon_code, "cart": command.targets[0]})
        return Done(False, refusal=DISCOUNT_REFUSALS.get(outcome.code, ErrorCode.CAPABILITY_MISSING).value)

    def _cancel_order(self, command: ActionCommand) -> Done:
        from . import cancellation

        state = {"order_ref": command.targets[0], "request": str(command.parameters.get("request") or "")}
        outcome = cancellation._execute(self.tool_context.conversation, state)
        if outcome.code == "cancelled" and outcome.order_ref:
            return Done(True, domain_refs={"order": outcome.order_ref})
        return Done(False, refusal=ErrorCode.REVISION_CONFLICT.value)

    def _amend_order(self, command: ActionCommand) -> Done:
        from . import order_addition

        parameters = command.parameters
        pending = {"order_ref": command.targets[0], "add": list(parameters.get("add") or ()),
                   "total_q": parameters.get("total_q")}
        outcome = order_addition.apply(self.tool_context.conversation, pending)
        if outcome.code == "added" and outcome.order_ref:
            return Done(True, domain_refs={"order": outcome.order_ref})
        # ``asked`` é a cotação de agora, diferente da confirmada: os termos mudaram.
        code = ErrorCode.TERMS_CHANGED if outcome.code == "asked" else ErrorCode.REVISION_CONFLICT
        return Done(False, refusal=code.value)
