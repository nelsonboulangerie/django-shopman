"""POSProjection — read models for the POS terminal (Fase 5).

Translates product listings, collections, and cash session state into
immutable projections for the POS page. Replaces the inline ``_load_products``
logic from ``shopman.backstage.views.pos``.

Never imports from ``shopman.backstage.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.conf import settings
from django.utils import timezone
from shopman.offerman.models import Collection, Product
from shopman.orderman.models import Session
from shopman.utils.monetary import format_money

from shopman.backstage.constants import POS_CHANNEL_REF
from shopman.backstage.presentation.status import payment_method_label
from shopman.backstage.services.integration_readiness import (
    build_provider_readiness,
    focus_nfe_readiness,
)
from shopman.shop.projections.channel_policy import resolve_channel_policy
from shopman.shop.projections.types import (
    Action,
    AddressAutocompleteProjection,
    SavedAddressProjection,
)
from shopman.shop.services.pos_intent import (
    POS_SALE_INTENT_PAYLOAD_KEYS,
    POS_SALE_INTENT_RECEIPT_CHANNELS,
    POS_SALE_INTENT_VERSION,
)

logger = logging.getLogger(__name__)


# ── Projections ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class POSProductProjection:
    """A single product tile in the POS grid."""

    sku: str
    name: str
    price_q: int
    price_display: str
    collection_ref: str
    image_url: str = ""


@dataclass(frozen=True)
class POSCollectionProjection:
    """A collection tab in the POS filter bar."""

    ref: str
    name: str


@dataclass(frozen=True)
class POSPaymentMethodProjection:
    """A payment method option in the POS."""

    ref: str
    label: str


@dataclass(frozen=True)
class POSFulfillmentOptionProjection:
    """A fulfillment option the POS is allowed to submit."""

    ref: str
    label: str
    description: str
    requires_address: bool


@dataclass(frozen=True)
class POSPaymentCollectionProjection:
    """Where payment is collected for a POS sale."""

    ref: str
    label: str
    description: str
    fulfillment_types: tuple[str, ...]
    payment_method_refs: tuple[str, ...]


@dataclass(frozen=True)
class POSCheckoutOptionProjection:
    """A stable option value accepted by the POS sale intent."""

    ref: str
    label: str
    description: str = ""


@dataclass(frozen=True)
class POSCheckoutFieldProjection:
    """A payload field a POS surface may collect during checkout."""

    ref: str
    payload_key: str
    section_ref: str
    label: str
    input_type: str
    required: bool = False
    required_when: dict[str, object] = field(default_factory=dict)
    placeholder: str = ""
    help_text: str = ""
    max_length: int = 0
    options: tuple[POSCheckoutOptionProjection, ...] = ()
    capability_ref: str = ""


@dataclass(frozen=True)
class POSCheckoutSectionProjection:
    """Logical checkout section independent from any concrete UI layout."""

    ref: str
    label: str
    description: str
    field_refs: tuple[str, ...]


@dataclass(frozen=True)
class POSCheckoutContractProjection:
    """Canonical headless checkout contract for POS operator surfaces."""

    intent_version: str
    allowed_payload_keys: tuple[str, ...]
    sections: tuple[POSCheckoutSectionProjection, ...]
    fields: tuple[POSCheckoutFieldProjection, ...]
    receipt_channels: tuple[POSCheckoutOptionProjection, ...]
    tender_methods: tuple[POSCheckoutOptionProjection, ...]
    cash_tender_delta_presets_q: tuple[int, ...]
    discount_types: tuple[POSCheckoutOptionProjection, ...]
    discount_reasons: tuple[POSCheckoutOptionProjection, ...]
    customer_memory_actions: tuple[POSCheckoutOptionProjection, ...]
    capabilities: dict[str, object]


@dataclass(frozen=True)
class POSChangeRequestProjection:
    """Um pedido de troco pendente, à espera de alguém trazer.

    Existe para o troco não sair andando: o operador pede, o gerente traz, e a
    troca acontece no balcão à vista de todos, em vez de alguém atravessar a
    loja com dinheiro por um trajeto que a câmera cobre só em parte.

    ⚠️ Não carrega nada de fechamento. Trocar dinheiro é net zero — o total da
    gaveta não muda — e um valor daqui perto do esperado convidaria a próxima
    tela a somar os dois.
    """

    ref: str
    amount_q: int
    amount_display: str
    #: As cédulas/moedas pedidas, em centavos, do maior para o menor. Vazio é um
    #: pedido completo ("me traz R$ 100"): a lista refina, não obriga.
    denominations: tuple[int, ...]
    note: str
    requested_by: str
    requested_at: str


@dataclass(frozen=True)
class POSPendingCashRefundProjection:
    """Um pedido cancelado cujo dinheiro ainda não saiu de nenhuma gaveta.

    Cancelar não é devolver: o gestor cancela às 22h e ninguém abriu gaveta. A
    pendência fica visível na antesala até alguém com turno aberto entregar o
    dinheiro ("Devolver"), e só então o Payman e o livro registram a devolução.
    """

    order_ref: str
    amount_q: int
    amount_display: str
    customer_name: str
    cancelled_at: str  # ISO datetime, "" quando o pedido não guarda


@dataclass(frozen=True)
class POSCashRuntimeProjection:
    """Active cash runtime resolved for the current operator surface."""

    has_open_shift: bool
    shift_id: int | None
    terminal_ref: str
    terminal_label: str
    operator_username: str
    opened_at: str
    # Dois valores: "open" e "closed". Houve um terceiro, `terminal_occupied`,
    # com quatro campos de bloqueio ao lado — de quando a custódia era da pessoa
    # e a gaveta podia estar "ocupada por outra". Saíram inteiros: com a custódia
    # na gaveta não há bloqueio a comunicar.
    status: str = "closed"
    # O operador atual pode ver a APURAÇÃO (esperado, contado, diferença)?
    #
    # Quem sabe o esperado não conta às cegas: confere um gabarito. O balcão
    # opera o turno inteiro sem isso, e o gerente também — `setup_groups` não dá
    # `audit_shift` a ele. Sai `false` para quase todo mundo, de propósito.
    can_audit_cash: bool = False
    # Só os PENDENTES, e o nome diz isso: atendido e cancelado ficam na trilha do
    # turno, não na tela. Uma lista chamada `change_requests` que mostrasse tudo
    # faria o balcão procurar troco para pedido já resolvido.
    pending_change_requests: tuple[POSChangeRequestProjection, ...] = ()
    # Devoluções em dinheiro que esperam uma gaveta aberta. Aparecem em todo
    # turno aberto do canal (não são "deste turno": são do caixa), porque quem
    # estiver com a gaveta aberta é quem vai devolver.
    pending_cash_refunds: tuple[POSPendingCashRefundProjection, ...] = ()
    # Contas na casa com saldo em aberto: quem está com a gaveta aberta é quem
    # recebe o acerto (em dinheiro entra no livro dele; pix/cartão é atestado).
    account_balances: tuple[POSAccountBalanceProjection, ...] = ()


@dataclass(frozen=True)
class POSCustomerMemoryProjection:
    """Consumption memory resolved for an operator-assisted POS customer."""

    total_orders: int
    average_order_display: str
    favorite_product: str
    favorite_item: dict[str, object]
    last_order_items: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class POSCustomerLookupProjection:
    """Customer data a POS surface can prefill without reading Guestman."""

    ref: str
    name: str
    phone: str
    email: str
    #: CPF/CNPJ já conhecido — pré-preenche o "CPF na nota" do checkout. O
    #: operador pode digitar OUTRO na venda (conveniência); o merge no Guestman
    #: é preenche-se-vazio e nunca sobrescreve o cadastro.
    tax_id: str
    #: A faixa de preço do cliente (`PriceTier.ref`). Chamava-se `loyalty_group`, e era o
    #: TERCEIRO nome errado da mesma coisa: fidelidade é o `LoyaltyAccount` (bronze/ouro),
    #: e nada disto tem a ver com ela.
    price_tier: str
    is_staff: bool
    default_address: SavedAddressProjection | None
    saved_addresses: tuple[SavedAddressProjection, ...]
    memory: POSCustomerMemoryProjection
    # Conta na casa (WP-10): o cliente pode comprar "em conta" (só o Admin liga;
    # ``Customer.metadata.house_account``) e quanto deve hoje (derivado do Payman).
    # Sem a flag o PDV nem mostra a opção: dado opcional faz a tela crescer.
    house_account: bool = False
    account_balance_q: int = 0


@dataclass(frozen=True)
class POSAccountBalanceProjection:
    """Um cliente com conta na casa e saldo em aberto (Σ dos intents ``account`` autorizados)."""

    customer_ref: str
    customer_name: str
    balance_q: int
    balance_display: str
    intents: int
    oldest_at: str  # ISO; "" quando não há


@dataclass(frozen=True)
class POSCustomerSearchResult:
    """A single match for the POS customer search (any unique key)."""

    ref: str
    name: str
    phone: str
    document: str
    email: str


@dataclass(frozen=True)
class POSShiftSummaryProjection:
    """Today's shift totals for the POS."""

    count: int
    total_display: str
    pickup_count: int
    delivery_count: int
    # Caixa cego (§2.6): o breakdown esperado (cash/digital) NÃO viaja no payload —
    # a contagem é cega e a conferência (esperado×contado) vive no gestor/Unfold.
    # (Removido com a morte do POS-HTMX legado que o consumia — WP1.)
    last_ref: str
    last_total_display: str
    cod_pending_count: int
    cod_pending_display: str


@dataclass(frozen=True)
class POSTabProjection:
    """A visible POS tab card."""

    ref: str
    display_ref: str
    session_key: str
    state: str
    status_label: str
    status_class: str
    customer_name: str
    customer_phone: str
    item_count: int
    line_count: int
    total_display: str
    last_touched_display: str
    items_preview: str
    # "Disparado + não-pago" anti-fraud signal: an open comanda whose courses
    # already went to the kitchen is, by nature, still unpaid. Derived from
    # Session.data["fired_lines"] — no extra storage.
    fired: bool = False


@dataclass(frozen=True)
class POSProjection:
    """Top-level read model for the POS terminal page."""

    products: tuple[POSProductProjection, ...]
    collections: tuple[POSCollectionProjection, ...]
    payment_methods: tuple[POSPaymentMethodProjection, ...]
    fulfillment_options: tuple[POSFulfillmentOptionProjection, ...]
    payment_collections: tuple[POSPaymentCollectionProjection, ...]
    checkout: POSCheckoutContractProjection
    actions: tuple[Action, ...]
    has_open_cash_session: bool
    cash_runtime: POSCashRuntimeProjection
    terminal_ref: str
    terminal_label: str
    terminal_default_fulfillment_type: str
    terminal_health_status: str
    terminal_components: tuple[object, ...]
    favorite_collection_refs: tuple[str, ...]
    delivery_minimum_q: int
    delivery_minimum_display: str
    fiscal_status: str
    fiscal_label: str
    fiscal_message: str
    operators: tuple[dict, ...] = ()
    # Quem pode AUTORIZAR exceção (sangria, desconto acima do teto). Conjunto
    # diferente de `operators`: operar o PDV e assinar uma exceção são duas
    # permissões distintas, e confundir as duas colocaria o balconista na lista
    # de quem autoriza a própria sangria.
    managers: tuple[dict, ...] = ()
    auto_lock_seconds: int = 60
    # Geometria do rolo declarada pelo terminal (0 = não declarou, e aí o
    # default do CSS do PDV manda). A superfície escreve estes dois valores nas
    # custom properties que o `@page` do recibo lê — ver o print CSS em
    # surfaces/pos-nuxt/app/assets/css/tailwind.css.
    terminal_roll_width_mm: int = 0
    terminal_roll_margin_mm: int = 0
    # Como ESTE balcão abre a gaveta. Vai para a superfície porque quem alcança
    # o agente na loopback é o navegador do balcão, não o servidor.
    cash_drawer: dict = field(default_factory=dict)


# ── Constants ──────────────────────────────────────────────────────────

_POS_PAYMENT_METHOD_REFS = ("cash", "pix", "card", "mixed")
_POS_TENDER_METHOD_REFS = ("cash", "pix", "card", "external")

_PAYMENT_COLLECTIONS = (
    POSPaymentCollectionProjection(
        ref="terminal",
        label="Receber no caixa",
        description="Pagamento confirmado no atendimento de balcão.",
        fulfillment_types=("pickup", "delivery"),
        payment_method_refs=_POS_PAYMENT_METHOD_REFS,
    ),
    POSPaymentCollectionProjection(
        ref="on_delivery",
        label="Receber na entrega",
        description="Disponível apenas para entrega em dinheiro.",
        fulfillment_types=("delivery",),
        payment_method_refs=("cash", "mixed"),
    ),
)


# ── Builders ───────────────────────────────────────────────────────────


def build_pos(*, terminal=None, operator=None) -> POSProjection:
    """Build the POS terminal projection."""
    products = _load_products()

    collections = tuple(
        POSCollectionProjection(ref=c["ref"], name=c["name"])
        for c in Collection.objects.filter(is_active=True, parent__isnull=True)
        .order_by("sort_order", "name")
        .values("ref", "name")
    )

    # A GAVETA primeiro, e o turno vem dela. Antes era o contrário — o turno se
    # resolvia pelo operador e o terminal se deduzia dele —, e era isso que fazia
    # a segunda pessoa do balcão não achar turno nenhum e cair na antessala.
    if terminal is None:
        from shopman.cashman.models import Terminal

        terminal = Terminal.default()
    cash_shift = _active_cash_shift_for_terminal(terminal)
    from shopman.backstage.services.pos_hardware import CashDrawerConfig
    from shopman.backstage.services.pos_terminal import runtime_profile

    runtime = runtime_profile(terminal)
    policy = resolve_channel_policy(POS_CHANNEL_REF)
    delivery_minimum_q = _delivery_minimum_q()
    fiscal_status, fiscal_label, fiscal_message = _fiscal_runtime()

    return POSProjection(
        products=tuple(products),
        collections=collections,
        payment_methods=_payment_methods(),
        fulfillment_options=_fulfillment_options(policy.fulfillment_types),
        payment_collections=_PAYMENT_COLLECTIONS,
        checkout=_checkout_contract(
            fulfillment_types=policy.fulfillment_types,
            delivery_minimum_q=delivery_minimum_q,
            fiscal_status=fiscal_status,
            fiscal_label=fiscal_label,
            fiscal_message=fiscal_message,
        ),
        actions=_pos_actions(),
        has_open_cash_session=bool(cash_shift) if operator is not None else True,
        cash_runtime=_cash_runtime_projection(
            cash_shift,
            runtime,
            operator,
        ),
        terminal_ref=runtime.terminal_ref,
        terminal_label=runtime.terminal_label,
        terminal_default_fulfillment_type=runtime.default_fulfillment_type,
        terminal_health_status=runtime.status,
        terminal_components=runtime.components,
        favorite_collection_refs=runtime.favorite_collection_refs,
        delivery_minimum_q=delivery_minimum_q,
        delivery_minimum_display=f"R$ {format_money(delivery_minimum_q)}" if delivery_minimum_q else "",
        fiscal_status=fiscal_status,
        fiscal_label=fiscal_label,
        fiscal_message=fiscal_message,
        operators=_eligible_operator_cards(),
        managers=_manager_cards(operator),
        auto_lock_seconds=int((getattr(terminal, "metadata", None) or {}).get("auto_lock_seconds", 60)),
        terminal_roll_width_mm=runtime.printer.roll_width_mm,
        terminal_roll_margin_mm=runtime.printer.margin_mm,
        cash_drawer=CashDrawerConfig.from_terminal(terminal).surface_payload(),
    )


def _eligible_operator_cards() -> tuple[dict, ...]:
    """Operators (staff with operate_pos + a PIN) for the lock-screen picker."""
    from shopman.backstage.services.operator import eligible_operators, operator_card

    return tuple(operator_card(u) for u in eligible_operators())


def _manager_cards(operator=None) -> tuple[dict, ...]:
    """Gerentes que podem autorizar exceção, para o diálogo de PIN oferecer a lista.

    ⚠️ Sem ``operator``, a lista mostrava o próprio operador quando ele era
    gerente. A Joyce (grupo Gerente do seed, tem ``operate_pos`` E
    ``adjust_shift``) se escolhia em "Quem autoriza?", digitava o próprio PIN e
    a exceção saía com as duas assinaturas dela. A segunda assinatura existe
    para haver DUAS pessoas; quem opera não se autoriza. O servidor recusa de
    qualquer jeito (``_verify_manager_pin``); esta lista só evita oferecer.

    Existe porque a tela pedia o nome do gerente DIGITADO, e nome digitado erra: o
    servidor resolve o usuário por ``username`` e valida o PIN contra a credencial
    daquela pessoa — a assinatura que fica em ``Entry.approved_by`` do livro. Com a
    lista, o ``username`` sai daqui já certo em vez de sair de um chute do balcão.

    Sai só nome e ``username``. Nada de id, e-mail ou qualquer coisa da credencial:
    esta lista é lida por qualquer terminal com sessão de balcão, e o que ela
    publica vira superfície de ataque.
    """
    from shopman.backstage.services.operator import ADJUST_SHIFT, eligible_operators

    operator_pk = getattr(operator, "pk", None)
    return tuple(
        {
            "username": user.get_username(),
            "name": user.get_full_name().strip() or user.get_username(),
        }
        for user in eligible_operators(perm=ADJUST_SHIFT)
        if operator_pk is None or user.pk != operator_pk
    )


def build_pos_shift_summary(*, channel_ref: str = POS_CHANNEL_REF) -> POSShiftSummaryProjection:
    """Build today's shift summary for the POS."""
    from django.db.models import Sum
    from django.utils import timezone
    from shopman.orderman.models import Order

    today = timezone.localdate()
    qs = Order.objects.filter(
        channel_ref=channel_ref,
        created_at__date=today,
    ).exclude(status="cancelled")

    shift_count = qs.count()
    shift_total_q = qs.aggregate(t=Sum("total_q"))["t"] or 0
    pickup_count = 0
    delivery_count = 0
    cod_pending_count = 0
    cod_pending_q = 0
    for order in qs:
        data = order.data or {}
        if data.get("fulfillment_type") == "delivery":
            delivery_count += 1
        else:
            pickup_count += 1
        payment = data.get("payment") or {}
        if payment.get("collection") == "on_delivery" and not payment.get("cod_settled_at"):
            cod_pending_count += 1
            cod_pending_q += int(order.total_q or 0)

    last_order = qs.order_by("-created_at").first()

    return POSShiftSummaryProjection(
        count=shift_count,
        total_display=format_money(shift_total_q),
        pickup_count=pickup_count,
        delivery_count=delivery_count,
        last_ref=last_order.ref if last_order else "",
        last_total_display=format_money(last_order.total_q) if last_order else "",
        cod_pending_count=cod_pending_count,
        cod_pending_display=format_money(cod_pending_q),
    )


def build_pos_tabs(
    *,
    channel_ref: str = POS_CHANNEL_REF,
    query: str = "",
    limit: int = 80,
) -> tuple[POSTabProjection, ...]:
    """Build POS tab cards with empty/in-use state."""
    from shopman.backstage.models import POSTab

    query_norm = _norm(query)
    sessions = {
        str((session.data or {}).get("tab_ref") or session.handle_ref or "").strip(): session
        for session in Session.objects.filter(
            channel_ref=channel_ref,
            state="open",
        ).filter(handle_type="pos_tab")
    }
    sessions.update({
        str((session.data or {}).get("tab_ref") or "").strip(): session
        for session in Session.objects.filter(
            channel_ref=channel_ref,
            state="open",
            data__has_key="tab_ref",
        )
    })
    sessions = {ref: session for ref, session in sessions.items() if ref}

    tab_displays = {
        row["ref"]: row["label"] or _display_ref(row["ref"])
        for row in POSTab.objects.filter(is_active=True)
        .order_by("ref")
        .values("ref", "label")
    }
    refs = list(tab_displays)
    for ref in sessions:
        if ref not in refs:
            refs.append(ref)

    tabs = []
    for ref in refs:
        session = sessions.get(ref)
        session_display = str(((session.data or {}) if session is not None else {}).get("tab_display") or "").strip()
        tab = _tab_projection(ref=ref, session=session, display_ref=session_display or tab_displays.get(ref, ""))
        if query_norm and query_norm not in _tab_haystack(tab, sessions.get(ref)):
            continue
        tabs.append(tab)

    tabs.sort(key=lambda tab: (tab.state != "in_use", tab.ref))
    return tuple(tabs[:limit])


def build_pos_customer_lookup(phone: str) -> POSCustomerLookupProjection | None:
    """Resolve POS customer lookup as a headless projection."""
    from shopman.shop.projections import customer_context
    from shopman.shop.services import pos as pos_service

    customer = pos_service.resolve_customer(phone)
    if customer is None:
        return None

    name = getattr(customer, "name", "") or f"{getattr(customer, 'first_name', '')} {getattr(customer, 'last_name', '')}".strip()
    tier_ref = customer.price_tier.ref if getattr(customer, "price_tier_id", None) else ""
    summary = customer_history_summary(customer.ref)
    addresses = customer_context.saved_addresses(customer.ref)
    from shopman.shop.services import house_account

    eligible = house_account.is_eligible(customer.ref)
    default_address = next((addr for addr in addresses if addr.is_default), addresses[0] if addresses else None)
    saved_addresses = tuple(_saved_address_projection(addr) for addr in addresses)

    return POSCustomerLookupProjection(
        ref=getattr(customer, "ref", ""),
        name=name,
        phone=getattr(customer, "phone", "") or phone,
        email=getattr(customer, "email", "") or "",
        tax_id=getattr(customer, "document", "") or "",
        price_tier=tier_ref,
        is_staff=tier_ref == "staff",
        default_address=_saved_address_projection(default_address) if default_address else None,
        saved_addresses=saved_addresses,
        memory=POSCustomerMemoryProjection(
            total_orders=int(summary.get("total_orders") or 0),
            average_order_display=format_money(int(summary.get("average_order_q") or 0)) if summary.get("average_order_q") else "",
            favorite_product=str(summary.get("favorite_product") or ""),
            favorite_item=dict(summary.get("favorite_item") or {}),
            last_order_items=tuple(dict(item) for item in (summary.get("last_order_items") or ())),
        ),
        house_account=eligible,
        account_balance_q=house_account.balance_q(customer.ref) if eligible else 0,
    )


def build_pos_customer_search(query: str, limit: int = 8) -> tuple[POSCustomerSearchResult, ...]:
    """Search customers by any unique key (name/phone/CPF/email) for the POS
    customer modal. Light projection (identity only) — the full lookup loads
    memory/addresses once a result is chosen."""
    query = (query or "").strip()
    if len(query) < 2:
        return ()
    from shopman.guestman.services import customer as customer_service

    results: list[POSCustomerSearchResult] = []
    for customer in customer_service.search(query, limit=limit):
        name = getattr(customer, "name", "") or f"{getattr(customer, 'first_name', '')} {getattr(customer, 'last_name', '')}".strip()
        results.append(POSCustomerSearchResult(
            ref=getattr(customer, "ref", ""),
            name=name,
            phone=getattr(customer, "phone", "") or "",
            document=getattr(customer, "document", "") or "",
            email=getattr(customer, "email", "") or "",
        ))
    return tuple(results)


# ── Internals ──────────────────────────────────────────────────────────


def _load_products() -> list[POSProductProjection]:
    """Load products with prices for the POS grid."""
    products: list[POSProductProjection] = []

    try:
        from shopman.offerman.models import ListingItem

        items = (
            ListingItem.objects.filter(
                listing__ref=POS_CHANNEL_REF,
                listing__is_active=True,
                is_published=True,
                is_sellable=True,
            )
            .select_related("product")
            .order_by("product__name")
        )
        for li in items:
            p = li.product
            price_q = li.price_q if li.price_q else p.base_price_q
            products.append(_product_projection(p, price_q))
    except Exception:
        logger.exception("pos_load_products_listing_failed")

    if not products:
        for p in Product.objects.filter(is_published=True, is_sellable=True).order_by("name"):
            products.append(_product_projection(p, p.base_price_q))

    return products


def _payment_methods() -> tuple[POSPaymentMethodProjection, ...]:
    """Return POS tender methods accepted by the canonical POS intent contract."""
    return tuple(
        POSPaymentMethodProjection(
            ref=ref,
            label=payment_method_label(ref),
        )
        for ref in _POS_PAYMENT_METHOD_REFS
    )


def _fulfillment_options(fulfillment_types: tuple[str, ...]) -> tuple[POSFulfillmentOptionProjection, ...]:
    """Expose POS fulfillment choices resolved from channel policy."""
    options = []
    for ref in fulfillment_types:
        if ref == "delivery":
            options.append(POSFulfillmentOptionProjection(
                ref="delivery",
                label="Entrega",
                description="Entrega local com endereço informado pelo operador.",
                requires_address=True,
            ))
        elif ref == "pickup":
            options.append(POSFulfillmentOptionProjection(
                ref="pickup",
                label="Retirada",
                description="Retirada no balcão ou consumo local.",
                requires_address=False,
            ))
    return tuple(options)


def _pos_actions() -> tuple[Action, ...]:
    """Canonical POS mutations consumed by headless operator surfaces."""
    return (
        Action(
            ref="create_tab",
            kind="mutation",
            label="Cadastrar comanda",
            priority="quiet",
            method="POST",
            href="/api/v1/backstage/pos/tabs/",
            payload_schema={"required": ["tab_ref"], "optional": ["label"]},
            idempotency="none",
        ),
        Action(
            ref="open_tab",
            kind="mutation",
            label="Abrir comanda",
            priority="secondary",
            method="POST",
            href="/api/v1/backstage/pos/tabs/{tab_ref}/open/",
            payload_schema={"path": {"tab_ref": "string"}},
        ),
        Action(
            ref="save_tab",
            kind="mutation",
            label="Salvar comanda",
            priority="secondary",
            method="POST",
            href="/api/v1/backstage/pos/tabs/save/",
            payload_schema={
                "required": ["tab_session_key", "items"],
                "optional": ["customer_name", "customer_phone", "fulfillment_type", "payment_method"],
            },
        ),
        Action(
            ref="review_sale",
            kind="mutation",
            label="Revisar checkout",
            priority="secondary",
            method="POST",
            href="/api/v1/backstage/pos/sale/review/",
            payload_schema={
                "required": ["intent_version", "tab_session_key", "items"],
                "optional": POS_SALE_INTENT_PAYLOAD_KEYS,
            },
            idempotency="none",
        ),
        Action(
            ref="close_sale",
            kind="mutation",
            label="Finalizar venda",
            priority="primary",
            method="POST",
            href="/api/v1/backstage/pos/sale/close/",
            payload_schema={
                "required": ["tab_session_key", "items", "payment_method"],
                "optional": [
                    "customer_name",
                    "customer_phone",
                    "customer_tax_id",
                    "customer_email",
                    "customer_memory_action",
                    "fulfillment_type",
                    "delivery_address",
                    "delivery_address_structured",
                    "delivery_date",
                    "delivery_time_slot",
                    "delivery_fee_q",
                    "order_notes",
                    "payment_collection",
                    "payment_tenders",
                    "tendered_amount_q",
                    "issue_fiscal_document",
                    "receipt_channels",
                    "receipt_email",
                    "manual_discount",
                    "manager_approval",
                    "client_request_id",
                ],
            },
            idempotency="required",
        ),
        Action(
            ref="cancel_recent_sale",
            kind="mutation",
            label="Cancelar venda recente",
            priority="secondary",
            method="POST",
            href="/api/v1/backstage/pos/sale/recent/cancel/",
            payload_schema={
                "required": ["order_ref", "manager_approval"],
                "optional": ["reason"],
            },
            confirmation={"style": "destructive"},
        ),
        Action(
            ref="open_cash_shift",
            kind="mutation",
            label="Abrir caixa",
            priority="secondary",
            method="POST",
            href="/api/v1/backstage/pos/cash/open/",
            payload_schema={"optional": ["opening_amount", "terminal_ref"]},
            idempotency="none",
        ),
        Action(
            ref="close_cash_shift",
            kind="mutation",
            label="Fechar caixa",
            priority="secondary",
            method="POST",
            href="/api/v1/backstage/pos/cash/close/",
            payload_schema={"required": ["closing_amount"], "optional": ["notes"]},
            confirmation={"style": "destructive"},
            idempotency="none",
        ),
        Action(
            ref="cash_movement",
            kind="mutation",
            label="Movimento de caixa",
            priority="quiet",
            method="POST",
            href="/api/v1/backstage/pos/cash/movement/",
            payload_schema={"required": ["kind", "amount", "reason"]},
            idempotency="none",
        ),
        Action(
            ref="drawer_open",
            kind="mutation",
            label="Abrir gaveta",
            priority="quiet",
            method="POST",
            href="/api/v1/backstage/pos/cash/drawer-open/",
            payload_schema={"required": ["reason"]},
            idempotency="none",
        ),
        Action(
            ref="drawer_unlock",
            kind="mutation",
            label="Liberar próxima venda com a gaveta aberta",
            priority="quiet",
            method="POST",
            href="/api/v1/backstage/pos/cash/drawer-unlock/",
            payload_schema={"required": ["manager_approval"], "optional": ["drawer_raw"]},
            idempotency="none",
        ),
        Action(
            ref="refund_cash",
            kind="mutation",
            label="Devolver dinheiro de venda cancelada",
            priority="quiet",
            method="POST",
            href="/api/v1/backstage/pos/cash/refund/{order_ref}/",
            payload_schema={"path": {"order_ref": "string"}, "required": ["manager_approval"]},
            idempotency="none",
        ),
        Action(
            ref="settle_account",
            kind="mutation",
            label="Receber acerto de conta do cliente",
            priority="quiet",
            method="POST",
            href="/api/v1/backstage/pos/accounts/{customer_ref}/settle/",
            payload_schema={"path": {"customer_ref": "string"}, "required": ["amount", "method"]},
            idempotency="none",
        ),
        Action(
            ref="request_change",
            kind="mutation",
            label="Pedir troco",
            priority="quiet",
            method="POST",
            href="/api/v1/backstage/pos/cash/change-request/",
            payload_schema={"required": ["kind"], "optional": ["amount", "note"]},
            idempotency="none",
        ),
        Action(
            ref="serve_change_request",
            kind="mutation",
            label="Atender pedido de troco",
            priority="quiet",
            method="POST",
            href="/api/v1/backstage/pos/cash/change-request/{request_ref}/serve/",
            payload_schema={"path": {"request_ref": "string"}, "required": ["manager_approval"]},
            idempotency="none",
        ),
        Action(
            ref="cancel_change_request",
            kind="mutation",
            label="Cancelar pedido de troco",
            priority="quiet",
            method="POST",
            href="/api/v1/backstage/pos/cash/change-request/{request_ref}/cancel/",
            payload_schema={"path": {"request_ref": "string"}},
            idempotency="none",
        ),
        Action(
            ref="customer_lookup",
            kind="query",
            label="Buscar cliente",
            priority="quiet",
            method="GET",
            href="/api/v1/backstage/pos/customer/lookup/?phone={phone}",
            payload_schema={"query": {"phone": "string"}},
            idempotency="none",
        ),
        Action(
            ref="customer_search",
            kind="query",
            label="Buscar cliente",
            priority="quiet",
            method="GET",
            href="/api/v1/backstage/pos/customer/search/?q={query}",
            payload_schema={"query": {"q": "string"}},
            idempotency="none",
        ),
        Action(
            ref="customer_resolve",
            kind="mutation",
            label="Salvar cliente",
            priority="secondary",
            method="POST",
            href="/api/v1/backstage/pos/customer/resolve/",
            payload_schema={"optional": ["customer_name", "customer_phone", "customer_tax_id", "customer_email"]},
            idempotency="required",
        ),
        Action(
            ref="reverse_geocode",
            kind="mutation",
            label="Resolver coordenadas",
            priority="quiet",
            method="POST",
            href="/api/v1/geocode/reverse",
            payload_schema={
                "required": ["lat", "lng"],
                "returns": {"shape": "delivery_address_structured"},
            },
            idempotency="none",
        ),
        Action(
            ref="clear_tab",
            kind="mutation",
            label="Liberar comanda",
            priority="quiet",
            method="DELETE",
            href="/api/v1/backstage/pos/tabs/{session_key}/clear/",
            payload_schema={"path": {"session_key": "string"}},
            confirmation={"style": "destructive"},
        ),
        Action(
            ref="rename_tab",
            kind="mutation",
            label="Renomear comanda",
            priority="quiet",
            method="POST",
            href="/api/v1/backstage/pos/tabs/rename/",
            payload_schema={"required": ["session_key", "new_tab_ref"]},
        ),
        Action(
            ref="move_tab_lines",
            kind="mutation",
            label="Mover itens (transferir/dividir/juntar)",
            priority="quiet",
            method="POST",
            href="/api/v1/backstage/pos/tabs/move-lines/",
            payload_schema={
                "required": ["from_session_key", "line_ids"],
                "optional": ["to_session_key", "to_tab_ref", "close_source_when_empty"],
            },
        ),
        Action(
            ref="fire_tab",
            kind="mutation",
            label="Enviar itens",
            priority="normal",
            method="POST",
            href="/api/v1/backstage/pos/tabs/fire/",
            payload_schema={
                "required": ["session_key"],
                "optional": ["line_ids", "client_request_id"],
            },
            idempotency="client_request_id",
        ),
        Action(
            ref="unfire_tab",
            kind="mutation",
            label="Cancelar envio à cozinha",
            priority="quiet",
            method="POST",
            href="/api/v1/backstage/pos/tabs/unfire/",
            payload_schema={"required": ["session_key", "line_ids"]},
            confirmation={"style": "destructive"},
        ),
    )


def _checkout_contract(
    *,
    fulfillment_types: tuple[str, ...],
    delivery_minimum_q: int,
    fiscal_status: str,
    fiscal_label: str,
    fiscal_message: str,
) -> POSCheckoutContractProjection:
    """Expose the mature POS sale intent as a headless checkout contract."""
    # Import local: o módulo de services do PDV importa projections em outros
    # caminhos, e um import de topo aqui fecharia o ciclo.
    from shopman.backstage.services import pos as pos_service

    # MULTI: imprimir E enviar não competem. "Sem comprovante" não é opção —
    # é nenhum canal marcado.
    receipt_channels = (
        POSCheckoutOptionProjection(ref="print", label="Imprimir"),
        POSCheckoutOptionProjection(ref="email", label="Enviar por e-mail"),
    )
    tender_methods = tuple(
        POSCheckoutOptionProjection(ref=ref, label=payment_method_label(ref))
        for ref in _POS_TENDER_METHOD_REFS
    )
    fields = (
        POSCheckoutFieldProjection(
            ref="customer_phone",
            payload_key="customer_phone",
            section_ref="customer",
            label="WhatsApp",
            input_type="tel",
            placeholder="(43) 99999-0000",
            max_length=80,
        ),
        POSCheckoutFieldProjection(
            ref="customer_name",
            payload_key="customer_name",
            section_ref="customer",
            label="Nome",
            input_type="text",
            placeholder="Nome do cliente",
            max_length=160,
        ),
        POSCheckoutFieldProjection(
            ref="customer_tax_id",
            payload_key="customer_tax_id",
            section_ref="customer",
            label="CPF/CNPJ",
            input_type="tax_id",
            max_length=32,
            capability_ref="fiscal_document",
        ),
        POSCheckoutFieldProjection(
            ref="customer_email",
            payload_key="customer_email",
            section_ref="customer",
            label="E-mail do cliente",
            input_type="email",
            max_length=180,
        ),
        POSCheckoutFieldProjection(
            ref="customer_memory_action",
            payload_key="customer_memory_action",
            section_ref="customer",
            label="Ação de memória",
            input_type="select",
            options=(
                POSCheckoutOptionProjection(ref="favorite_item", label="Adicionar favorito"),
                POSCheckoutOptionProjection(ref="last_order", label="Repetir último pedido"),
            ),
            capability_ref="customer_memory",
        ),
        POSCheckoutFieldProjection(
            ref="fulfillment_type",
            payload_key="fulfillment_type",
            section_ref="fulfillment",
            label="Fulfillment",
            input_type="segmented",
            required=True,
            options=tuple(
                POSCheckoutOptionProjection(ref=ref, label="Entrega" if ref == "delivery" else "Retirada")
                for ref in fulfillment_types
            ),
        ),
        POSCheckoutFieldProjection(
            ref="delivery_address",
            payload_key="delivery_address",
            section_ref="fulfillment",
            label="Endereço de entrega",
            input_type="address_autocomplete",
            required_when={"fulfillment_type": "delivery"},
            placeholder="Rua, número, bairro e referência",
            max_length=400,
            capability_ref="delivery_address_autocomplete",
        ),
        POSCheckoutFieldProjection(
            ref="delivery_address_structured",
            payload_key="delivery_address_structured",
            section_ref="fulfillment",
            label="Endereço estruturado",
            input_type="object",
            required_when={"fulfillment_type": "delivery"},
            help_text="Objeto aceito: formatted_address, route, street_number, neighborhood, city, state_code, postal_code, latitude, longitude, place_id, complement, delivery_instructions, reference.",
            capability_ref="delivery_address_autocomplete",
        ),
        POSCheckoutFieldProjection(
            ref="delivery_date",
            payload_key="delivery_date",
            section_ref="fulfillment",
            label="Data combinada",
            input_type="date",
            max_length=32,
        ),
        POSCheckoutFieldProjection(
            ref="delivery_time_slot",
            payload_key="delivery_time_slot",
            section_ref="fulfillment",
            label="Horário combinado",
            input_type="text",
            placeholder="Ex: 14:00-14:30",
            max_length=80,
        ),
        POSCheckoutFieldProjection(
            ref="delivery_fee_q",
            payload_key="delivery_fee_q",
            section_ref="fulfillment",
            label="Taxa de entrega",
            input_type="money_q",
            required_when={"fulfillment_type": "delivery"},
        ),
        POSCheckoutFieldProjection(
            ref="order_notes",
            payload_key="order_notes",
            section_ref="fulfillment",
            label="Observações do pedido",
            input_type="textarea",
            max_length=500,
        ),
        POSCheckoutFieldProjection(
            ref="payment_method",
            payload_key="payment_method",
            section_ref="payment",
            label="Forma principal",
            input_type="segmented",
            required=True,
            options=tuple(
                POSCheckoutOptionProjection(ref=ref, label=payment_method_label(ref))
                for ref in _POS_PAYMENT_METHOD_REFS
            ),
        ),
        POSCheckoutFieldProjection(
            ref="payment_collection",
            payload_key="payment_collection",
            section_ref="payment",
            label="Recebimento",
            input_type="segmented",
            required=True,
            options=tuple(
                POSCheckoutOptionProjection(ref=collection.ref, label=collection.label, description=collection.description)
                for collection in _PAYMENT_COLLECTIONS
            ),
        ),
        POSCheckoutFieldProjection(
            ref="payment_tenders",
            payload_key="payment_tenders",
            section_ref="payment",
            label="Pagamentos divididos",
            input_type="tender_list",
            required_when={"payment_method": "mixed"},
            capability_ref="split_payment",
        ),
        POSCheckoutFieldProjection(
            ref="tendered_amount_q",
            payload_key="tendered_amount_q",
            section_ref="payment",
            label="Valor recebido",
            input_type="money_q",
            required_when={"payment_method": "cash", "payment_collection": "terminal"},
            capability_ref="cash_change",
        ),
        POSCheckoutFieldProjection(
            ref="issue_fiscal_document",
            payload_key="issue_fiscal_document",
            section_ref="receipt",
            label="Emitir fiscal",
            input_type="boolean",
            capability_ref="fiscal_document",
        ),
        POSCheckoutFieldProjection(
            ref="receipt_channels",
            payload_key="receipt_channels",
            section_ref="receipt",
            label="Comprovante",
            input_type="multi_toggle",
            options=receipt_channels,
        ),
        POSCheckoutFieldProjection(
            ref="receipt_email",
            payload_key="receipt_email",
            section_ref="receipt",
            label="E-mail do comprovante",
            input_type="email",
            required_when={"receipt_channels": "email"},
            max_length=180,
        ),
        POSCheckoutFieldProjection(
            ref="manual_discount",
            payload_key="manual_discount",
            section_ref="approval",
            label="Desconto manual",
            input_type="discount",
            capability_ref="manual_discount",
        ),
        POSCheckoutFieldProjection(
            ref="manager_approval",
            payload_key="manager_approval",
            section_ref="approval",
            label="Aprovação gerencial",
            input_type="credentials",
            required_when={"manual_discount.discount_q": {"gt": _discount_approval_threshold_q()}},
            capability_ref="manager_approval",
        ),
    )
    sections = (
        POSCheckoutSectionProjection(
            ref="customer",
            label="Cliente",
            description="Identificação, WhatsApp e memória de atendimento.",
            field_refs=("customer_phone", "customer_name", "customer_tax_id", "customer_email", "customer_memory_action"),
        ),
        POSCheckoutSectionProjection(
            ref="fulfillment",
            label="Entrega ou retirada",
            description="Campos que viram fulfillment e dados de entrega no Orderman.",
            field_refs=(
                "fulfillment_type",
                "delivery_address",
                "delivery_address_structured",
                "delivery_date",
                "delivery_time_slot",
                "delivery_fee_q",
                "order_notes",
            ),
        ),
        POSCheckoutSectionProjection(
            ref="payment",
            label="Pagamento",
            description="Recebimento no terminal, na entrega, dinheiro e pagamentos divididos.",
            field_refs=("payment_method", "payment_collection", "payment_tenders", "tendered_amount_q"),
        ),
        POSCheckoutSectionProjection(
            ref="receipt",
            label="Fiscal e comprovante",
            description="Dados opcionais para fiscal e comprovante.",
            field_refs=("issue_fiscal_document", "receipt_channels", "receipt_email"),
        ),
        POSCheckoutSectionProjection(
            ref="approval",
            label="Controle comercial",
            description="Desconto manual e aprovação gerencial quando configurada.",
            field_refs=("manual_discount", "manager_approval"),
        ),
    )
    return POSCheckoutContractProjection(
        intent_version=POS_SALE_INTENT_VERSION,
        allowed_payload_keys=POS_SALE_INTENT_PAYLOAD_KEYS,
        sections=sections,
        fields=fields,
        receipt_channels=tuple(option for option in receipt_channels if option.ref in POS_SALE_INTENT_RECEIPT_CHANNELS),
        tender_methods=tender_methods,
        cash_tender_delta_presets_q=(0, 1000, 2000, 5000, 10000),
        discount_types=(
            POSCheckoutOptionProjection(ref="percent", label="Percentual"),
            POSCheckoutOptionProjection(ref="fixed", label="Valor fixo"),
        ),
        discount_reasons=(
            POSCheckoutOptionProjection(ref="cortesia", label="Cortesia"),
            POSCheckoutOptionProjection(ref="fidelidade", label="Fidelidade"),
            POSCheckoutOptionProjection(ref="ajuste_operacional", label="Ajuste operacional"),
            POSCheckoutOptionProjection(ref="qualidade", label="Qualidade"),
        ),
        customer_memory_actions=(
            POSCheckoutOptionProjection(ref="favorite_item", label="Adicionar favorito"),
            POSCheckoutOptionProjection(ref="last_order", label="Repetir último pedido"),
        ),
        capabilities={
            "prepare_checkout_action_ref": "save_tab",
            "review_action_ref": "review_sale",
            "submit_action_ref": "close_sale",
            "customer_lookup_action_ref": "customer_lookup",
            "supports_split_payment": True,
            "supports_cash_change": True,
            "supports_on_delivery_cash": "delivery" in fulfillment_types,
            "supports_customer_lookup": True,
            "supports_customer_memory": True,
            "supports_delivery_address_autocomplete": bool(getattr(settings, "GOOGLE_MAPS_API_KEY", "")),
            "supports_receipt_email": True,
            "supports_manual_discount": True,
            "provider_readiness": tuple(
                item.as_projection()
                for item in build_provider_readiness(mode="runtime")
            ),
            "fiscal_document": fiscal_status,
            "fiscal_label": fiscal_label,
            "fiscal_message": fiscal_message,
            # O toggle 'Nota fiscal' só aparece com adapter configurado E flag da loja on.
            "supports_fiscal_document": _supports_fiscal_document(),
            "delivery_minimum_q": delivery_minimum_q,
            "delivery_minimum_display": f"R$ {format_money(delivery_minimum_q)}" if delivery_minimum_q else "",
            "requires_manager_approval_above_q": _discount_approval_threshold_q(),
            "address_autocomplete": _address_autocomplete_capability(),
            "tab_lifecycle": {
                "create_action_ref": "create_tab",
                "open_action_ref": "open_tab",
                "save_action_ref": "save_tab",
                "clear_action_ref": "clear_tab",
                "tab_ref_format": "free_text",
                "tab_ref_max_length": 64,
                "tab_ref_placeholder": "Mesa, nome ou referência",
                "tab_ref_disallowed_chars": ("/", "\\", "?", "#", "%"),
                "numeric_refs_zero_padded_to": 8,
                "requires_open_tab_for_cart": False,
                "requires_tab_before_save": True,
                "allows_direct_checkout_without_tab": True,
                "allows_operator_tab_creation": True,
                "draft_association_target_states": ("empty",),
                "occupied_tab_selection": "open_existing_not_merge",
            },
            "tab_manipulation": {
                "move_action_ref": "move_tab_lines",
                "rename_action_ref": "rename_tab",
                "allows_transfer": True,
                "allows_split": True,
                "allows_merge": True,
                "freezes_price_on_move": True,
            },
            "kitchen_handoff": {
                "fire_action_ref": "fire_tab",
                "unfire_action_ref": "unfire_tab",
                "progressive": True,
                "per_line_state_key": "fired",
                "fires_whole_tab_when_no_lines": True,
            },
            "cash_management": {
                "open_action_ref": "open_cash_shift",
                "close_action_ref": "close_cash_shift",
                "movement_action_ref": "cash_movement",
                "movement_kinds": ("sangria", "suprimento"),
                # Os motivos que viram botão na tela. SAÍDA pergunta para onde o
                # dinheiro foi; ENTRADA não pergunta nada — "entrada de caixa" já
                # é a resposta inteira, e um campo com uma opção só ensina o
                # balcão a preencher qualquer coisa para passar. Lista vazia na
                # entrada é deliberada, e o servidor cobra o motivo só na saída.
                "movement_reasons": {
                    "sangria": ("Sangria", "Fornecedor"),
                    "suprimento": (),
                },
                # As cédulas e moedas que o balcão pode pedir como troco. Vem do
                # servidor para não existirem duas listas: repetir os números em
                # TypeScript é assinar uma divergência para o dia em que uma
                # moeda sair de circulação.
                "change_denominations": pos_service.CHANGE_DENOMINATIONS,
                "requires_open_shift_for_sale": True,
                "blocks_close_when_offline_queue_pending": True,
            },
            "sale_correction": {
                "cancel_recent_action_ref": "cancel_recent_sale",
                "max_age_minutes": 5,
                "supports_reason": True,
                "requires_manager_approval": True,
                # "preparing" incluso: venda de balcão com fire nasce em preparo.
                "allowed_statuses": ("new", "accepted", "preparing"),
            },
            "idempotent_replay": {
                "request_key": "client_request_id",
                "required_for_close": True,
                "close_action_ref": "close_sale",
                "safe_for_offline_queue": True,
            },
            "customer_lookup": {
                "action_ref": "customer_lookup",
                "lookup_key": "phone",
                "returns_default_address": True,
                "returns_saved_addresses": True,
                "returns_memory": True,
            },
            "live_refresh": {
                "product_projection_refresh": "pos",
                "shift_projection_refresh": "pos.shift",
                "tab_projection_refresh": "pos.tabs",
                "supports_push_updates": False,
            },
        },
    )


def _active_cash_shift_for_terminal(terminal):
    if terminal is None:
        return None
    try:
        from shopman.cashman import services as cash

        return cash.open_shift_for_terminal(terminal)
    except Exception:
        logger.debug("pos_terminal_cash_shift_lookup_failed", exc_info=True)
        return None


def _cash_runtime_projection(cash_shift, runtime, operator) -> POSCashRuntimeProjection:
    """Dois estados só: a gaveta tem turno aberto, ou não tem.

    Existiu um terceiro, ``terminal_occupied`` — "Terminal aberto por marina" —
    de quando a custódia era da pessoa: quem chegava depois não achava turno
    SEU, via a gaveta ocupada por outra, e só passava fechando o caixa dela.
    Com a custódia na gaveta, o turno do terminal É o turno de quem está nele.
    Não há bloqueio a exibir, e o revezamento não pede ritual nenhum.
    """
    from shopman.backstage.permissions import can_audit_cash

    # `can_audit_cash` NÃO é o operador do balcão: esperado e diferença são do
    # Dono (ver setup_groups). Quem conta às cegas não pode conferir o gabarito.
    audita = bool(operator is not None and can_audit_cash(operator))

    if cash_shift is None:
        return POSCashRuntimeProjection(
            has_open_shift=False,
            shift_id=None,
            terminal_ref=runtime.terminal_ref,
            terminal_label=runtime.terminal_label,
            operator_username=getattr(operator, "username", "") if operator is not None else "",
            opened_at="",
            status="closed",
            can_audit_cash=audita,
        )
    return POSCashRuntimeProjection(
        has_open_shift=True,
        shift_id=cash_shift.pk,
        terminal_ref=cash_shift.terminal.ref,
        terminal_label=str(cash_shift.terminal),
        # Quem está operando AGORA, não quem abriu a gaveta de manhã. O nome de
        # quem abriu vive em `cash_shift.opened_by` e aparece na auditoria.
        operator_username=getattr(operator, "username", "") if operator is not None else "",
        opened_at=cash_shift.opened_at.isoformat() if cash_shift.opened_at else "",
        status="open",
        can_audit_cash=audita,
        pending_change_requests=_pending_change_requests(cash_shift),
        pending_cash_refunds=_pending_cash_refunds(cash_shift),
        account_balances=account_balances(),
    )


def account_balances() -> tuple[POSAccountBalanceProjection, ...]:
    """Clientes com conta na casa e saldo em aberto, maior saldo primeiro."""
    from shopman.shop.services import house_account

    return tuple(
        POSAccountBalanceProjection(
            customer_ref=row.customer_ref,
            customer_name=row.customer_name,
            balance_q=row.balance_q,
            balance_display=f"R$ {format_money(row.balance_q)}",
            intents=row.intents,
            oldest_at=row.oldest_at,
        )
        for row in house_account.balances()
    )


def _pending_cash_refunds(cash_shift) -> tuple[POSPendingCashRefundProjection, ...]:
    from shopman.shop.services import payment as payment_service

    return tuple(
        POSPendingCashRefundProjection(
            order_ref=item.order_ref,
            amount_q=item.amount_q,
            amount_display=f"R$ {format_money(item.amount_q)}",
            customer_name=item.customer_name,
            cancelled_at=item.cancelled_at,
        )
        for item in payment_service.pending_cash_refunds(channel_ref=cash_shift.terminal.channel_ref)
    )


def _pending_change_requests(cash_shift) -> tuple[POSChangeRequestProjection, ...]:
    from shopman.backstage.services.pos import pending_change_requests

    # O ``ref`` da tela é o id do lançamento ``change_requested``: é por ele que o
    # balcão atende e cancela (``change-request/<ref>/serve|cancel``).
    return tuple(
        POSChangeRequestProjection(
            ref=str(entry.get("entry_id") or ""),
            amount_q=int(entry.get("amount_q") or 0),
            # Todo pedido tem valor agora, e ele é exato. O guarda do zero fica:
            # linha antiga do livro (o livro é imutável) ainda pode não ter, e
            # "R$ 0,00" na tela pareceria pedido malformado.
            amount_display=(
                f"R$ {format_money(int(entry.get('amount_q') or 0))}"
                if int(entry.get("amount_q") or 0) > 0
                else ""
            ),
            denominations=tuple(int(v) for v in (entry.get("denominations") or [])),
            note=str(entry.get("note") or ""),
            requested_by=str(entry.get("requested_by") or ""),
            requested_at=str(entry.get("requested_at") or ""),
        )
        for entry in pending_change_requests(cash_shift)
    )


def _address_autocomplete_capability() -> AddressAutocompleteProjection:
    api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", "") or ""
    lat, lng = _shop_coordinates()
    return AddressAutocompleteProjection(
        enabled=bool(api_key),
        public_api_key=api_key,
        shop_latitude=lat,
        shop_longitude=lng,
    )


def _shop_coordinates() -> tuple[float | None, float | None]:
    try:
        from shopman.shop.models import Shop

        shop = Shop.objects.order_by("pk").first()
    except Exception:
        logger.debug("pos_shop_coordinates_lookup_failed", exc_info=True)
        return None, None
    if shop is None or shop.latitude is None or shop.longitude is None:
        return None, None
    return float(shop.latitude), float(shop.longitude)


def _saved_address_projection(addr) -> SavedAddressProjection:
    return SavedAddressProjection(
        id=addr.id,
        formatted_address=addr.formatted_address,
        complement=addr.complement,
        label=addr.label,
        is_default=addr.is_default,
        label_key=addr.label_key,
        label_custom=addr.label_custom,
        route=addr.route,
        street_number=addr.street_number,
        neighborhood=addr.neighborhood,
        city=addr.city,
        state_code=addr.state_code,
        postal_code=addr.postal_code,
        latitude=addr.latitude,
        longitude=addr.longitude,
        place_id=addr.place_id,
        delivery_instructions=addr.delivery_instructions,
    )


def _product_projection(product: Product, price_q: int) -> POSProductProjection:
    ci = (
        product.collection_items
        .filter(is_primary=True)
        .select_related("collection")
        .first()
    )

    return POSProductProjection(
        sku=product.sku,
        name=product.name,
        price_q=price_q,
        price_display=f"R$ {format_money(price_q)}",
        collection_ref=ci.collection.ref if ci else "",
        image_url=product.image_url or "",
    )


def _tab_projection(*, ref: str, session: Session | None, display_ref: str = "") -> POSTabProjection:
    display_ref = display_ref or _display_ref(ref)
    if session is None:
        return POSTabProjection(
            ref=ref,
            display_ref=display_ref,
            session_key="",
            state="empty",
            status_label="Livre",
            status_class="badge-neutral",
            customer_name="",
            customer_phone="",
            item_count=0,
            line_count=0,
            total_display="R$ 0,00",
            last_touched_display="",
            items_preview="",
        )

    data = session.data or {}
    customer = data.get("customer") or {}
    items = session.items or []
    last_touched = _parse_dt(data.get("last_touched_at"), fallback=session.opened_at)
    item_count = sum(_qty_int(item.get("qty", 1)) for item in items)
    total_q = sum(
        _qty_int(item.get("qty", 1)) * int(item.get("unit_price_q", 0))
        for item in items
    )
    discount_q = int((data.get("manual_discount") or {}).get("discount_q", 0))

    return POSTabProjection(
        ref=ref,
        display_ref=display_ref,
        session_key=session.session_key,
        state="in_use",
        status_label="Em uso",
        status_class="badge-warning",
        customer_name=str(customer.get("name") or ""),
        customer_phone=str(customer.get("phone") or ""),
        item_count=item_count,
        line_count=len(items),
        total_display=f"R$ {format_money(max(0, total_q - discount_q))}",
        last_touched_display=_format_time(last_touched),
        items_preview=_items_preview(items),
        fired=bool(data.get("fired_lines")),
    )


def _parse_dt(value, *, fallback):
    if not value:
        return fallback
    from django.utils.dateparse import parse_datetime

    parsed = parse_datetime(str(value))
    if parsed is None:
        return fallback
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _format_time(value) -> str:
    return timezone.localtime(value).strftime("%H:%M")


def _qty_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def _items_preview(items: list[dict]) -> str:
    preview = []
    for item in items[:2]:
        qty = _qty_int(item.get("qty", 1))
        name = str(item.get("name") or item.get("sku") or "").strip()
        if not name:
            continue
        preview.append(f"{qty}x {name}")
    if len(items) > 2:
        preview.append(f"+{len(items) - 2}")
    return " · ".join(preview)


def _tab_haystack(tab: POSTabProjection, session: Session | None) -> str:
    item_parts = []
    if session is not None:
        for item in session.items or []:
            item_parts.extend([str(item.get("sku") or ""), str(item.get("name") or "")])
    return _norm(
        " ".join([
            tab.ref,
            tab.display_ref,
            tab.customer_name,
            tab.customer_phone,
            tab.items_preview,
            *item_parts,
        ])
    )


def _display_ref(ref: str) -> str:
    value = str(ref or "").strip()
    if value.isdigit():
        return value.lstrip("0") or "0"
    return value


def _norm(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _delivery_minimum_q() -> int:
    """Resolve the POS-visible delivery minimum from the unified policy source
    (``shop.defaults.rules.delivery_minimum_q``; ``0`` = no minimum)."""
    try:
        from shopman.shop.projections.cart import shop_rule_q

        return shop_rule_q("delivery_minimum_q")
    except Exception:
        logger.debug("pos_delivery_minimum_lookup_failed", exc_info=True)
        return 0


def _discount_approval_threshold_q() -> int:
    """Teto de aprovação do desconto, lido de quem o aplica.

    A projection ANUNCIA a política; quem a aplica é o gate do orquestrador
    (``shop.services.pos.discount_approval_threshold_q``). Ler de lá é o que
    garante que o número mostrado na tela é o mesmo que decide o PIN — quando
    esta função tinha leitura própria, o Admin mudava um e o balcão obedecia o
    outro.
    """
    from shopman.shop.services.pos import discount_approval_threshold_q

    return discount_approval_threshold_q()


def _pos_fiscal_toggle_enabled() -> bool:
    """A loja OFERECE emissão de NFC-e no PDV? Flag de negócio por estabelecimento,
    editável no Admin em ``Shop.defaults['pos']['fiscal_toggle']``.

    Lê de quem é dono da pergunta (``shop.services.pos.fiscal_toggle_enabled``),
    pelo mesmo motivo do teto de desconto logo acima: o deploy check
    ``SHOPMAN_W003`` também pergunta isso, e duas leituras do mesmo dict acabam
    discordando. Combina com o adapter pronto para liberar o toggle 'Nota fiscal'.
    """
    from shopman.shop.services.pos import fiscal_toggle_enabled

    return fiscal_toggle_enabled()


def _supports_fiscal_document() -> bool:
    """O toggle 'Nota fiscal' deve aparecer no PDV? Adapter fiscal configurado E flag da
    loja ligado. Sem adapter OU flag desligado → recurso não aparece."""
    return bool(getattr(settings, "SHOPMAN_FISCAL_ADAPTER", None)) and _pos_fiscal_toggle_enabled()


def _fiscal_runtime() -> tuple[str, str, str]:
    """Return a compact fiscal health tuple for the POS terminal bar."""
    adapter_path = getattr(settings, "SHOPMAN_FISCAL_ADAPTER", None)
    if not adapter_path:
        return ("warning", "Fiscal", "sem adapter")

    if "fiscal_focusnfe.FocusNFeBackend" in str(adapter_path):
        readiness = focus_nfe_readiness(mode="runtime")
        return (readiness.status, readiness.label, readiness.message)

    # Adapter fiscal desconhecido: informar, nunca quebrar a projection do POS.
    return ("warning", "Fiscal", "adapter sem verificação de prontidão")


# ── Open-comanda read-model ──────────────────────────────────────────────
# The read shape the POS surface renders for an open Session (its lines,
# customer, fulfillment, payment intent, per-line discount). Semantic DATA only
# (_q cents, refs, booleans) — no copy/format/HTML. Sibling of POSTabProjection
# (the grid card): same comanda, the "open/edit" view vs the "card" view. POS
# write-side commands stay CQRS-pure (they return the mutated Session); the
# backstage views compose command + this query.


def _is_delivery_fee_item(item: dict) -> bool:
    return bool((item.get("meta") or {}).get("type") == "delivery_fee")


def _int_q(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _tab_payload_line_discount(item: dict) -> dict | None:
    """Surface the operator's per-line manual discount (percent) for restore."""
    manual = (item.get("meta") or {}).get("manual_discount") or {}
    value = manual.get("value")
    if not value:
        return None
    return {"value": value, "reason": manual.get("reason", "cortesia")}


def _manual_discount_originals(session: Session) -> dict[str, int]:
    """Map ``sku -> pre-discount unit price`` for manual per-line discounts.

    Sourced from ``session.pricing["discount"]["items"]``, which the
    DiscountModifier writes precisely because the item-level ``modifiers_applied``
    does NOT survive the session save (extra line fields are stripped on
    ``update_items``). ``original_price_q`` is the price the discount was computed
    against, deterministic per SKU, so a SKU key is unambiguous.
    """
    records = ((session.pricing or {}).get("discount") or {}).get("items") or []
    return {
        rec["sku"]: int(rec["original_price_q"])
        for rec in records
        if rec.get("type") == "manual" and rec.get("sku") and rec.get("original_price_q")
    }


def _tab_line_display_price_q(item: dict, manual_originals: dict[str, int]) -> int:
    """Pre-discount unit price for display AND for restore.

    When a manual per-line discount won, the DiscountModifier baked the discounted
    price into ``unit_price_q``. The cart reloads the PRE-discount price plus the
    discount descriptor, so re-sending applies the discount ONCE — reading back the
    baked price while re-sending the descriptor double-applies it (bug B1-3). The
    original comes from ``session.pricing`` (see ``_manual_discount_originals``),
    never from the item's ``modifiers_applied`` (stripped on save)."""
    manual = (item.get("meta") or {}).get("manual_discount") or {}
    if manual.get("value"):
        original = manual_originals.get(item.get("sku", ""))
        if original:
            return int(original)
    return int(item.get("unit_price_q", 0))


def _tab_payload_payment_tenders(payment: dict) -> list[dict]:
    tenders = payment.get("tenders")
    if not isinstance(tenders, list) or not tenders:
        return []
    method = str(payment.get("method") or "").strip().lower()
    if method == "mixed" or len(tenders) > 1:
        return tenders
    return []


def build_open_tab(session: Session) -> dict:
    """Read-model of an open POS comanda, rendered by the POS surface.

    The stored ``tab_ref``/``tab_display`` are already normalized at open time,
    so they are read back verbatim (no re-normalization).
    """
    data = session.data or {}
    customer = data.get("customer") or {}
    payment = data.get("payment") or {}
    fiscal = data.get("fiscal") or {}
    receipt = data.get("receipt") or {}
    discount = data.get("manual_discount") or {}
    tab_ref = str(data.get("tab_ref") or session.handle_ref or "")
    tab_display = str(data.get("tab_display") or "") or _display_ref(tab_ref)
    fired_lines = set(data.get("fired_lines") or [])
    manual_originals = _manual_discount_originals(session)
    items = [
        {
            "line_id": item.get("line_id", ""),
            "sku": item["sku"],
            "name": item.get("name", item["sku"]),
            "price_q": _tab_line_display_price_q(item, manual_originals),
            "qty": int(item.get("qty", 1)),
            "notes": (item.get("meta") or {}).get("notes", ""),
            "fired": item.get("line_id", "") in fired_lines,
            "discount": _tab_payload_line_discount(item),
            "price_overridden": bool((item.get("meta") or {}).get("price_overridden")),
        }
        for item in (session.items or [])
        if not _is_delivery_fee_item(item)
    ]

    return {
        "session_key": session.session_key,
        "tab_session_key": session.session_key,
        "tab_ref": tab_ref,
        "tab_display": tab_display,
        "items": items,
        "customer_phone": customer.get("phone", ""),
        "customer_name": customer.get("name", ""),
        "customer_ref": customer.get("ref", data.get("customer_ref", "")),
        "price_tier": customer.get("price_tier", ""),
        "customer_tax_id": customer.get("tax_id", ""),
        "customer_email": customer.get("email", ""),
        "fulfillment_type": data.get("fulfillment_type", "pickup") or "pickup",
        "delivery_address": data.get("delivery_address", ""),
        "delivery_address_structured": data.get("delivery_address_structured", {}),
        "delivery_date": data.get("delivery_date", ""),
        "delivery_time_slot": data.get("delivery_time_slot", ""),
        "delivery_fee_q": data.get("delivery_fee_q", 0),
        "order_notes": data.get("order_notes", ""),
        "payment_method": payment.get("method", "cash"),
        "payment_collection": payment.get("collection", "terminal"),
        "payment_tenders": _tab_payload_payment_tenders(payment),
        "tendered_amount_q": "",
        "client_request_id": data.get("client_request_id", (data.get("pos") or {}).get("client_request_id", "")),
        "issue_fiscal_document": bool(fiscal.get("issue_document")),
        "receipt_channels": list(receipt.get("channels") or []),
        "receipt_email": receipt.get("email", ""),
        "discount_type": discount.get("type", "percent"),
        "discount_value": str(discount.get("value", "")) if discount.get("value") else "",
        "discount_reason": discount.get("reason", "cortesia"),
    }


def customer_history_summary(customer_ref: str, *, limit: int = 5) -> dict:
    """Return compact consumption memory for POS lookup surfaces."""
    if not customer_ref:
        return {}
    try:
        from shopman.orderman.services import CustomerOrderHistoryService

        stats = CustomerOrderHistoryService.get_customer_stats(customer_ref)
        recent = CustomerOrderHistoryService.list_customer_orders(customer_ref, limit=limit)
    except Exception:
        logger.exception("pos_customer_history_failed customer_ref=%s", customer_ref)
        return {}

    favorite = ""
    favorite_item: dict = {}
    last_order_items: list[dict] = []
    counts: dict[str, tuple[str, float, int]] = {}
    if recent:
        for item in recent[0].items or []:
            sku = str(item.get("sku") or "")
            if not sku or sku == "__DELIVERY_FEE__":
                continue
            try:
                qty = int(item.get("qty") or 1)
            except (TypeError, ValueError):
                qty = 1
            last_order_items.append({
                "sku": sku,
                "name": str(item.get("name") or sku),
                "qty": max(1, qty),
                "unit_price_q": _int_q(item.get("unit_price_q") or item.get("price_q") or item.get("unit_price") or 0),
            })
    for order in recent:
        for item in order.items or []:
            sku = str(item.get("sku") or "")
            if not sku or sku == "__DELIVERY_FEE__":
                continue
            name = str(item.get("name") or sku)
            try:
                qty = float(item.get("qty") or 1)
            except (TypeError, ValueError):
                qty = 1
            unit_price_q = _int_q(item.get("unit_price_q") or item.get("price_q") or item.get("unit_price") or 0)
            prev_name, prev_qty, prev_price_q = counts.get(sku, (name, 0, unit_price_q))
            counts[sku] = (prev_name or name, prev_qty + qty, prev_price_q or unit_price_q)
    if counts:
        fav_sku, fav_row = max(counts.items(), key=lambda row: row[1][1])
        favorite = fav_row[0]
        favorite_item = {
            "sku": fav_sku,
            "name": fav_row[0],
            "qty": 1,
            "unit_price_q": fav_row[2],
        }

    return {
        "total_orders": stats.total_orders,
        "total_spent_q": stats.total_spent_q,
        "average_order_q": stats.average_order_q,
        "last_order_at": stats.last_order_at,
        "favorite_product": favorite,
        "favorite_item": favorite_item,
        "last_order_items": last_order_items[:8],
    }

    return ("warning", "Fiscal", "adapter customizado")


def build_pos_recent_sales(*, limit: int = 20) -> dict:
    """Últimas vendas do balcão, com o estado FISCAL de cada uma.

    A tela da venda não pode responder "a nota autorizou?" — a emissão é
    assíncrona e a confirmação some quando a próxima venda começa. Esta lista é
    a casa disso: status da NFC-e, reimpressão da DANFE, reenvio por e-mail e
    reprocessamento de falha, para qualquer venda recente, a qualquer hora.
    Reusa a MESMA projeção fiscal do gestor (``order_queue._fiscal_status``) —
    um estado, duas superfícies, zero divergência.
    """
    from shopman.orderman.models import Order

    from shopman.backstage.projections.order_queue import _fiscal_status

    since = timezone.now() - timezone.timedelta(hours=24)
    orders = (
        Order.objects.filter(channel_ref=POS_CHANNEL_REF, created_at__gte=since)
        .prefetch_related("items")
        .order_by("-created_at")[: max(1, min(int(limit), 50))]
    )

    sales = []
    for order in orders:
        data = order.data or {}
        fiscal_status, fiscal_label, fiscal_links = _fiscal_status(order)
        payment = data.get("payment") or {}
        methods = [
            str(t.get("method") or "")
            for t in (payment.get("tenders") or [])
            if isinstance(t, dict) and t.get("amount_q")
        ] or [str(payment.get("method") or "")]
        receipt = data.get("receipt") or {}
        sales.append({
            "order_ref": order.ref,
            "status": str(order.status),
            "created_at_display": timezone.localtime(order.created_at).strftime("%H:%M"),
            "total_display": format_money(int(order.total_q or 0)),
            "payment_label": " + ".join(payment_method_label(m) for m in methods if m),
            "customer_name": str((data.get("customer") or {}).get("name") or ""),
            "fiscal_status": fiscal_status,
            "fiscal_label": fiscal_label,
            "fiscal_links": list(fiscal_links),
            "nfce_number": str(data.get("nfce_number") or ""),
            "email_sent": bool(data.get("nfce_email_sent_at")),
            "receipt_email": str(receipt.get("email") or (data.get("customer") or {}).get("email") or ""),
            # As ações seguem o FATO (a nota), nunca o toggle do operador.
            "can_print_danfe": bool(data.get("nfce_access_key")),
            "can_resend_email": bool(data.get("nfce_access_key")),
            "can_requeue_fiscal": fiscal_status == "failed",
        })
    return {"sales": sales}
