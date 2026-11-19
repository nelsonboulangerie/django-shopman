"""Comércio falso, leitura e execução sobre o mesmo estado sintético.

Leitura: fonte fora, fato vencido, preço que muda entre a cotação e a
confirmação. Execução: queda antes e depois do efeito, resposta perdida,
efeito pendente; idempotência por (escopo, chave) com conferência do
``content_hash``; a guarda chamada dentro da "transação" do efeito.
"""

from __future__ import annotations

import dataclasses
from decimal import ROUND_HALF_EVEN, Decimal

from conversational_commerce.contracts import (
    ActionCommand,
    ActionReceipt,
    Known,
    Quantity,
    TermsDocument,
    Unknown,
    seal,
)
from conversational_commerce.contracts.common import Fact, Prediction
from conversational_commerce.contracts.errors import ErrorCode
from conversational_commerce.ports import (
    Capabilities,
    EffectGuard,
    EffectState,
    ItemSummary,
    PortError,
    PromiseReading,
    TrustedContext,
)
from conversational_commerce.ports import commerce_execute as execute_port
from conversational_commerce.ports import commerce_read as read_port

from .base import FakeBase
from .faults import Fault
from .synthetic_domain import CUSTOMERS, KNOWLEDGE, POLICIES, SyntheticState

FACT_VALIDITY_SECONDS = 300
TERMS_VALIDITY_SECONDS = 1800
RECONCILIATION_SECONDS = 900


class FakeCommerceRead(FakeBase):
    PORT = "commerce_read"

    def __init__(self, clock, faults=None, state: SyntheticState | None = None) -> None:
        super().__init__(clock, faults)
        self.state = state if state is not None else SyntheticState()
        self.quotes: dict[str, TermsDocument] = {}

    def capabilities(self) -> Capabilities:
        return Capabilities(port="commerce_read", operations=read_port.OPERATIONS,
                            guarantees={"fact_validity_seconds": FACT_VALIDITY_SECONDS, "object_authorization": True,
                                        "promise_is_not_reservation": True},
                            unsupported=("scarcity",))

    def _fact(self, operation: str, value, source: str) -> Fact:
        fault = self._fault(operation)
        if fault is Fault.SOURCE_FAILED:
            return Unknown(reason="source_failed")
        if fault is Fault.STALE_FACT:
            return Unknown(reason="stale")
        if value is None:
            return Unknown(reason="not_found")
        return Known(value=value, source=source, observed_at=self.clock.now(),
                     valid_until=self.clock.at(FACT_VALIDITY_SECONDS), source_version=f"v{len(self.calls)}")

    def search_catalog(self, ctx: TrustedContext, query: str) -> tuple[ItemSummary, ...]:
        if self._fault("search_catalog") is Fault.SOURCE_FAILED:
            raise PortError("provider_unavailable", "catálogo fora")
        needle = query.lower()
        return tuple(
            ItemSummary(ref=item.ref, name=item.name, unit=item.unit, price=item.price)
            for item in self.state.items.values()
            if needle in item.name.lower() or needle in item.ref.lower()
        )

    def read_item(self, ctx: TrustedContext, ref: str) -> Fact:
        item = self.state.items.get(ref)
        value = None if item is None else {"ref": item.ref, "name": item.name, "unit": item.unit,
                                           "price_minor": item.price_minor, "currency": item.price.currency}
        return self._fact("read_item", value, "fake-catalog")

    def promise(self, ctx: TrustedContext, ref: str, quantity: Quantity, when: str) -> PromiseReading:
        fault = self._fault("promise")
        item = self.state.items.get(ref)
        if item is None or fault is Fault.SOURCE_FAILED:
            gone = Unknown(reason="not_found" if item is None else "source_failed")
            return PromiseReading(ref=ref, quantity=quantity, factual=gone, expected=gone, planned=gone,
                                  promisable=gone)

        def known(value):
            return Known(value=value, source="fake-inventory", observed_at=self.clock.now(),
                         valid_until=self.clock.at(FACT_VALIDITY_SECONDS))

        wanted = Decimal(quantity.value)
        can = Decimal(item.on_hand) + Decimal(item.expected) >= wanted
        return PromiseReading(ref=ref, quantity=quantity, factual=known(item.on_hand), expected=known(item.expected),
                              planned=known(item.planned), promisable=known(can))

    def quote(self, ctx: TrustedContext, cart_ref: str) -> TermsDocument:
        fault = self._fault("quote")
        if fault is Fault.PROVIDER_DOWN:
            raise PortError("provider_unavailable", "cotação fora")
        cart = self.state.carts.get(cart_ref)
        if cart is None:
            raise PortError("object_forbidden", "carrinho inexistente ou de outro sujeito")
        owner = self.state.cart_owner.get(cart_ref)
        if ctx.subject is not None and owner != ctx.subject:
            raise PortError("object_forbidden", "carrinho de outro sujeito")
        items, total = [], 0
        for ref, qty in sorted(cart.items()):
            item = self.state.items[ref]
            line = int((Decimal(qty) * item.price_minor).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
            total += line
            items.append({"ref": ref, "quantity": {"value": qty, "unit": item.unit}, "unit_price": item.price,
                          "line_total": {"amount_minor": line, "currency": item.price.currency}})
        version = self.state.versions.get(cart_ref, 1)
        terms = seal(TermsDocument(
            **self.envelope(ctx, "terms"),
            terms_id=f"{cart_ref}-v{version}",
            version=version,
            items=items,
            total={"amount_minor": total, "currency": items[0]["unit_price"].currency},
            recipient={"subject_ref": owner or "unknown-subject"},
            fulfillment={"mode": "pickup"},
            valid_until=self.clock.at(TERMS_VALIDITY_SECONDS),
        ))
        self.quotes[terms.hash] = terms
        self.state.current_terms[cart_ref] = terms.hash
        if fault is Fault.PRICE_CHANGES_AFTER_QUOTE:
            # O preço muda depois da cotação: os termos apresentados deixam de ser os vigentes.
            self.state.current_terms.pop(cart_ref, None)
            ref = items[0]["ref"]
            self.state.items[ref] = dataclasses.replace(self.state.items[ref],
                                                        price_minor=self.state.items[ref].price_minor + 50)
            self.state.versions[cart_ref] = version + 1
        return terms

    def read_order(self, ctx: TrustedContext, ref: str) -> Fact:
        order = self.state.orders.get(ref)
        if order is not None and ctx.subject is not None and order["subject"] != ctx.subject:
            raise PortError("object_forbidden", "pedido de outro sujeito")
        return self._fact("read_order", order, "fake-orders")

    def read_customer(self, ctx: TrustedContext, ref: str) -> Fact:
        if ctx.subject is not None and ref != ctx.subject:
            raise PortError("object_forbidden", "cliente lê só o próprio cadastro")
        return self._fact("read_customer", CUSTOMERS.get(ref), "fake-customers")

    def read_policy(self, ctx: TrustedContext, policy_id: str) -> Fact:
        return self._fact("read_policy", POLICIES.get(policy_id), "fake-policies")

    def knowledge(self, ctx: TrustedContext, query: str) -> tuple[Fact, ...]:
        self._fault("knowledge")
        return tuple(
            Known(value={"topic": key, "text": text}, source="fake-knowledge", observed_at=self.clock.now())
            for key, text in KNOWLEDGE.items()
            if query.lower() in key or query.lower() in text.lower()
        )

    def scarcity(self, ctx: TrustedContext, ref: str) -> Prediction:
        from conversational_commerce.contracts import Unavailable

        return Unavailable(reason="not_supported")


class FakeCommerceExecute(FakeBase):
    PORT = "commerce_execute"

    def __init__(self, clock, faults=None, state: SyntheticState | None = None, epochs: dict | None = None) -> None:
        super().__init__(clock, faults)
        self.state = state if state is not None else SyntheticState()
        # (escopo, chave) → (content_hash, recibo)
        self.by_key: dict[tuple[str, str], tuple[str, ActionReceipt]] = {}
        # comando → efeito aplicado (para reconciliar depois de queda ou resposta perdida)
        self.applied: dict[str, str] = {}
        # Época de posse vigente por episódio (o teste muda quando a pessoa assume).
        self.epochs = epochs if epochs is not None else {}
        self.effects = 0

    def capabilities(self) -> Capabilities:
        return Capabilities(port="commerce_execute", operations=execute_port.OPERATIONS,
                            guarantees={"atomic_effect_guard": True, "idempotency_retention_seconds": 7 * 24 * 3600,
                                        "reconciliation": True})

    def _receipt(self, ctx, command: ActionCommand, **fields) -> ActionReceipt:
        return ActionReceipt(**self.envelope(ctx, "rcp", cause_id=command.id, episode_id=command.episode_id),
                             command_id=command.command_id, **fields)

    def _pending(self, ctx, command, status: str) -> ActionReceipt:
        return self._receipt(ctx, command, status=status, effect="unknown",
                             reconciliation={"deadline": self.clock.at(RECONCILIATION_SECONDS), "owner": "core"})

    def _apply(self, command: ActionCommand) -> str:
        """O efeito no sistema de registro. Devolve a referência de domínio."""
        self.effects += 1
        if command.action == "commit_order":
            order_ref = self.clock.new_id("order")
            subject = self.state.cart_owner.get(command.targets[0], "unknown-subject")
            self.state.orders[order_ref] = {"ref": order_ref, "subject": subject, "terms_hash": command.terms_hash,
                                            "state": "placed"}
            return order_ref
        for target in command.targets:
            self.state.versions[target] = self.state.versions.get(target, 0) + 1
            self.state.current_terms.pop(target, None)  # mudou o alvo: termos velhos não valem
        return f"effect-{self.effects:04d}"

    def execute(self, ctx: TrustedContext, command: ActionCommand, guard: EffectGuard) -> ActionReceipt:
        key = (command.idempotency.scope, command.idempotency.key)
        if key in self.by_key:
            stored_hash, receipt = self.by_key[key]
            if stored_hash != command.content_hash:
                raise PortError(ErrorCode.IDEMPOTENCY_CONFLICT, "mesma chave com outro conteúdo; recibo mantido")
            return receipt
        fault = self._fault("execute")
        if fault is Fault.CRASH_BEFORE_EFFECT:
            raise PortError(ErrorCode.EFFECT_UNKNOWN, "caiu antes do efeito; reconcilie com a mesma chave")
        # ── unidade atômica do efeito: guarda + efeito + recibo ──
        state = EffectState(
            now=self.clock.now(),
            terms_hash=self.state.current_terms.get(command.targets[0]) if command.terms_hash else None,
            versions={target: self.state.versions.get(target, 0) for target in command.expected_versions},
            ownership_epoch=self.epochs.get(command.episode_id, command.expected_ownership_epoch),
        )
        try:
            guard.verify(state)
        except PortError as refused:
            receipt = self._receipt(ctx, command, status="failure", effect="not_applied",
                                    error={"code": refused.code.value, "retry": "never"})
            self.by_key[key] = (command.content_hash, receipt)
            return receipt
        if fault is Fault.EFFECT_PENDING:
            receipt = self._pending(ctx, command, "pending")
            self.by_key[key] = (command.content_hash, receipt)
            return receipt
        ref = self._apply(command)
        self.applied[command.command_id] = ref
        receipt = self._receipt(ctx, command, status="success", effect="applied", domain_refs={"effect": ref},
                                observed_versions={t: self.state.versions.get(t, 0) for t in command.targets})
        if fault is Fault.CRASH_AFTER_EFFECT:
            # O efeito existe; a resposta se perdeu. Só a reconciliação acha o recibo.
            raise PortError(ErrorCode.EFFECT_UNKNOWN, "caiu depois do efeito; reconcilie com a mesma chave")
        self.by_key[key] = (command.content_hash, receipt)
        return receipt

    def locate(self, ctx: TrustedContext, scope: str, key: str) -> ActionReceipt | None:
        self._fault("locate")
        found = self.by_key.get((scope, key))
        return None if found is None else found[1]

    def reconcile(self, ctx: TrustedContext, command: ActionCommand) -> ActionReceipt:
        self._fault("reconcile")
        key = (command.idempotency.scope, command.idempotency.key)
        stored = self.by_key.get(key)
        if command.command_id in self.applied:
            ref = self.applied[command.command_id]
            receipt = self._receipt(ctx, command, status="success", effect="applied", domain_refs={"effect": ref},
                                    supersedes=stored[1].id if stored else None)
        elif stored is not None and stored[1].status in ("pending", "unknown"):
            receipt = self._pending(ctx, command, "pending")
        elif stored is not None:
            return stored[1]
        else:
            receipt = self._receipt(ctx, command, status="failure", effect="not_applied",
                                    error={"code": "provider_unavailable", "retry": "never"})
        self.by_key[key] = (command.content_hash, receipt)
        return receipt
