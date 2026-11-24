"""A sacola passa de um canal a outro antes do pedido: uma viva por vez (OC-15).

O contrato é o §4.5 do plano da Etapa II omnicanal. Duas funções, nenhum modelo:

- ``offer`` lê a sacola aberta da origem e devolve uma ``TransferOffer`` com a
  revisão (``rev``) e o total daquele instante. Oferecer não é transferir: a origem
  fica como está, e quem leva a oferta adiante é o portador (o metadado do
  ``AccessLink`` quando o destino é a loja, o estado do código ``NB-`` quando o
  destino é a conversa), em ``offer.as_metadata()``.
- ``accept`` faz a passagem no momento do efeito: confere quem aceita, trava a
  origem, recusa se ela mudou desde a oferta (``source_changed``) ou se o destino já
  tem sacola com itens (``destination_conflict``, nunca mescla), recria cada linha
  pelo serviço de sacola do canal de destino (preço, reserva e listagem de LÁ),
  coleta o que não chegou igual, abandona a origem devolvendo as reservas e grava o
  recibo na origem. O mesmo aceite outra vez devolve o mesmo recibo (X4).

O que nunca viaja: pagamento (não existe antes do pedido; a forma escolhida que o
destino não aceita vira diferença), o orçamento da Nice (a sacola nova tem revisão
própria, então o orçamento antigo não fecha nada) e cupom que o destino recusa
(vira diferença ``coupon_not_applied``).

A mesma loja de um navegador para outro (login pelo código NB, travessia do
navegador embutido) é o caso de mesmo canal: a sacola não é recriada, é ADOTADA,
porque é a mesma sessão no mesmo canal (``_adopt_in_place``).

Chaves em ``Session.data``: ``transferred_to`` e ``transfer_receipt`` na origem,
``transferred_from`` no destino (que o commit copia para o pedido). Ver
``docs/reference/data-schemas.md``.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, dataclass, field, replace
from decimal import Decimal, InvalidOperation

from django.db import models, transaction
from django.utils import timezone
from shopman.orderman.exceptions import SessionError
from shopman.orderman.models import Session

logger = logging.getLogger(__name__)

#: Onde a oferta viaja no metadado do ``AccessLink`` (e no estado do código ``NB-``).
TRANSFER_METADATA_KEY = "cart_transfer"
#: A sacola da loja que segue dentro da própria loja (código NB, travessia do navegador).
CARRIED_CART_METADATA_KEY = "cart_session_key"

#: Força de identidade de quem entrou por um dispositivo que já provou ser da pessoa.
STRENGTH_DEVICE = "device"

_DELIVERY_FEE_SKU = "__DELIVERY_FEE__"
#: Viajam sempre que existem: dizem o que e quando, não quem.
_COMMERCIAL_KEYS = ("delivery_date", "delivery_time_slot", "order_notes")
#: Só viajam entre o mesmo dono: endereço e presente são dado de uma pessoa.
_DELIVERY_KEYS = ("delivery_address", "delivery_address_structured", "saved_address_id", "address_label")
_GIFT_KEYS = ("is_gift", "recipient", "gift_message", "gift_hide_values")

REFUSAL_MESSAGES = {
    "no_cart": "Não há sacola aberta para levar.",
    "invalid_offer": "Esta passagem de sacola não é válida.",
    "not_authorized": "Esta sacola é de outra pessoa ou pede uma identificação mais forte.",
    "source_changed": "A sacola mudou depois do convite. Peça o convite de novo.",
    "destination_conflict": "Já existe uma sacola com itens deste lado. Escolha qual manter.",
    "nothing_available": "Nenhum item da sacola está disponível deste lado.",
    "conversation_unavailable": "O WhatsApp da loja está indisponível agora.",
}


class TransferRefused(Exception):
    """A passagem não aconteceu; nada mudou, nem na origem nem no destino."""

    def __init__(self, code: str):
        self.code = code
        self.message = REFUSAL_MESSAGES.get(code, REFUSAL_MESSAGES["invalid_offer"])
        super().__init__(code)


@dataclass(frozen=True)
class TransferOffer:
    """O convite para levar a sacola: o que ela era no instante da oferta.

    ``rev`` e ``total_q`` são ``None`` só na sacola que segue dentro da própria loja
    (``carried_offer``), que não é recriada e por isso não fica velha. ``customer_ref``
    é o dono da sacola na oferta (vazio = anônima); ``None`` = não registrado.
    """

    source_channel: str
    source_key: str
    dest_channel: str
    rev: int | None
    total_q: int | None
    customer_ref: str | None
    actor: str = ""
    at: str = ""

    @property
    def offer_id(self) -> str:
        rev = "carried" if self.rev is None else str(self.rev)
        raw = f"{self.source_channel}:{self.source_key}:{rev}:{self.dest_channel}"
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    @property
    def same_channel(self) -> bool:
        return self.source_channel == self.dest_channel

    def as_metadata(self) -> dict:
        return {"offer_id": self.offer_id, **asdict(self)}

    @classmethod
    def from_metadata(cls, value) -> TransferOffer:
        if not isinstance(value, dict):
            raise TransferRefused("invalid_offer")
        try:
            offer = cls(
                source_channel=str(value["source_channel"]),
                source_key=str(value["source_key"]),
                dest_channel=str(value["dest_channel"]),
                rev=int(value["rev"]),
                total_q=int(value["total_q"]),
                customer_ref=str(value.get("customer_ref") or ""),
                actor=str(value.get("actor") or ""),
                at=str(value.get("at") or ""),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise TransferRefused("invalid_offer") from exc
        if not (offer.source_channel and offer.source_key and offer.dest_channel):
            raise TransferRefused("invalid_offer")
        if value.get("offer_id") and value["offer_id"] != offer.offer_id:
            raise TransferRefused("invalid_offer")
        return offer


@dataclass(frozen=True)
class TransferDestination:
    """Quem aceita e o que o destino já mostra.

    ``session_key`` é a sacola que o destino já tem na mão (a do navegador, a da
    conversa). ``replace_existing`` é a resposta "substituir" da superfície depois de
    um ``destination_conflict``: a sacola do destino é abandonada, nunca mesclada.
    """

    customer_ref: str = ""
    identity_strength: str = ""
    verified_customer: bool = False
    session_key: str = ""
    replace_existing: bool = False
    origin_channel: str = ""


@dataclass
class TransferReceipt:
    """O que aconteceu, gravado na origem e devolvido igual a cada reenvio do aceite."""

    offer_id: str
    source_channel: str
    source_key: str
    rev: int | None
    dest_channel: str
    dest_session_key: str
    accepted_by: str
    actor: str
    at: str
    source_total_q: int
    dest_total_q: int
    differences: list[dict] = field(default_factory=list)
    replayed: bool = False

    def as_dict(self) -> dict:
        data = asdict(self)
        data.pop("replayed")
        return data

    @classmethod
    def from_dict(cls, value: dict) -> TransferReceipt:
        known = {name for name in cls.__dataclass_fields__ if name != "replayed"}
        return cls(**{key: value.get(key) for key in known})


def offer(source_channel: str, source_key: str, dest_channel: str, *, customer_ref: str, actor: str) -> TransferOffer:
    """O convite para levar a sacola aberta de ``source_channel`` a ``dest_channel``.

    Só lê. ``customer_ref`` é quem oferece: numa sacola com dono, tem de ser o dono.
    """
    session = None
    if source_key:
        session = Session.objects.filter(channel_ref=source_channel, session_key=source_key, state="open").first()
    if session is None or not _sellable_lines(session):
        raise TransferRefused("no_cart")
    owner = _owner_ref(session)
    if owner and owner != (customer_ref or ""):
        raise TransferRefused("not_authorized")
    return TransferOffer(
        source_channel=source_channel,
        source_key=session.session_key,
        dest_channel=dest_channel,
        rev=session.rev,
        total_q=_total_q(session),
        customer_ref=owner,
        actor=actor,
        at=timezone.now().isoformat(),
    )


#: Onde a oferta da sacola da loja para a conversa viaja no estado do código ``NB-``
#: (OC-16). Chave própria, e não ``cart_transfer``: se a mensagem cair por engano no
#: fluxo de login, o access link ganha a chave e a troca do link a ignora.
CONVERSATION_STATE_KEY = "conversation_cart_transfer"
#: O trecho da mensagem pronta de "Continuar pelo WhatsApp" pelo qual a Nice a
#: reconhece mesmo com o código vencido. A mensagem não contém "quero entrar no site"
#: nem ``#menu``: essas são as palavras do fluxo de login no ManyChat.
CONVERSATION_MESSAGE_MARKER = "sacola que montei no site"
_CONVERSATION_MESSAGE = "Olá! Quero continuar por aqui a sacola que montei no site (ref. {code})"


def conversation_number() -> str:
    """O WhatsApp da loja para a mensagem pronta (o mesmo do login por WhatsApp); vazio sem ele."""
    from shopman.shop.services.whatsapp_verify import _wa_number

    return _wa_number()


def offer_to_conversation(offer: TransferOffer) -> dict:
    """Guarda a oferta da sacola da loja para a conversa sob um código ``NB-`` (OC-16, C02).

    O mesmo mecanismo da entrada pelo WhatsApp (``doorman.link_state``): código de uso
    único, prazo curto, nenhum dado pessoal, e o código não autentica ninguém. Quem
    aceita é a Nice, quando a mensagem chega pelo número que a ENVIA, com vínculo
    ``verified_customer`` (``accept``). Oferecer não toca a sacola.
    """
    import urllib.parse

    from shopman.doorman.services.link_state import store_state

    number = conversation_number()
    if not number:
        raise TransferRefused("conversation_unavailable")
    code = store_state({CONVERSATION_STATE_KEY: offer.as_metadata()})
    message = _CONVERSATION_MESSAGE.format(code=code)
    logger.info("session_transfer.offered_to_conversation offer=%s", offer.offer_id)
    return {
        "code": code,
        "message": message,
        "deep_link": f"https://wa.me/{number}?text={urllib.parse.quote(message)}",
        "wa_number": number,
    }


def carried_offer(metadata, *, channel_ref: str) -> TransferOffer | None:
    """A oferta que um link carrega, se carrega alguma.

    ``cart_transfer`` é a oferta de outro canal (``offer``). ``cart_session_key`` é a
    sacola deste mesmo canal que viajou num link da própria loja; vira uma oferta de
    mesmo canal, sem revisão, porque não é recriada.
    """
    if not isinstance(metadata, dict):
        return None
    if metadata.get(TRANSFER_METADATA_KEY):
        return TransferOffer.from_metadata(metadata[TRANSFER_METADATA_KEY])
    carried = str(metadata.get(CARRIED_CART_METADATA_KEY) or "")
    if not carried:
        return None
    return TransferOffer(
        source_channel=channel_ref,
        source_key=carried,
        dest_channel=channel_ref,
        rev=None,
        total_q=None,
        customer_ref=None,
    )


def accept(offer: TransferOffer, *, dest_context: TransferDestination, actor: str) -> TransferReceipt:
    """Leva a sacola oferecida ao destino, ou recusa sem mudar nada (``TransferRefused``)."""
    if offer.same_channel:
        return _adopt_in_place(offer, dest_context=dest_context, actor=actor)
    with transaction.atomic():
        principal = _lock_principal(dest_context.customer_ref)
        source = (
            Session.objects.select_for_update()
            .filter(channel_ref=offer.source_channel, session_key=offer.source_key)
            .first()
        )
        if source is None:
            raise TransferRefused("no_cart")
        stored = (source.data or {}).get("transfer_receipt")
        if isinstance(stored, dict) and stored.get("offer_id") == offer.offer_id:
            # O mesmo aceite outra vez (o segundo link da mesma oferta, a rede que
            # repetiu): o recibo gravado, nunca uma segunda sacola.
            receipt = TransferReceipt.from_dict(stored)
            if receipt.accepted_by != dest_context.customer_ref:
                raise TransferRefused("not_authorized")
            return replace(receipt, replayed=True)
        if source.state != "open" or source.rev != offer.rev:
            raise TransferRefused("source_changed")
        if offer.customer_ref is not None and _owner_ref(source) != offer.customer_ref:
            # O dono mudou sem mexer na revisão (identificar não incrementa ``rev``).
            raise TransferRefused("source_changed")
        _authorize(source, dest_context)

        conflicts = _destination_carts(offer.dest_channel, dest_context, principal=principal)
        if conflicts and not dest_context.replace_existing:
            raise TransferRefused("destination_conflict")

        from shopman.shop.services import sessions

        for existing in conflicts:
            sessions.abandon_session(session_key=existing.session_key, channel_ref=offer.dest_channel)
        source_data = dict(source.data or {})
        source_lines = [dict(line) for line in source.items if line.get("sku") != _DELIVERY_FEE_SKU]
        source_total_q = _total_q(source)
        # Devolver as reservas da origem ANTES de reservar no destino, na mesma
        # transação: o estoque que a origem segurava serve ao destino, ninguém
        # observa o intervalo, e toda recusa daqui em diante desfaz as duas pontas.
        sessions.abandon_session(session_key=source.session_key, channel_ref=offer.source_channel)

        now = timezone.now().isoformat()
        target, differences = _rebuild(
            offer,
            source_lines=source_lines,
            source_data=source_data,
            same_owner=bool(_owner_ref(source)),
            principal=principal,
            dest_context=dest_context,
            transferred_from={
                "channel_ref": offer.source_channel,
                "session_key": offer.source_key,
                "rev": offer.rev,
                "at": now,
                "by": actor,
            },
        )
        receipt = TransferReceipt(
            offer_id=offer.offer_id,
            source_channel=offer.source_channel,
            source_key=offer.source_key,
            rev=offer.rev,
            dest_channel=offer.dest_channel,
            dest_session_key=target.session_key,
            accepted_by=dest_context.customer_ref,
            actor=actor,
            at=now,
            source_total_q=source_total_q,
            dest_total_q=_total_q(target),
            differences=differences,
        )
        source_data["transferred_to"] = {
            "channel_ref": offer.dest_channel,
            "session_key": target.session_key,
            "at": now,
        }
        source_data["transfer_receipt"] = receipt.as_dict()
        Session.objects.filter(pk=source.pk).update(data=source_data)
    logger.info(
        "session_transfer.accepted offer=%s from=%s to=%s differences=%d",
        offer.offer_id,
        offer.source_channel,
        offer.dest_channel,
        len(differences),
    )
    return receipt


# ── Internos ──────────────────────────────────────────────────────────


def _owner_ref(session: Session) -> str:
    customer = (session.data or {}).get("customer")
    return str(customer.get("ref") or "") if isinstance(customer, dict) else ""


def _qty(line: dict) -> Decimal:
    try:
        return Decimal(str(line.get("qty") or 0))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def _qty_text(qty: Decimal) -> str:
    """``"2"``, ``"0.5"``: a quantidade como se lê, sem os zeros do armazenamento."""
    return format(qty.normalize(), "f")


def _sellable_lines(session: Session) -> list[dict]:
    return [
        line
        for line in (session.items or [])
        if line.get("sku") != _DELIVERY_FEE_SKU and _qty(line).is_finite() and _qty(line) > 0
    ]


def _total_q(session: Session) -> int:
    return sum(int(line.get("line_total_q") or 0) for line in (session.items or []))


def _lock_principal(customer_ref: str):
    """Trava o cliente de quem aceita antes de qualquer sessão (ordem Customer → Session)."""
    if not customer_ref:
        return None
    from shopman.shop.services import account as account_service

    try:
        return account_service.lock_active_customer(customer_ref=customer_ref)
    except account_service.AccountUnavailable as exc:
        raise TransferRefused("not_authorized") from exc


def _authorize(source: Session, dest_context: TransferDestination) -> None:
    """Autoriza no momento do efeito (§4.5).

    Quem aceita é o dono da sacola, ou a sacola é anônima e quem aceita provou ser
    quem diz: dispositivo confiável na loja, ou vínculo ``verified_customer`` na
    conversa. Sem cliente do lado de lá não há a quem entregar a sacola.
    """
    principal = dest_context.customer_ref
    if not principal:
        raise TransferRefused("not_authorized")
    owner = _owner_ref(source)
    if owner:
        if owner != principal:
            raise TransferRefused("not_authorized")
        return
    if dest_context.verified_customer or dest_context.identity_strength == STRENGTH_DEVICE:
        return
    raise TransferRefused("not_authorized")


def _destination_carts(dest_channel: str, dest_context: TransferDestination, *, principal) -> list[Session]:
    """As sacolas abertas COM itens que o destino já tem para esta pessoa, travadas."""
    match = models.Q(pk__in=[])
    if dest_context.session_key:
        match |= models.Q(session_key=dest_context.session_key)
    if principal is not None:
        match |= models.Q(data__customer__ref=principal.ref)
        if principal.phone:
            match |= models.Q(handle_type="phone", handle_ref=principal.phone)
    candidates = (
        Session.objects.select_for_update()
        .filter(channel_ref=dest_channel, state="open")
        .filter(match)
        .order_by("pk")
    )
    return [candidate for candidate in candidates if _sellable_lines(candidate)]


def _carried_data(
    source_data: dict, *, dest_channel: str, same_owner: bool, differences: list[dict],
) -> dict:
    """O que da ``Session.data`` da origem vale no destino. Pagamento nunca."""
    from shopman.shop.services.channel_policy import resolve_channel_policy

    policy = resolve_channel_policy(dest_channel)
    carried: dict = {}
    fulfillment = str(source_data.get("fulfillment_type") or "")
    if fulfillment:
        if fulfillment in policy.fulfillment_types:
            carried["fulfillment_type"] = fulfillment
        else:
            differences.append({"kind": "fulfillment_not_available", "fulfillment_type": fulfillment})
    for key in _COMMERCIAL_KEYS:
        if source_data.get(key) not in (None, ""):
            carried[key] = source_data[key]
    personal = list(_GIFT_KEYS)
    if carried.get("fulfillment_type") == "delivery":
        personal = list(_DELIVERY_KEYS) + personal
    present = [key for key in personal if key in source_data]
    if same_owner:
        carried.update({key: source_data[key] for key in present})
        if isinstance(source_data.get("customer"), dict):
            carried["customer"] = dict(source_data["customer"])
    elif present:
        differences.append({"kind": "details_not_carried", "fields": present})
    payment = source_data.get("payment")
    method = str(payment.get("method") or "") if isinstance(payment, dict) else ""
    if method and method not in policy.payment_methods:
        differences.append({"kind": "payment_not_available", "method": method})
    return carried


def _rebuild(
    offer: TransferOffer,
    *,
    source_lines: list[dict],
    source_data: dict,
    same_owner: bool,
    principal,
    dest_context: TransferDestination,
    transferred_from: dict,
) -> tuple[Session, list[dict]]:
    """A sacola nova no destino, linha a linha pelo serviço de sacola de lá."""
    from shopman.shop import product_options
    from shopman.shop.services import cart as cart_service
    from shopman.shop.services import sessions

    differences: list[dict] = []
    dest = offer.dest_channel
    origin = str(source_data.get("origin_channel") or dest_context.origin_channel or offer.source_channel)
    data = {"origin_channel": origin}
    # Data, horário e recebimento antes das linhas: a reserva no destino cai na
    # mesma data que a sacola prometia (``cart._cart_date`` lê ``delivery_date``).
    data.update(_carried_data(source_data, dest_channel=dest, same_owner=same_owner, differences=differences))
    data["transferred_from"] = transferred_from
    target = sessions.create_session(dest, data=data)
    key = target.session_key
    if principal is not None:
        # O preço do destino é o desta pessoa (grupo, aniversário) desde a primeira linha.
        sessions.assign_customer(session_key=key, channel_ref=dest, customer_uuid=principal.uuid)

    carried_lines: list[dict] = []
    for line in source_lines:
        sku = str(line.get("sku") or "")
        name = str(line.get("name") or sku)
        qty = _qty(line)
        if not sku or not qty.is_finite() or qty <= 0:
            continue
        options = product_options.selection_of(product_options.line_options(line))

        def add(amount, *, sku=sku, name=name, options=options, line=line):
            cart_service.add_item(
                session_key=key,
                channel_ref=dest,
                origin_channel=origin,
                sku=sku,
                qty=amount,
                unit_price_q=int(line.get("unit_price_q") or 0),
                name=name,
                options=options,
            )

        try:
            add(qty)
            carried_lines.append(line)
            continue
        except cart_service.CartDateMismatchError:
            differences.append({"kind": "unavailable", "sku": sku, "name": name, "qty": _qty_text(qty)})
            continue
        except cart_service.CartUnavailableError as exc:
            available = Decimal(str(exc.available_qty or 0))
        except (product_options.OptionSelectionError, SessionError):
            differences.append({"kind": "unavailable", "sku": sku, "name": name, "qty": _qty_text(qty)})
            continue
        if Decimal(0) < available < qty:
            try:
                add(available)
                carried_lines.append({**line, "qty": str(available)})
                differences.append(
                    {"kind": "qty_reduced", "sku": sku, "name": name, "from_qty": _qty_text(qty), "to_qty": _qty_text(available)}
                )
                continue
            except (cart_service.CartUnavailableError, product_options.OptionSelectionError, SessionError):
                pass
        differences.append({"kind": "unavailable", "sku": sku, "name": name, "qty": _qty_text(qty)})

    if not carried_lines:
        raise TransferRefused("nothing_available")

    coupon = str(source_data.get("coupon_code") or "")
    if coupon:
        try:
            cart_service.validate_and_apply_coupon(session_key=key, channel_ref=dest, code=coupon, customer=principal)
        except cart_service.CouponRejected as exc:
            differences.append({"kind": "coupon_not_applied", "code": coupon, "reason": exc.code})

    target = Session.objects.get(pk=target.pk)
    arrived = {
        (line.get("sku"), product_options.signature(product_options.line_options(line))): line
        for line in target.items
        if line.get("sku") != _DELIVERY_FEE_SKU
    }
    for line in carried_lines:
        landed = arrived.get((line.get("sku"), product_options.signature(product_options.line_options(line))))
        if landed is None:
            continue
        before, after = int(line.get("unit_price_q") or 0), int(landed.get("unit_price_q") or 0)
        if before != after:
            differences.append(
                {"kind": "price_changed", "sku": line.get("sku"), "name": str(landed.get("name") or ""),
                 "from_q": before, "to_q": after}
            )
    return target, differences


def _adopt_in_place(offer: TransferOffer, *, dest_context: TransferDestination, actor: str) -> TransferReceipt:
    """A sacola deste canal que viajou num link da própria loja: ADOTADA, não recriada.

    É a mesma sessão no mesmo canal: preço, reserva e listagem já são os daqui, e a
    revisão não fica velha porque nada foi copiado. A guarda é só contra desperdício:
    uma ref que não aponta para sacola aberta com itens não vale a troca
    (``no_cart``), e a sacola de outra pessoa não se adota (``not_authorized``).

    ⚠️ **A sacola que viajou GANHA da sacola que o navegador já tinha**, e isto não é
    a mescla que o ``destination_conflict`` proíbe. O webview do WhatsApp tem pote de
    cookie próprio e persistente e chega carregando a sacola de uma visita anterior;
    quando a adoção só acontecia com o navegador "vazio", a pessoa que acabara de
    montar a sacola aterrissava numa de dias atrás, a dela descartada em silêncio. A
    que viajou é o contexto explícito deste login; a outra é resíduo do mesmo canal,
    que fica como está (nem abandonada, nem mesclada).

    Quem entra com a sacola anônima passa a ver o preço dela: a identidade de preço
    vai para a sessão e ela é reprecificada; o que mudou de preço vira diferença.
    """
    from shopman.shop.services import cart as cart_service
    from shopman.shop.services import sessions

    with transaction.atomic():
        principal = _lock_principal(dest_context.customer_ref)
        source = (
            Session.objects.select_for_update()
            .filter(channel_ref=offer.source_channel, session_key=offer.source_key, state="open")
            .first()
        )
        if source is None or not _sellable_lines(source):
            raise TransferRefused("no_cart")
        if offer.rev is not None and source.rev != offer.rev:
            raise TransferRefused("source_changed")
        _authorize(source, dest_context)
        differences: list[dict] = []
        if principal is not None and _owner_ref(source) != principal.ref:
            before = {line.get("line_id"): int(line.get("unit_price_q") or 0) for line in source.items}
            if sessions.assign_customer(session_key=source.session_key, channel_ref=source.channel_ref,
                                        customer_uuid=principal.uuid):
                source = cart_service.reprice(session_key=source.session_key, channel_ref=source.channel_ref) or source
            for line in source.items:
                was = before.get(line.get("line_id"))
                now_q = int(line.get("unit_price_q") or 0)
                if line.get("sku") != _DELIVERY_FEE_SKU and was is not None and was != now_q:
                    differences.append({"kind": "price_changed", "sku": line.get("sku"),
                                        "name": str(line.get("name") or ""), "from_q": was, "to_q": now_q})
        total_q = _total_q(source)
        return TransferReceipt(
            offer_id=offer.offer_id,
            source_channel=offer.source_channel,
            source_key=offer.source_key,
            rev=offer.rev,
            dest_channel=offer.dest_channel,
            dest_session_key=source.session_key,
            accepted_by=dest_context.customer_ref,
            actor=actor,
            at=timezone.now().isoformat(),
            source_total_q=total_q,
            dest_total_q=total_q,
            differences=differences,
        )
