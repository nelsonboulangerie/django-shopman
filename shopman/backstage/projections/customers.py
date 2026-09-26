"""Clientes no Gestor — lista, ficha, prévia da unificação e trilha do desfazer.

Por que existe: o cadastro do iFood (``IF-*``) nasce sem telefone — o iFood
manda o 0800 da central, e gravá-lo daria à pessoa o número de um terceiro — e
até 19/09/2026 nascia um por PEDIDO. Unificar só existia no Admin e no conflito
de contato do PDV, e nenhum dos dois ACHA o cadastro que ninguém digitou. Esta
é a leitura que o gestor usa para achar, comparar e decidir.

Três regras moldam o formato:

1. **Quem decide é gente.** ``duplicate_hint`` e ``candidates`` são SUGESTÃO,
   com o motivo escrito; nada aqui unifica sozinho.
2. **A prévia é a unificação de verdade, desfeita.** ``build_merge_preview`` lê
   ``MergeService.preview``, que roda o mesmo código da ida num savepoint que
   sempre volta. Contar por fora seria uma segunda régua.
3. **Só cadastro ATIVO é cliente.** O absorvido aparece na ficha dizendo para
   onde foi, e na trilha — nunca na lista, que é a mesma régua do B.I. (#1042)
   e do público do Marketing (#1044).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Count, Q, Value
from django.db.models.functions import Concat, Lower, Trim
from django.utils import timezone
from shopman.utils.monetary import format_money

from shopman.shop.projections.types import Action

logger = logging.getLogger(__name__)

PAGE_SIZE = 30

#: De onde o cadastro veio, na palavra que o gestor usa. Vazio quando o
#: ``source_system`` não diz nada útil (seed, teste) — melhor que inventar.
_SOURCE_LABELS: dict[str, str] = {
    "ifood": "iFood",
    "pdv": "Balcão",
    "manychat": "WhatsApp",
    "doorman": "Loja online",
    "manual": "Cadastro manual",
}

#: Os filtros da lista, na ordem da tela. ``ref`` é contrato; ``label`` é copy.
FILTERS: tuple[tuple[str, str], ...] = (
    ("all", "Todos"),
    ("possible_duplicates", "Possíveis duplicados"),
    ("ifood", "Vindos do iFood"),
    ("no_phone", "Sem telefone"),
)
_FILTER_REFS = {ref for ref, _label in FILTERS}

#: O que a unificação move, na ordem em que a prévia e a trilha contam.
#: Singular e plural porque a frase é lida por gente ("1 contatos" não).
_MOVED: tuple[tuple[str, str, str, str], ...] = (
    ("orders", "migrated_orders", "pedido", "pedidos"),
    ("contact_points", "migrated_contact_points", "contato", "contatos"),
    ("identifiers", "migrated_identifiers", "identificador", "identificadores"),
    ("addresses", "migrated_addresses", "endereço", "endereços"),
    ("external_identities", "migrated_external_identities", "conta vinculada", "contas vinculadas"),
    ("preferences", "migrated_preferences", "preferência", "preferências"),
    ("consents", "migrated_consents", "consentimento", "consentimentos"),
    ("timeline_events", "migrated_timeline_events", "evento do histórico", "eventos do histórico"),
)

_IDENTITY_FIELD_LABELS: dict[str, str] = {
    "document": "CPF",
    "birthday": "Aniversário",
    "first_name": "Nome",
    "last_name": "Sobrenome",
    "phone": "Telefone",
    "email": "E-mail",
}

_IDENTIFIER_LABELS: dict[str, str] = {
    "phone": "Telefone",
    "email": "E-mail",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "whatsapp": "WhatsApp",
    "telegram": "Telegram",
    "manychat": "ManyChat",
    "cpf": "CPF",
    "ifood": "iFood",
}


# ── Contrato ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CustomerFilterOption:
    ref: str
    label: str
    active: bool


@dataclass(frozen=True)
class CustomerRowProjection:
    ref: str
    name: str
    phone_display: str
    email: str
    document_display: str
    source_label: str
    is_ifood: bool
    # "12 pedidos" / "1 pedido" / "Nenhum pedido".
    orders_label: str
    # "há 12 dias" — vazio sem pedido.
    last_order_display: str
    # Motivo da suspeita, quando há: "Mesmo nome de outro cadastro".
    duplicate_hint: str


@dataclass(frozen=True)
class CustomerListProjection:
    query: str
    filter: str
    filters: tuple[CustomerFilterOption, ...]
    items: tuple[CustomerRowProjection, ...]
    page: int
    page_size: int
    total: int
    has_next: bool
    # "34 clientes" / "Nenhum cliente com esse filtro".
    total_label: str


@dataclass(frozen=True)
class CustomerIdentifierProjection:
    type_label: str
    value: str


@dataclass(frozen=True)
class CustomerOrderRowProjection:
    ref: str
    channel_label: str
    status_label: str
    ordered_at_display: str
    total_display: str


@dataclass(frozen=True)
class CustomerCandidateProjection:
    ref: str
    name: str
    phone_display: str
    document_display: str
    source_label: str
    orders_label: str
    # Por que a tela acha que é a mesma pessoa. Sempre preenchido.
    reason_label: str


@dataclass(frozen=True)
class CustomerDetailProjection:
    ref: str
    name: str
    is_active: bool
    # Absorvido: para onde foi. Vazio no cadastro ativo.
    merged_into_ref: str
    phone_display: str
    email: str
    document_display: str
    birthday_display: str
    source_label: str
    is_ifood: bool
    created_display: str
    notes: str
    orders_label: str
    total_spent_display: str
    last_order_display: str
    identifiers: tuple[CustomerIdentifierProjection, ...]
    addresses: tuple[str, ...]
    recent_orders: tuple[CustomerOrderRowProjection, ...]
    candidates: tuple[CustomerCandidateProjection, ...]
    actions: tuple[Action, ...]


@dataclass(frozen=True)
class MergeSideProjection:
    ref: str
    name: str
    phone_display: str
    document_display: str
    source_label: str
    orders_label: str


@dataclass(frozen=True)
class MergeMoveProjection:
    ref: str
    count: int
    label: str


@dataclass(frozen=True)
class MergeFillProjection:
    field_label: str
    value: str


@dataclass(frozen=True)
class MergePreviewProjection:
    # Quem SAI (fica desativado) e quem FICA (recebe tudo).
    source: MergeSideProjection
    target: MergeSideProjection
    moves: tuple[MergeMoveProjection, ...]
    fills: tuple[MergeFillProjection, ...]
    loyalty_label: str
    # A frase que resume o gesto antes do "Unificar".
    summary: str
    undo_notice: str
    actions: tuple[Action, ...]


@dataclass(frozen=True)
class MergeAuditRowProjection:
    id: str
    source_ref: str
    target_ref: str
    target_name: str
    actor: str
    merged_at_display: str
    status: str
    status_label: str
    moved_label: str
    can_undo: bool
    # "Dá para desfazer por mais 6h12" / "Desfeita por ana em 24/09 às 10:00".
    undo_label: str


@dataclass(frozen=True)
class MergeAuditListProjection:
    items: tuple[MergeAuditRowProjection, ...]
    undo_window_hours: int


# ── Leitura ───────────────────────────────────────────────────────────


def _customer_model():
    from shopman.guestman.models import Customer

    return Customer


def _full_name_expr():
    return Lower(Trim(Concat("first_name", Value(" "), "last_name")))


def _name_key(customer) -> str:
    return re.sub(r"\s+", " ", f"{customer.first_name} {customer.last_name}").strip().lower()


def _customer_name(customer) -> str:
    return (getattr(customer, "name", "") or f"{customer.first_name} {customer.last_name}").strip()


def _phone_display(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    return phone or ""


def _document_display(document: str) -> str:
    digits = re.sub(r"\D", "", document or "")
    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    if len(digits) == 14:
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
    return document or ""


def _is_ifood(customer) -> bool:
    return customer.source_system == "ifood" or str(customer.ref).startswith("IF-")


def _source_label(customer) -> str:
    if _is_ifood(customer):
        return "iFood"
    return _SOURCE_LABELS.get(customer.source_system or "", "")


def _orders_label(total: int) -> str:
    if total <= 0:
        return "Nenhum pedido"
    return "1 pedido" if total == 1 else f"{total} pedidos"


def _elapsed_label(moment) -> str:
    from shopman.backstage.projections.order_queue import _elapsed_since_label

    return _elapsed_since_label(moment)


def _local(moment) -> str:
    return timezone.localtime(moment).strftime("%d/%m/%Y às %H:%M") if moment else ""


def _order_stats(refs: list[str]) -> dict[str, tuple[int, object]]:
    """Pedidos e último pedido por cliente, lidos do vínculo canônico do pedido.

    ``Order.data["customer_ref"]`` é o selo que o fluxo de resolução grava (o
    mesmo que ``CustomerOrderHistoryService`` lê). O insight não serve aqui: ele
    é opcional, e "Nenhum pedido" num cadastro com pedido seria mentira.
    """
    if not refs:
        return {}
    try:
        from django.db.models import Max
        from shopman.orderman.models import Order

        rows = (
            Order.objects.filter(data__customer_ref__in=refs)
            .values("data__customer_ref")
            .annotate(n=Count("id"), last=Max("created_at"))
        )
        return {row["data__customer_ref"]: (int(row["n"]), row["last"]) for row in rows}
    except Exception:
        logger.debug("customers.order_stats_failed", exc_info=True)
        return {}


def _duplicate_sets() -> tuple[set[str], set[str]]:
    """Nomes completos e documentos que aparecem em MAIS de um cadastro ativo."""
    Customer = _customer_model()
    active = Customer.objects.filter(is_active=True)
    names = set(
        active.annotate(key=_full_name_expr())
        .values("key")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .values_list("key", flat=True)
    )
    documents = set(
        active.exclude(document="")
        .values("document")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .values_list("document", flat=True)
    )
    return names, documents


def _duplicate_hint(customer, names: set[str], documents: set[str]) -> str:
    if customer.document and customer.document in documents:
        return "Mesmo CPF de outro cadastro"
    if _name_key(customer) in names:
        return "Mesmo nome de outro cadastro"
    return ""


def _search_q(query: str) -> Q:
    q = (
        Q(ref__icontains=query)
        | Q(full_name__icontains=query.lower())
        | Q(document__icontains=query)
        | Q(phone__icontains=query)
        | Q(email__icontains=query)
    )
    # Telefone e CPF moram só com dígitos: "(43) 99999-0000" não acha nada por
    # icontains. Mesma regra da busca do PDV.
    digits = re.sub(r"\D", "", query)
    if len(digits) >= 4 and digits != query:
        q |= Q(document__icontains=digits) | Q(phone__icontains=digits)
    return q


def build_customer_list(query: str = "", filter_ref: str = "all", page: int = 1) -> CustomerListProjection:
    Customer = _customer_model()
    query = (query or "").strip()
    filter_ref = filter_ref if filter_ref in _FILTER_REFS else "all"
    page = max(int(page or 1), 1)

    qs = Customer.objects.filter(is_active=True).annotate(full_name=_full_name_expr())
    names, documents = _duplicate_sets()

    if filter_ref == "no_phone":
        qs = qs.filter(phone="")
    elif filter_ref == "ifood":
        qs = qs.filter(Q(source_system="ifood") | Q(ref__startswith="IF-"))
    elif filter_ref == "possible_duplicates":
        qs = qs.filter(Q(full_name__in=names) | Q(document__in=documents))
    if query:
        qs = qs.filter(_search_q(query))

    # Duplicados em sequência: quem está comparando lê os dois lado a lado.
    ordering = ("full_name", "ref") if filter_ref == "possible_duplicates" else ("-created_at", "ref")
    total = qs.count()
    start = (page - 1) * PAGE_SIZE
    customers = list(qs.order_by(*ordering)[start:start + PAGE_SIZE])
    stats = _order_stats([customer.ref for customer in customers])

    items = []
    for customer in customers:
        count, last = stats.get(customer.ref, (0, None))
        items.append(
            CustomerRowProjection(
                ref=customer.ref,
                name=_customer_name(customer),
                phone_display=_phone_display(customer.phone),
                email=customer.email or "",
                document_display=_document_display(customer.document),
                source_label=_source_label(customer),
                is_ifood=_is_ifood(customer),
                orders_label=_orders_label(count),
                last_order_display=_elapsed_label(last),
                duplicate_hint=_duplicate_hint(customer, names, documents),
            )
        )

    if total:
        total_label = "1 cliente" if total == 1 else f"{total} clientes"
    elif query or filter_ref != "all":
        total_label = "Nenhum cliente com essa busca"
    else:
        total_label = "Nenhum cliente cadastrado"

    return CustomerListProjection(
        query=query,
        filter=filter_ref,
        filters=tuple(CustomerFilterOption(ref=ref, label=label, active=ref == filter_ref) for ref, label in FILTERS),
        items=tuple(items),
        page=page,
        page_size=PAGE_SIZE,
        total=total,
        has_next=start + PAGE_SIZE < total,
        total_label=total_label,
    )


def _ifood_customer_ids(customer_ref: str) -> set[str]:
    try:
        from shopman.orderman.models import Order

        values = (
            Order.objects.filter(data__customer_ref=customer_ref)
            .values_list("data__customer__ifood_customer_id", flat=True)[:200]
        )
        return {str(value) for value in values if value}
    except Exception:
        logger.debug("customers.ifood_ids_failed ref=%s", customer_ref, exc_info=True)
        return set()


def _refs_sharing_ifood_customer(customer_ref: str) -> set[str]:
    """Outros cadastros cujos pedidos trazem o MESMO ``customer.id`` do iFood.

    É a evidência mais forte que existe para um ``IF-*``: o iFood diz que é a
    mesma pessoa. Só existe em pedido a partir de 19/09/2026 (quando a ingestão
    passou a guardar o ``customer.id``); o ``IF-*`` mais antigo não tem esse
    rastro, e para ele sobram nome e CPF.
    """
    ids = _ifood_customer_ids(customer_ref)
    if not ids:
        return set()
    try:
        from shopman.orderman.models import Order

        refs = (
            Order.objects.filter(data__customer__ifood_customer_id__in=ids)
            .exclude(data__customer_ref=customer_ref)
            .values_list("data__customer_ref", flat=True)[:50]
        )
        return {str(ref) for ref in refs if ref}
    except Exception:
        logger.debug("customers.ifood_siblings_failed ref=%s", customer_ref, exc_info=True)
        return set()


def build_customer_candidates(customer) -> tuple[CustomerCandidateProjection, ...]:
    """Quem PODE ser a mesma pessoa — e por quê. Sugestão, nunca decisão."""
    Customer = _customer_model()
    reasons: dict[str, str] = {}

    for ref in _refs_sharing_ifood_customer(customer.ref):
        reasons.setdefault(ref, "Mesmo cliente no iFood")

    others = Customer.objects.filter(is_active=True).exclude(pk=customer.pk)
    if customer.document:
        for ref in others.filter(document=customer.document).values_list("ref", flat=True)[:10]:
            reasons.setdefault(ref, "Mesmo CPF")
    if customer.email:
        for ref in others.filter(email__iexact=customer.email).values_list("ref", flat=True)[:10]:
            reasons.setdefault(ref, "Mesmo e-mail")
    key = _name_key(customer)
    if key:
        for ref in (
            others.annotate(full_name=_full_name_expr()).filter(full_name=key).values_list("ref", flat=True)[:10]
        ):
            reasons.setdefault(ref, "Mesmo nome")

    if not reasons:
        return ()
    found = {c.ref: c for c in others.filter(ref__in=list(reasons))}
    stats = _order_stats(list(found))
    candidates = []
    for ref, reason in reasons.items():
        other = found.get(ref)
        if other is None:
            continue
        candidates.append(
            CustomerCandidateProjection(
                ref=other.ref,
                name=_customer_name(other),
                phone_display=_phone_display(other.phone),
                document_display=_document_display(other.document),
                source_label=_source_label(other),
                orders_label=_orders_label(stats.get(other.ref, (0, None))[0]),
                reason_label=reason,
            )
        )
    return tuple(candidates)


def _merged_into(customer) -> str:
    try:
        from shopman.guestman.contrib.merge.models import MergeAudit, MergeStatus

        audit = (
            MergeAudit.objects.filter(source_ref=customer.ref, status=MergeStatus.COMPLETED)
            .order_by("-merged_at")
            .first()
        )
        return audit.target_ref if audit else ""
    except Exception:
        logger.debug("customers.merged_into_failed ref=%s", customer.ref, exc_info=True)
        return ""


def _channel_names(refs: set[str]) -> dict[str, str]:
    try:
        from shopman.shop.models import Channel

        return dict(Channel.objects.filter(ref__in=refs).values_list("ref", "name"))
    except Exception:
        return {}


def _status_label(status: str) -> str:
    try:
        from shopman.orderman.models import Order

        label = dict(Order.Status.choices).get(status, status)
        return str(label).capitalize()
    except Exception:
        return status


def build_customer_detail(ref: str) -> CustomerDetailProjection | None:
    Customer = _customer_model()
    customer = Customer.objects.filter(ref=ref).first()
    if customer is None:
        return None

    stats_count, stats_spent, stats_last = 0, 0, None
    recent: list = []
    try:
        from shopman.orderman.services import CustomerOrderHistoryService

        stats = CustomerOrderHistoryService.get_customer_stats(customer.ref)
        stats_count, stats_spent, stats_last = stats.total_orders, stats.total_spent_q, stats.last_order_at
        recent = CustomerOrderHistoryService.list_customer_orders(customer.ref, limit=10)
    except Exception:
        logger.debug("customers.history_failed ref=%s", ref, exc_info=True)

    channels = _channel_names({record.channel_ref for record in recent})
    recent_orders = tuple(
        CustomerOrderRowProjection(
            ref=record.order_ref,
            channel_label=channels.get(record.channel_ref, record.channel_ref),
            status_label=_status_label(record.status),
            ordered_at_display=_local(record.ordered_at),
            total_display=f"R$ {format_money(int(record.total_q or 0))}",
        )
        for record in recent
    )

    identifiers: tuple[CustomerIdentifierProjection, ...] = ()
    try:
        from shopman.guestman.contrib.identifiers.models import CustomerIdentifier

        identifiers = tuple(
            CustomerIdentifierProjection(
                type_label=_IDENTIFIER_LABELS.get(ident.identifier_type, ident.identifier_type),
                value=ident.identifier_value,
            )
            for ident in CustomerIdentifier.objects.filter(customer=customer).order_by("identifier_type")
        )
    except ImportError:
        pass

    addresses = tuple(
        str(address.formatted_address)
        for address in customer.addresses.all().order_by("-is_default", "pk")[:5]
        if address.formatted_address
    )

    from shopman.backstage.projections.order_queue import _customer_registry_fields

    registry = _customer_registry_fields(customer)
    candidates = build_customer_candidates(customer) if customer.is_active else ()

    actions: tuple[Action, ...] = ()
    if customer.is_active:
        actions = (
            Action(
                ref="merge_preview",
                kind="query",
                label="Ver o que muda",
                priority="secondary",
                method="GET",
                href="/api/v1/backstage/customers/merge/preview/",
                payload_schema={"required": ["source_ref", "target_ref"]},
            ),
        )

    return CustomerDetailProjection(
        ref=customer.ref,
        name=_customer_name(customer),
        is_active=bool(customer.is_active),
        merged_into_ref="" if customer.is_active else _merged_into(customer),
        phone_display=_phone_display(customer.phone),
        email=customer.email or "",
        document_display=_document_display(customer.document),
        birthday_display=str(registry.get("birthday_display") or ""),
        source_label=_source_label(customer),
        is_ifood=_is_ifood(customer),
        created_display=_local(customer.created_at),
        notes=str(customer.notes or "").strip(),
        orders_label=_orders_label(stats_count),
        total_spent_display=f"R$ {format_money(int(stats_spent))}" if stats_spent else "",
        last_order_display=_elapsed_label(stats_last),
        identifiers=identifiers,
        addresses=addresses,
        recent_orders=recent_orders,
        candidates=candidates,
        actions=actions,
    )


def _side(customer) -> MergeSideProjection:
    count = _order_stats([customer.ref]).get(customer.ref, (0, None))[0]
    return MergeSideProjection(
        ref=customer.ref,
        name=_customer_name(customer),
        phone_display=_phone_display(customer.phone),
        document_display=_document_display(customer.document),
        source_label=_source_label(customer),
        orders_label=_orders_label(count),
    )


def _fill_value(field: str, raw) -> str:
    if field == "document":
        return _document_display(str(raw or ""))
    if field == "phone":
        return _phone_display(str(raw or ""))
    if field == "birthday" and raw:
        try:
            year, month, day = str(raw)[:10].split("-")
            return f"{day}/{month}/{year}"
        except ValueError:
            return str(raw)
    return str(raw or "")


def build_merge_preview(source, target, preview) -> MergePreviewProjection:
    """``preview`` é o ``MergePreview`` do Guestman — a unificação feita e desfeita."""
    from shopman.guestman.contrib.merge.models import MergeAudit

    moves = tuple(
        MergeMoveProjection(ref=ref, count=count, label=f"{count} {singular if count == 1 else plural}")
        for ref, attr, singular, plural in _MOVED
        if (count := int(getattr(preview, attr, 0) or 0))
    )
    filled = dict(preview.identity_filled or {})
    fills: list[MergeFillProjection] = []
    # O nome anda inteiro: uma linha só, não "Nome" e "Sobrenome" separados.
    if "first_name" in filled or "last_name" in filled:
        fills.append(
            MergeFillProjection(
                field_label="Nome",
                value=f"{filled.pop('first_name', '')} {filled.pop('last_name', '')}".strip(),
            )
        )
    for field, raw in filled.items():
        fills.append(MergeFillProjection(field_label=_IDENTITY_FIELD_LABELS.get(field, field), value=_fill_value(field, raw)))

    loyalty_label = ""
    if preview.loyalty_merged:
        points = int(preview.loyalty_points_absorbed or 0)
        loyalty_label = (
            f"{points} {'ponto' if points == 1 else 'pontos'} de fidelidade somam no cadastro que fica"
            if points
            else "A conta de fidelidade é somada no cadastro que fica"
        )

    source_name = _customer_name(source)
    target_name = _customer_name(target)
    return MergePreviewProjection(
        source=_side(source),
        target=_side(target),
        moves=moves,
        fills=tuple(fills),
        loyalty_label=loyalty_label,
        summary=(
            f"{source_name} ({source.ref}) deixa de existir como cadastro separado. "
            f"Tudo o que é dele passa para {target_name} ({target.ref})."
        ),
        undo_notice=(
            f"Dá para desfazer por {MergeAudit.UNDO_WINDOW_HOURS} horas, em Clientes › Unificações. "
            "Os pontos de fidelidade somados não voltam sozinhos."
        ),
        actions=(
            Action(
                ref="merge",
                kind="mutation",
                label="Unificar",
                priority="primary",
                method="POST",
                href="/api/v1/backstage/customers/merge/",
                payload_schema={"required": ["source_ref", "target_ref"]},
                idempotency="required",
            ),
        ),
    )


def _remaining(deadline) -> str:
    seconds = int((deadline - timezone.now()).total_seconds())
    if seconds <= 0:
        return ""
    hours, minutes = divmod(seconds // 60, 60)
    return f"{hours}h{minutes:02d}" if hours else f"{minutes}min"


def build_merge_audit_list(limit: int = 50) -> MergeAuditListProjection:
    from shopman.guestman.contrib.merge.models import MergeAudit, MergeStatus

    audits = list(MergeAudit.objects.order_by("-merged_at")[:limit])
    full_names = {
        customer.ref: _customer_name(customer)
        for customer in _customer_model().objects.filter(ref__in={audit.target_ref for audit in audits})
    }
    status_labels = dict(MergeStatus.choices)
    items = []
    for audit in audits:
        moved = [
            f"{count} {singular if count == 1 else plural}"
            for _ref, attr, singular, plural in _MOVED
            if attr != "migrated_orders" and (count := int(getattr(audit, attr, 0) or 0))
        ]
        orders = len((audit.snapshot or {}).get("orders") or [])
        if orders:
            moved.insert(0, f"{orders} {'pedido' if orders == 1 else 'pedidos'}")

        can_undo = bool(audit.can_undo)
        if can_undo:
            undo_label = f"Dá para desfazer por mais {_remaining(audit.undo_deadline)}"
        elif audit.status == MergeStatus.REVERTED:
            who = f" por {audit.reverted_by}" if audit.reverted_by else ""
            undo_label = f"Desfeita{who} em {_local(audit.reverted_at)}" if audit.reverted_at else f"Desfeita{who}"
        elif audit.status == MergeStatus.COMPLETED:
            undo_label = f"O prazo para desfazer terminou em {_local(audit.merged_at + timedelta(hours=MergeAudit.UNDO_WINDOW_HOURS))}"
        else:
            undo_label = ""

        items.append(
            MergeAuditRowProjection(
                id=str(audit.pk),
                source_ref=audit.source_ref,
                target_ref=audit.target_ref,
                target_name=full_names.get(audit.target_ref, ""),
                actor=audit.actor or "",
                merged_at_display=_local(audit.merged_at),
                status=str(audit.status),
                status_label=str(status_labels.get(audit.status, audit.status)),
                moved_label=", ".join(moved) if moved else "Nada além do próprio cadastro",
                can_undo=can_undo,
                undo_label=undo_label,
            )
        )
    return MergeAuditListProjection(items=tuple(items), undo_window_hours=MergeAudit.UNDO_WINDOW_HOURS)
