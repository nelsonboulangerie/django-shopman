"""
Resolvers de emissão de NFC-e — exemplos prontos para ``SHOPMAN_FISCAL_EMISSION_RESOLVER``.

Um resolver é só ``callable(order) -> bool``: devolve True para emitir a nota, False para
não emitir. O motor (``shopman.shop.services.fiscal.emission_resolver``) chama o resolver
apontado no settings; se AUSENTE ou com erro, cai no fallback padrão (opt-in do operador).

Aponte no ambiente/settings, ex.:
    SHOPMAN_FISCAL_EMISSION_RESOLVER = "shopman.shop.fiscal_resolvers.on_request_or_tax_id"

Vários resolvers de uma vez:
- No env, separe por VÍRGULA → combinados por OR (emite se QUALQUER um disser sim):
    SHOPMAN_FISCAL_EMISSION_RESOLVER = "...on_request_or_tax_id,...card_payment"
- Para AND/NOT ou lógica composta, monte um resolver próprio com os COMBINADORES:
    # meuapp/fiscais.py
    from shopman.shop.fiscal_resolvers import all_of, not_in_debug, on_request_or_tax_id
    resolver = all_of(on_request_or_tax_id, not_in_debug)   # emite E não em DEBUG
    # SHOPMAN_FISCAL_EMISSION_RESOLVER = "meuapp.fiscais.resolver"
"""

from __future__ import annotations

# ── combinadores (AND / OR / NOT) ─────────────────────────────────────────────


def any_of(*resolvers):
    """OR: emite se QUALQUER resolver disser sim. ``any_of(a, b, c)``."""

    def _resolver(order) -> bool:
        return any(bool(r(order)) for r in resolvers)

    return _resolver


def all_of(*resolvers):
    """AND: emite só se TODOS disserem sim. Ideal para combinar razão + guarda,
    ex.: ``all_of(on_request_or_tax_id, not_in_debug)``."""

    def _resolver(order) -> bool:
        return all(bool(r(order)) for r in resolvers)

    return _resolver


def not_(resolver):
    """NOT: inverte um resolver. ``not_(pickup_only)``."""

    def _resolver(order) -> bool:
        return not bool(resolver(order))

    return _resolver


def always(order) -> bool:
    """Emite SEMPRE (toda venda vira NFC-e). Postura mais conservadora/fiscal."""
    return True


def on_request_or_tax_id(order) -> bool:
    """Emite quando o operador pediu OU o cliente informou CPF/CNPJ ("CPF na nota").

    É a regra prática de balcão: a maioria não pede nota; quem informa o documento
    quer a nota — então emite. Exemplo real recomendado para começar.
    """
    data = order.data or {}
    fiscal = data.get("fiscal") or {}
    customer = data.get("customer") or {}
    return bool(fiscal.get("issue_document") or (customer.get("tax_id") or "").strip())


def channels(*refs: str):
    """Fábrica: emite sempre nos canais dados (ex.: só no PDV presencial).

    Uso (resolver por canal exige um wrapper importável):
        emit_pdv = channels("pdv")
        SHOPMAN_FISCAL_EMISSION_RESOLVER = "meuapp.fiscais.emit_pdv"
    """
    allowed = {r.strip().lower() for r in refs if r.strip()}

    def _resolver(order) -> bool:
        return (getattr(order, "channel_ref", "") or "").lower() in allowed

    return _resolver


def above_amount_q(threshold_q: int):
    """Fábrica: emite quando o total é ≥ ``threshold_q`` centavos.

        emit_big = above_amount_q(10000)  # ≥ R$ 100,00
        SHOPMAN_FISCAL_EMISSION_RESOLVER = "meuapp.fiscais.emit_big"
    """

    def _resolver(order) -> bool:
        return int(getattr(order, "total_q", 0) or 0) >= int(threshold_q)

    return _resolver


# ── forma de pagamento ────────────────────────────────────────────────────────


def _payment_methods_present(order) -> set[str]:
    """Os métodos que de fato compõem o pagamento, lidos das LINHAS (tenders).

    ``payment.method`` é um rótulo agregado — numa venda mista ele colapsa para
    ``"mixed"`` e esconde o cartão que está lá dentro. As linhas dizem a
    verdade; o rótulo é o fallback para pedidos sem tenders (canais remotos).
    """
    payment = (order.data or {}).get("payment") or {}
    tenders = payment.get("tenders") or []
    methods = {
        str(t.get("method") or "").strip().lower()
        for t in tenders
        if isinstance(t, dict) and t.get("amount_q")
    }
    methods.discard("")
    if methods:
        return methods
    method = str(payment.get("method") or "").strip().lower()
    return {method} if method else set()


def card_payment(order) -> bool:
    """Emite quando o pagamento é CARTÃO (crédito/débito). Pronto p/ apontar direto."""
    return bool(_payment_methods_present(order) & {"card", "credit", "debit"})


def eletronic_payment(order) -> bool:
    """Emite quando QUALQUER parte do pagamento é ELETRÔNICA (PIX ou cartão) —
    deixa rastro, então nota. Lê as linhas do pagamento, então a venda mista
    (dinheiro + cartão) emite. Dinheiro puro/externo ficam de fora. Pronto p/
    apontar direto (bom em OR com on_request_or_tax_id)."""
    return bool(_payment_methods_present(order) & {"pix", "card", "credit", "debit"})


def deferred_settlement(order) -> bool:
    """Emite quando a MERCADORIA sai antes de o dinheiro se liquidar.

    Um conceito só, para os dois jeitos de fiado do balcão:
    - pagamento na entrega (COD): o tender nasce ``status="pending"`` e o
      entregador sai com a sacola — a nota tem que ir junto;
    - conta na casa: método ``account``, o acerto vem depois (dias, semanas).

    Lido dos próprios tenders — dado durável do pedido, não do rótulo do canal.
    Fallback sem tenders: ``payment.collection == "on_delivery"`` ou método
    agregado ``account``.
    """
    payment = (order.data or {}).get("payment") or {}
    tenders = payment.get("tenders") or []
    for t in tenders:
        if not isinstance(t, dict) or not t.get("amount_q"):
            continue
        if str(t.get("status") or "").strip().lower() == "pending":
            return True
        if str(t.get("method") or "").strip().lower() == "account":
            return True
    if str(payment.get("collection") or "").strip().lower() == "on_delivery":
        return True
    return str(payment.get("method") or "").strip().lower() == "account"


def payment_methods(*methods: str):
    """Fábrica: emite quando a forma de pagamento está no conjunto.

        emit_eletronico = payment_methods("pix", "card", "credit", "debit")  # dinheiro fica de fora
    """
    allowed = {m.strip().lower() for m in methods if m.strip()}

    def _resolver(order) -> bool:
        method = str(((order.data or {}).get("payment") or {}).get("method") or "").lower()
        return method in allowed

    return _resolver


# ── guardas de ambiente (combine com all_of) ──────────────────────────────────


def not_in_debug(order) -> bool:
    """GUARDA: só emite fora de DEBUG (evita bater na SEFAZ em dev). Combine com all_of,
    ex.: ``all_of(on_request_or_tax_id, not_in_debug)``."""
    from django.conf import settings

    return not bool(getattr(settings, "DEBUG", False))


def only_in_environments(*envs: str):
    """Fábrica-GUARDA: só emite nos ambientes dados (settings.SHOPMAN_ENVIRONMENT).

        prod_ou_staging = only_in_environments("production", "staging")  # nunca em development
    """
    allowed = {e.strip().lower() for e in envs if e.strip()}

    def _resolver(order) -> bool:
        from django.conf import settings

        return str(getattr(settings, "SHOPMAN_ENVIRONMENT", "")).strip().lower() in allowed

    return _resolver


# ── fulfillment ───────────────────────────────────────────────────────────────


def fulfillment_types(*types: str):
    """Fábrica: emite conforme o tipo de entrega/retirada.

        so_entrega = fulfillment_types("delivery")   # emite na entrega, não no balcão
    """
    allowed = {t.strip().lower() for t in types if t.strip()}

    def _resolver(order) -> bool:
        ft = str((order.data or {}).get("fulfillment_type") or "").lower()
        return ft in allowed

    return _resolver
