"""Os efeitos da Concierge como sítio do executor do framework (N6; a sacola, #3198).

O executor (``shopman/shop/conversational/commerce_execute.py``) abre a transação, chama
``lock``, entrega o estado à ``EffectGuard`` e só então chama ``apply``. Este sítio não
inventa efeito nenhum: chama os executores que já existem, com as conferências deles.

| Ação do framework | Efeito que já existe | Alvo |
|---|---|---|
| ``change_cart`` | ``tools.set_item`` (quantidade absoluta; zero tira) | a sacola (``session_key``) |
| ``set_fulfillment`` | ``tools.set_fulfillment`` e a grade de horários (retirada); o dia pela régua do checkout | a sacola |
| ``set_delivery_address`` | ``tools.set_fulfillment`` (entrega), com o texto ORIGINAL lido pela referência da fala | a sacola |
| ``set_payment`` | a escrita da forma que a revisão da casa faz (``review_order``), só as formas do canal sem dinheiro | a sacola |
| ``commit_order`` | ``tools.place_order`` (revisão ``quote_token``, confirmação posterior, ``run_idempotent_mutation``) | a sacola (``session_key``) |
| ``grant_discount`` | ``discount.handle_request`` → ``discount._grant`` | a sacola |
| ``cancel_order`` | ``cancellation._execute`` | o pedido do cliente |
| ``amend_order`` | ``order_addition.apply`` | o pedido do cliente |

``lock`` reusa o ponto do N2 (#2625): ``effect_authority.lock_turn_authority`` trava a linha
da conversa, a mesma que ``service.mark_handoff`` trava antes de subir o ``turn_fence``, e
reconfere a posse. A época de posse que a guarda confere é esse ``turn_fence``. A sacola é
travada também, e a versão dela é a ``Session.rev``; pedido não tem versão no Orderman, e o
efeito reconfere o estado dele (``self_cancellable``, a cotação nova do acréscimo).

A sacola ainda não existe no primeiro pedido pelo motor: o alvo é a sacola NOVA da conversa
(``ports.new_cart_ref``), e ela nasce no efeito (``set_item``, ``_ensure_session``), nunca na leitura.

O sítio é do turno: nasce com o ``ToolContext`` da conversa reivindicada. Ligá-lo no turno
da Nice é o N9.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from conversational_commerce.contracts import ActionCommand
from conversational_commerce.contracts.errors import ErrorCode
from conversational_commerce.ports import PortError, TrustedContext

from shopman.shop.conversational.commerce_execute import TERMS_REF, Done, Reading

from .ports import new_cart_ref
from .tools import ToolContext

ACTIONS = ("change_cart", "set_fulfillment", "set_delivery_address", "set_payment", "commit_order",
           "grant_discount", "cancel_order", "amend_order")
CART_ACTIONS = frozenset({"change_cart", "set_fulfillment", "set_delivery_address", "set_payment", "commit_order",
                          "grant_discount"})
#: As ações que podem cair na sacola nova da conversa (as outras pedem sacola com item).
NEW_CART_ACTIONS = frozenset({"change_cart", "set_fulfillment", "set_payment"})
#: O que o comando ``set_fulfillment`` aceita: só o que o cliente disse.
FULFILLMENT_FIELDS = frozenset({"date", "mode", "time"})
_CLOCK = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

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
#: A recusa do ``set_fulfillment`` da casa. O resto (validação de dia ou horário, modo que o canal
#: não oferece) é o recebimento que a casa não atende.
FULFILLMENT_REFUSALS = {
    "invalid_fulfillment": ErrorCode.INVALID_CONTENT,
    "invalid_date": ErrorCode.INVALID_CONTENT,
    "no_cart": ErrorCode.FACT_UNAVAILABLE,
    "revision_conflict": ErrorCode.REVISION_CONFLICT,
}
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
        # A época de posse é a do episódio do motor (muda quando a equipe assume e devolve), não a cerca do
        # turno da casa (``turn_fence``, que sobe a cada mensagem). O que a guarda pergunta, "a posse mudou
        # depois da decisão?", a casa acabou de responder na trava acima: a mesma cerca, a conversa ativa, a
        # reivindicação válida. Passada a trava, a leitura atesta a época que o comando espera; não passada,
        # o efeito já foi recusado (#3410: com a cerca no lugar da época, todo efeito no ar saía revogado).
        epoch = command.expected_ownership_epoch
        target = command.targets[0]
        if cart and command.action in NEW_CART_ACTIONS and target == new_cart_ref(conversation.pk):
            # A sacola nova desta conversa: nasce no efeito. Se outra parte do turno já a criou,
            # o efeito cai nela, a mesma sacola presa ao telefone.
            return Reading(ownership_epoch=epoch, versions={target: 0})
        if not cart:
            if own_order(conversation, target) is None:
                raise PortError(ErrorCode.OBJECT_FORBIDDEN, "pedido que não é do cliente da conversa")
            return Reading(ownership_epoch=epoch)
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
        return Reading(ownership_epoch=epoch, versions={target: session.rev}, terms_ref=terms_ref)

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

        lines = command.parameters.get("lines")
        if not isinstance(lines, (list, tuple)) or not lines:
            return Done(False, refusal=ErrorCode.INVALID_CONTENT.value)
        for line in lines:
            sku, quantity = line.get("item"), line.get("quantity")
            if not isinstance(sku, str) or not sku or not isinstance(quantity, str) or not quantity.isdigit():
                return Done(False, refusal=ErrorCode.INVALID_CONTENT.value)
        # Todas as linhas na mesma transação do executor: uma recusa desfaz as anteriores (tudo ou nada).
        for line in lines:
            result = tools.set_item(self.tool_context, line["item"], int(line["quantity"]))
            if not result.get("ok"):
                code = CART_REFUSALS.get(str(result.get("code") or ""), ErrorCode.FACT_UNAVAILABLE)
                return Done(False, refusal=code.value)
        # ``effect``: o que o molde do pacote cita (``change_cart.done``, faceta ``effect``).
        # A sacola nova nasce no ``set_item``: o recibo aponta a de verdade, nunca o alvo provisório.
        session = tools._open_session(self.tool_context)
        cart = str(session.session_key) if session is not None else command.targets[0]
        return Done(True, domain_refs={"effect": cart, "cart": cart, "items": ",".join(line["item"] for line in lines)})

    def _set_fulfillment(self, command: ActionCommand) -> Done:
        """O dia, retirada ou entrega, e a hora: aplica o que veio e guarda o resto.

        Retirada passa pelo ``tools.set_fulfillment`` (o mesmo do fechamento de hoje), com a
        janela da grade que cobre a hora dita. O dia sem modo, e a entrega (cujo endereço vem
        depois, no fechamento), passam pela régua de encomenda do checkout e pela operação
        canônica da sessão. O recibo diz o recebimento DEPOIS do efeito: ``date``, ``mode``,
        ``time`` e a ``window`` (a janela da grade, quando há).
        """
        from shopman.shop.services import cart as cart_service
        from shopman.shop.services import sessions as session_service
        from shopman.storefront.intents.checkout import _validate_preorder

        from . import tools
        from .order_closing import _fulfillment_types, _match_slot

        said = dict(command.parameters)
        if not said or set(said) - FULFILLMENT_FIELDS or not all(isinstance(v, str) and v for v in said.values()):
            return Done(False, refusal=ErrorCode.INVALID_CONTENT.value)
        try:
            day = date.fromisoformat(said["date"]).isoformat() if "date" in said else ""
        except ValueError:
            return Done(False, refusal=ErrorCode.INVALID_CONTENT.value)
        clock = _CLOCK.match(said.get("time", "")) if "time" in said else None
        if "time" in said and clock is None:
            return Done(False, refusal=ErrorCode.INVALID_CONTENT.value)
        unavailable = Done(False, refusal=ErrorCode.FULFILLMENT_UNAVAILABLE.value)
        ctx = self.tool_context
        types = _fulfillment_types(ctx.channel_ref)
        if "mode" in said and said["mode"] not in types:
            return unavailable
        session = tools._ensure_session(ctx)
        data = dict(session.data or {})
        day = day or str(data.get("delivery_date") or "")
        kind = said.get("mode") or str(data.get("fulfillment_type") or "")
        if not kind and len(types) == 1:
            kind = types[0]
        if not kind and clock is not None and "pickup" in types:
            kind = "pickup"  # hora dita sem modo é a de buscar (a mesma leitura do fechamento de hoje)
        slot = ""
        if clock is not None:
            day = day or tools._today_iso()
            listing = tools.execute("list_fulfillment_slots", {"delivery_date": day,
                                                               "fulfillment_type": kind or "pickup"}, ctx)
            slots = list(listing.get(f"{kind or 'pickup'}_slots") or [])
            chosen = _match_slot(slots, int(clock.group(1)) * 60 + int(clock.group(2)))
            if chosen is None or not chosen.get("available", chosen.get("enabled", True)):
                return unavailable
            slot = str(chosen.get("ref") or "")
        elif day == str(data.get("delivery_date") or "") and kind == str(data.get("fulfillment_type") or ""):
            slot = str(data.get("delivery_time_slot") or "")
        if kind == "pickup":
            result = tools.execute("set_fulfillment", {"fulfillment_type": "pickup", "delivery_date": day,
                                                       "slot_ref": slot}, ctx)
            if not result.get("ok"):
                code = FULFILLMENT_REFUSALS.get(str(result.get("error") or result.get("code") or ""),
                                                ErrorCode.FULFILLMENT_UNAVAILABLE)
                return Done(False, refusal=code.value)
        else:
            if day and _validate_preorder(day, cart_lines=list(session.items or []), channel_ref=ctx.channel_ref,
                                          session_key=session.session_key):
                return unavailable
            if kind == "delivery":
                cart_service.set_delivery_draft(session_key=session.session_key, channel_ref=ctx.channel_ref,
                                                fulfillment_type="delivery")
            if day:
                session_service.modify_session(
                    session_key=session.session_key, channel_ref=ctx.channel_ref,
                    ops=[{"op": "set_data", "path": "delivery_date", "value": day},
                         {"op": "set_data", "path": "delivery_time_slot", "value": slot}])
        refs = {"effect": session.session_key, "cart": session.session_key}
        refs.update({key: value for key, value in (("date", day), ("mode", kind), ("window", slot),
                                                   ("time", said.get("time", ""))) if value})
        return Done(True, domain_refs=refs)

    def _set_delivery_address(self, command: ActionCommand) -> Done:
        """O endereço da entrega, lido AQUI, no texto original da fala (P17: nunca pela IA, nunca em contrato).

        O comando traz só a referência protegida da fala (``source``). A leitura é a da casa
        (``address_parts``): o endereço inteiro, ou a parte que faltava (número, CEP, bairro, complemento).
        Grava pelo ``tools.set_fulfillment`` de hoje (a geocodificação, a área de entrega, a régua da nota),
        mantendo o dia e a janela já combinados. O recibo traz só ``address_ref``, opaca.
        """
        from shopman.shop.conversational.commerce_read import address_ref

        from . import tools
        from .ports import resolve_text, shared_location_of

        source = command.parameters.get("source")
        if set(command.parameters) != {"source"} or not isinstance(source, str) or not source:
            return Done(False, refusal=ErrorCode.INVALID_CONTENT.value)
        ctx = self.tool_context
        session = tools._open_session(ctx)
        data = dict((session.data if session is not None else None) or {})
        if session is None or data.get("fulfillment_type") != "delivery":
            # O endereço vem com a entrega: sem ela, o motor pergunta "retirada ou entrega?" (``ask_mode``).
            return Done(False, refusal=ErrorCode.FACT_UNAVAILABLE.value)
        # Só o trecho de endereço da fala: "apto 12, e põe mais um croissant" grava "apto 12" (o croissant é da
        # sacola, outro movimento do turno, e nunca vai para a etiqueta nem para a nota).
        said = (
            {"use_shared_location": True} if shared_location_of(source)
            else address_parts(address_of(resolve_text(source)), data.get("delivery_address_structured"))
        )
        if not said:
            return Done(False, refusal=ErrorCode.INVALID_CONTENT.value)
        result = tools.set_fulfillment(
            ctx, fulfillment_type="delivery", delivery_date=str(data.get("delivery_date") or ""),
            slot_ref=str(data.get("delivery_time_slot") or ""), **said)
        if not result.get("ok") or result.get("code") in {"saved_address_offer", "saved_addresses"}:
            # Só "não localizei" tem frase própria (``set_delivery_address.not_located``); o resto é o
            # efeito que falhou (dia ou janela que deixou de valer, sem localização enviada), e quem responde
            # é a limitação comum. Nunca ``fact_unavailable``, que é a falta da entrega (``ask_mode``).
            located = str(result.get("error") or "") != "address_not_located"
            return Done(False, refusal=(ErrorCode.PROVIDER_UNAVAILABLE if located else ErrorCode.INVALID_CONTENT).value)
        if result.get("delivery_out_of_zone"):
            return Done(False, refusal=ErrorCode.FULFILLMENT_UNAVAILABLE.value)  # fora da área: nada fica gravado
        cart = str(session.session_key)
        written = tools._open_session(ctx)  # o endereço como ficou gravado: a referência é dele
        recorded = dict((written.data if written is not None else None) or {})
        return Done(True, domain_refs={"effect": cart, "cart": cart, "address_ref": address_ref(cart, recorded)})

    def _set_payment(self, command: ActionCommand) -> Done:
        """A forma de pagamento na sacola, como a revisão da casa a grava (a mesma do fechamento de hoje).

        Só as formas do canal, sem dinheiro (D-003): o motor só propõe a que o fato ``requirements``
        oferece, e o sítio confere de novo. O recibo diz a forma gravada (``method``).
        """
        from . import tools
        from .order_closing import _methods

        said = dict(command.parameters)
        method = said.get("method")
        if set(said) != {"method"} or not isinstance(method, str) or not method:
            return Done(False, refusal=ErrorCode.INVALID_CONTENT.value)
        if method not in _methods(self.tool_context.channel_ref):
            return Done(False, refusal=ErrorCode.INVALID_CONTENT.value)
        # A MESMA escrita que a revisão da casa faz com a forma escolhida (``review_order``), pela
        # operação canônica da sessão (sobe a revisão da sacola: o "sim" de antes cai, N07). Direto,
        # e não pelo ``review_order``, porque ele não grava nada com a sacola vazia ("pago no pix" antes do item).
        session = tools._ensure_session(self.tool_context)
        session = tools._set_session_data(self.tool_context, session.session_key, {"payment": {"method": method}})
        cart = str(session.session_key)
        return Done(True, domain_refs={"effect": cart, "cart": cart, "method": method})

    def _commit_order(self, command: ActionCommand) -> Done:
        from . import tools

        parameters = command.parameters
        token, method = parameters.get(TERMS_REF), parameters.get("payment_method")
        notes = parameters.get("order_notes") or ""
        if not parameters:
            # O "sim" do motor: a confirmação é presa aos termos pelo hash e pela revisão da sacola
            # (o ``lock`` e a guarda já conferiram que é a mesma). A casa revisa a sacola de novo, com
            # a forma de pagamento que já está nela (ou a única do canal), e grava por essa revisão.
            review = tools.execute("review_order", {}, self.tool_context)
            if not (review.get("ok") and review.get("ready") and review.get("quote_token")):
                # O pedido não está completo (sem pagamento escolhido, sem recebimento): nada nasce.
                return Done(False, refusal=ErrorCode.INVALID_CONTENT.value)
            token, method = str(review["quote_token"]), str(review.get("payment_method") or "")
        if not isinstance(token, str) or not token or not isinstance(method, str) or not isinstance(notes, str):
            return Done(False, refusal=ErrorCode.INVALID_CONTENT.value)
        result = tools.place_order(self.tool_context, token, method, notes)
        if result.get("ok") and result.get("order_ref"):
            order = str(result["order_ref"])
            return Done(True, domain_refs={"effect": order, "order": order})
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


_CEP = re.compile(r"^\d{5}-?\d{3}$")
_NUMBER = re.compile(r"^(?:n[º°o.]?\s*)?(\d{1,6}[a-z]?|s/?n|sem n[uú]mero)$")
#: Fala que traz um logradouro (o tipo e o nome) ou um CEP: é endereço novo, nunca complemento.
#: Sobre o texto dobrado (sem acento, minúsculo): "na verdade e rua y, 50", "av. brasil 1200", "86010-000".
_NEW_ADDRESS = re.compile(
    r"\b(?:rua|avenida|av|alameda|travessa|rodovia|estrada|praca|largo)\.?\s+\w|\b\d{5}-?\d{3}\b")


#: Onde uma fala se divide em trechos: vírgula, ponto e vírgula, exclamação, interrogação, "e", "mas".
#: O ponto fica de fora ("Av. Brasil" é um trecho só).
_CLAUSE_SEP = re.compile(r"(\s*[,;!?]\s*|\s+(?:e|mas)\s+)", re.IGNORECASE)
#: Trecho que pede outra coisa, pelas palavras da casa (sobre o texto dobrado): mexer na sacola, agradecer.
_OTHER_CUE = re.compile(
    r"\b(?:poe|ponha|coloca|coloque|bota|adiciona|acrescenta|inclui|mais|menos|tira|remove|troca|quero|queria|"
    r"gostaria|manda|traz|vou querer|obrigad\w*|valeu)\b")
MASK = "[endereço omitido]"


def _product_words() -> frozenset[str]:
    """As palavras dos nomes do cardápio (dobradas, de 4 letras ou mais): "croissant", "campanha"."""
    from shopman.offerman.models import Product

    from .address import _fold

    names = Product.objects.filter(is_sellable=True).values_list("name", flat=True)
    return frozenset(word for name in names for word in re.findall(r"\w{4,}", _fold(str(name))))


def _other_clause(piece: str, products: frozenset[str]) -> bool:
    """O trecho pede outra coisa que não o endereço: um ato da regra local, uma palavra do fechamento
    (desistir, fechar, pagar, retirar, entregar), um verbo de sacola ou um produto do cardápio."""
    from .address import _fold
    from .order_closing import _CARD_RE, _CASH_RE, _DELIVERY_RE, _GIVE_UP_RE, _PICKUP_RE, _PIX_RE, _START_RE
    from .turn_framework import NiceRules

    folded = _fold(piece)
    rules = (_GIVE_UP_RE, _START_RE, _PIX_RE, _CARD_RE, _CASH_RE, _PICKUP_RE, _DELIVERY_RE, _OTHER_CUE)
    words = re.findall(r"\w{4,}", folded)
    named = any(word in products or word.rstrip("s") in products for word in words)  # "croissants"
    return bool(NiceRules().read(piece)) or any(rule.search(folded) for rule in rules) or named


def address_clauses(text: str) -> list[tuple[str, bool | None]]:
    """A fala em trechos, na ordem: ``(trecho, é_endereço)``; o separador vem como ``(sep, None)``.

    "apto 12, e põe mais um croissant" → ``[("apto 12", True), (", e ", None), ("põe mais um croissant", False)]``.
    """
    products = _product_words()
    found: list[tuple[str, bool | None]] = []
    for index, piece in enumerate(_CLAUSE_SEP.split(str(text or ""))):
        if index % 2:
            found.append((piece, None))
        elif piece.strip():
            found.append((piece.strip(), not _other_clause(piece, products)))
    return found


def address_of(text: str) -> str:
    """Só os trechos de endereço da fala ("apto 12, e põe mais um croissant" → "apto 12")."""
    return ", ".join(piece for piece, is_address in address_clauses(text) if is_address)


def masked_for_reading(text: str) -> str:
    """A fala com cada trecho de endereço trocado pela máscara: é o que a IA lê (P17)."""
    clauses = address_clauses(text)
    out: list[str] = []
    for index, (piece, is_address) in enumerate(clauses):
        if is_address is None:
            before = clauses[index - 1][1] if index else None
            after = clauses[index + 1][1] if index + 1 < len(clauses) else None
            if before and after:
                continue  # entre dois trechos de endereço: some na máscara única
            out.append(piece)
        elif is_address:
            if MASK not in out[-1:]:
                out.append(MASK)
        else:
            out.append(piece)
    return "".join(out)


def address_parts(text: str, structured) -> dict:
    """A leitura da casa do que o cliente escreveu para o endereço (``tools.set_fulfillment``).

    Sem endereço na sacola, o texto é o endereço inteiro. Com endereço, a resposta ao que faltava:
    o CEP, o número (ou "sem número"), o bairro (quando só ele falta) ou o complemento (quando só ele
    falta; "sem complemento" responde, e uma fala com logradouro ou CEP é endereço novo). Qualquer outra
    fala é um endereço novo, inteiro.
    """
    from shopman.shop.conversational.commerce_read import _address_requirements

    from .address import _fold

    text = " ".join(str(text or "").split())
    if not text:
        return {}
    if not isinstance(structured, dict) or not structured.get("formatted_address"):
        return {"address": text}
    pending = _address_requirements({"delivery_address_structured": structured})
    folded = _fold(text)
    if "delivery_complement" in pending:
        # "na verdade é Rua Y, 50": a pergunta era o complemento, mas a fala é outro endereço.
        return {"address": text} if _NEW_ADDRESS.search(folded) else {"complement": text}
    words = pending.get("delivery_address_details") or []
    if words and _CEP.match(folded.replace(" ", "")):
        return {"postal_code": text}
    if words and _NUMBER.match(folded):
        return {"street_number": text}
    if words == ["o bairro"] and not any(ch.isdigit() for ch in text):
        return {"neighborhood": text}
    return {"address": text}
