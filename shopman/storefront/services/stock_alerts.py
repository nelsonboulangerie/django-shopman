"""Stock-back alerts ("Me avise quando disponível") — subscribe + notify.

Subscribe is open to anonymous shoppers (phone only) and logged-in customers.
The notify path is triggered by a stock-arrival receiver and is idempotent: it
only fires for *pending* subscriptions of a SKU that is *now* available, and
stamps ``notified_at`` so each subscription notifies exactly once.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from shopman.storefront.constants import STOREFRONT_CHANNEL_REF

logger = logging.getLogger(__name__)


def has_pending(sku: str, *, alert_types: tuple[str, ...] = ()) -> bool:
    """Cheap guard for the arrival/bake receivers (indexed exists())."""
    from shopman.storefront.models import StockAlertSubscription

    qs = StockAlertSubscription.objects.filter(sku=sku, notified_at__isnull=True)
    if alert_types:
        qs = qs.filter(alert_type__in=alert_types)
    return qs.exists()


def default_alert_type(sku: str) -> str:
    """Que aviso o cliente está pedindo quando toca o sino deste produto?

    ⚠️ Quem decide é o SERVIDOR, e a natureza do produto é o critério — a tela
    diz só "me avise sobre este produto", porque o cliente não sabe (nem
    deveria saber) que existem dois eixos de aviso.

    - Item de fornada → ``production_ready``: quem quer pão quer saber quando
      sai do forno.
    - Item de prateleira → ``stock_back``: quem quer um item de prateleira quer
      saber quando ele volta.

    Antes desta derivação a loja mandava o POST sem ``alert_type``, todo mundo
    caía em ``stock_back`` e o eixo ``production_ready`` era código órfão: o
    receptor de fornada nunca achava ninguém, e o público de "Fornada pronta"
    do Marketing prometia gente que a loja não sabia criar.
    """
    from shopman.shop.projections import catalog_context
    from shopman.storefront.models import StockAlertSubscription

    try:
        if catalog_context.comes_out_of_the_oven(sku):
            return StockAlertSubscription.AlertType.PRODUCTION_READY
    except Exception:
        logger.debug("stock_alerts: alert_type derivation failed sku=%s", sku, exc_info=True)
    return StockAlertSubscription.AlertType.STOCK_BACK


def subscribed_skus(*, customer=None, phone: str = "") -> set[str]:
    """SKUs com inscrição PENDENTE para este viewer (cliente logado e/ou telefone).

    Usado pela projeção para persistir o estado do sino "Me avise" entre reloads.
    """
    from django.db.models import Q

    from shopman.storefront.models import StockAlertSubscription

    customer_ref = (getattr(customer, "ref", "") or "").strip()
    contact = (phone or getattr(customer, "phone", "") or "").strip()
    if not customer_ref and not contact:
        return set()

    cond = Q()
    if customer_ref:
        cond |= Q(customer_ref=customer_ref)
    if contact:
        cond |= Q(contact_phone=contact)
    return set(
        StockAlertSubscription.objects.filter(notified_at__isnull=True)
        .filter(cond)
        .values_list("sku", flat=True)
    )


def has_pending_for(*, sku: str, customer=None, phone: str = "", alert_type: str = "") -> bool:
    """True when this customer/contact still has a pending alert for ``sku``."""
    from django.db.models import Q

    from shopman.storefront.models import StockAlertSubscription

    customer_ref = (getattr(customer, "ref", "") or "").strip()
    contact = (phone or getattr(customer, "phone", "") or "").strip()
    if not sku or (not customer_ref and not contact):
        return False

    qs = StockAlertSubscription.objects.filter(sku=sku, notified_at__isnull=True)
    if alert_type:
        qs = qs.filter(alert_type=alert_type)
    cond = Q()
    if customer_ref:
        cond |= Q(customer_ref=customer_ref)
    if contact:
        cond |= Q(contact_phone=contact)
    return qs.filter(cond).exists()


def subscribe(
    sku: str,
    *,
    channel_ref: str = STOREFRONT_CHANNEL_REF,
    customer=None,
    phone: str = "",
    alert_type: str = "",
):
    """Register a pending alert. Returns the subscription or None.

    ``alert_type`` vazio NÃO é ``stock_back``: é "decida você", e a decisão sai
    de :func:`default_alert_type`, pela natureza do produto. Quem passa o tipo
    explicitamente manda — é o caso do endpoint quando o corpo escolhe.

    Dedupes a pending alert per (sku, alert_type, target): os dois eixos podem
    coexistir para o mesmo contato sem um sobrescrever o outro. Ninguém cria os
    dois de propósito — quem faz isso é um pedido explícito, ou uma linha
    antiga; ``_notify`` garante que ainda assim sai UMA mensagem por pessoa.

    ``customer`` is a Guestman Customer (or None for anonymous); ``phone`` is
    the anonymous contact.
    """
    from shopman.storefront.models import StockAlertSubscription

    alert_type = alert_type or default_alert_type(sku)
    customer_ref = (getattr(customer, "ref", "") or "").strip()
    contact = (phone or getattr(customer, "phone", "") or "").strip()
    if not customer_ref and not contact:
        return None

    pending = StockAlertSubscription.objects.filter(
        sku=sku, alert_type=alert_type, notified_at__isnull=True
    )
    existing = (
        pending.filter(customer_ref=customer_ref).first()
        if customer_ref
        else pending.filter(contact_phone=contact).first()
    )
    if existing:
        return existing

    return StockAlertSubscription.objects.create(
        sku=sku,
        alert_type=alert_type,
        channel_ref=channel_ref or STOREFRONT_CHANNEL_REF,
        customer_ref=customer_ref,
        contact_phone=contact,
    )


def notify_back_in_stock(sku: str, *, also_bake_waiters: bool = False) -> int:
    """Notify pending subscribers once ``sku`` is available again.

    Idempotent: marks ``notified_at`` only on a successful send, so a failed
    delivery is retried on the next stock arrival. Devolve quantas PESSOAS
    foram avisadas (não quantas assinaturas: ver ``_notify``).

    ⚠️ ``also_bake_waiters`` é a REDE DE SEGURANÇA de quem espera fornada.

    Um item de fornada pode voltar a ter estoque por um caminho que não é
    produção — recebimento, devolução, ajuste de inventário. Quem assinou
    ``production_ready`` ficaria calado para sempre nesses casos, porque o
    ``production_changed`` nunca vai acontecer para aquela unidade. Então:
    chegou estoque por fora da produção, a promessa "o produto está aí" está
    cumprida e a fila da fornada também é servida — com a copy de CHEGADA
    (``stock_arrived``), porque nada saiu do forno e mentir sobre isso é pior
    que o silêncio que estamos consertando.

    O receptor liga a rede só quando o ``Move`` NÃO é de produção
    (``kind != make``). Ligá-la também na fornada faria a mesma pessoa ser
    servida duas vezes no mesmo instante — e, pior, pelo caminho errado: os
    dois ``on_commit`` correm em ordem de registro, e o do ``Move`` costuma
    chegar primeiro, então o "saiu do forno" viraria "chegou ao estoque".
    """
    from shopman.storefront.models import StockAlertSubscription

    types = [StockAlertSubscription.AlertType.STOCK_BACK]
    if also_bake_waiters:
        types.append(StockAlertSubscription.AlertType.PRODUCTION_READY)
    return _notify(sku, alert_types=types, event="stock_arrived")


def notify_bake_ready(sku: str) -> int:
    """Notify pending ``production_ready`` subscribers quando sai uma fornada.

    Mesmo gate de disponibilidade do ``stock_back``: fornada concluída que ainda
    não virou estoque vendável no canal não vira aviso, porque o aviso promete
    "pode pedir agora". Frustrar quem pediu para ser avisado é pior que calar.
    """
    from shopman.storefront.models import StockAlertSubscription

    return _notify(
        sku,
        alert_types=[StockAlertSubscription.AlertType.PRODUCTION_READY],
        event="production_ready",
    )


def _notify(sku: str, *, alert_types: list[str], event: str) -> int:
    """Serve as inscrições pendentes destes tipos com UMA copy: a do que aconteceu.

    ``event`` é do EVENTO, não da inscrição: "chegou ao estoque" e "saiu do
    forno" prometem coisas diferentes, e quem sabe qual das duas é verdade
    agora é quem disparou, não quem assinou.

    Uma pessoa, uma mensagem: assinaturas do mesmo telefone são agrupadas e
    carimbadas juntas. Contatos legados que assinaram os dois eixos do mesmo
    produto (era o que o concierge fazia) recebiam duas mensagens iguais.
    """
    from shopman.storefront.models import StockAlertSubscription
    from shopman.storefront.services import sku_state

    pending = list(
        StockAlertSubscription.objects.filter(
            sku=sku, alert_type__in=alert_types, notified_at__isnull=True
        )
    )
    if not pending:
        return 0

    product_name = _product_name(sku)
    notified = 0
    #: Uma entrada por destinatário: a chave é o canal + o telefone, porque é o
    #: telefone que recebe. Assinatura sem telefone fica de fora do agrupamento
    #: e falha sozinha em ``_deliver`` (não há a quem avisar).
    groups: dict[tuple[str, str], list] = {}
    for sub in pending:
        channel_ref = sub.channel_ref or STOREFRONT_CHANNEL_REF
        groups.setdefault((channel_ref, (sub.contact_phone or "").strip()), []).append(sub)

    for (channel_ref, _phone), subs in groups.items():
        try:
            state = sku_state.resolve(sku=sku, channel_ref=channel_ref)
        except Exception:
            logger.debug("stock_alerts: availability check failed sku=%s", sku, exc_info=True)
            continue
        if not state.can_add_to_cart:
            continue  # still unavailable for this channel — keep pending
        if not _deliver(
            subs[0], product_name=product_name, event=event,
            available_qty=state.available_qty,
        ):
            continue
        stamped = timezone.now()
        for sub in subs:
            sub.notified_at = stamped
            sub.save(update_fields=["notified_at"])
        notified += 1
    if notified:
        logger.info(
            "stock_alerts: notified %s subscriber(s) for sku=%s event=%s",
            notified, sku, event,
        )
    return notified


# ── private ──────────────────────────────────────────────────────────


def _product_name(sku: str) -> str:
    # Read through the shop projection (surface modules don't import kernels).
    from shopman.shop.projections import catalog_context

    product = catalog_context.get_product(sku)
    return product.name if product is not None else sku


def _image_url(sku: str) -> str:
    """Foto do produto pelo orquestrador — superfície não fala com o kernel."""
    try:
        from shopman.shop.services import campaign as campaign_service

        return campaign_service.product_image_url(sku)
    except Exception:
        logger.debug("stock_alerts: foto não resolveu sku=%s", sku, exc_info=True)
        return ""


def _first_name(sub) -> str:
    """Primeiro nome de quem assinou, ou vazio.

    Vazio é resultado legítimo: assinante anônimo tem só telefone. O template trata a
    ausência (a saudação some), então nunca sai "Oi ," na cara do cliente.
    """
    ref = (getattr(sub, "customer_ref", "") or "").strip()
    if not ref:
        return ""
    # Pelo orquestrador, nunca pelo guestman direto: superfície é adaptador de HTTP e
    # read-model, e a fronteira tem teste (`test_import_boundaries`).
    try:
        from shopman.shop.services import customer as customer_service

        return customer_service.first_name_for(ref)
    except Exception:
        logger.debug("stock_alerts: first name lookup failed for %s", ref, exc_info=True)
        return ""


def _deliver(
    sub, *, product_name: str, event: str = "stock_arrived", available_qty: int | None = None,
) -> bool:
    """Send the subscription's notification via the channel's backend. True on success."""
    from shopman.shop.config import ChannelConfig
    from shopman.shop.notifications import notify
    from shopman.shop.services import storefront_links
    from shopman.shop.services.availability_copy import availability_phrase

    # subscribe() stores contact_phone = phone OR the customer's phone, so a
    # bare customer_ref without phone has no reachable recipient.
    recipient = (sub.contact_phone or "").strip()
    if not recipient:
        logger.debug("stock_alerts: no recipient for sub=%s", sub.pk)
        return False

    try:
        backend = (ChannelConfig.for_channel(sub.channel_ref or STOREFRONT_CHANNEL_REF).notifications.backend) or "manychat"
    except Exception:
        logger.debug("stock_alerts: backend resolve failed, default manychat", exc_info=True)
        backend = "manychat"

    try:
        result = notify(
            event=event,
            recipient=recipient,
            context={
                "sku": sub.sku,
                # Nome que a mensagem usa: o sufixo que o template gruda no fim do link
                # do botão. Ver o gêmeo em `handlers/_stock_receivers.py`.
                "product_sku": sub.sku,
                # Foto do produto. Prefixo `product_` por namespacing: o campo vive no
                # perfil do assinante no ManyChat.
                "product_image_url": _image_url(sub.sku),
                "product_name": product_name,
                "customer_name": _first_name(sub),
                "product_url": storefront_links.product_url(sub.sku),
                # Placeholders do template compartilhado de stock_arrived: aqui
                # não há reserva nem prazo — cliente sem hold ("Me avise").
                "reserve_note": "",
                "deadline_note": "",
                # Quantidade REAL, já resolvida na checagem de disponibilidade acima.
                # Vazio quando o canal não sabe contar (`available_qty=None`): a
                # mensagem então não fala em número, em vez de inventar um.
                "available_qty": "" if available_qty is None else str(available_qty),
                # Frase pronta para template aprovado do WhatsApp. O ManyChat não
                # deve montar gramática com pedaços soltos: campo vazio ou valor
                # antigo no perfil do assinante vira FOMO falso.
                "availability_phrase": availability_phrase(available_qty),
                "cta": "Garanta o seu:",
                "action_url": storefront_links.product_url(sub.sku),
            },
            backend=backend,
        )
        return bool(getattr(result, "success", False))
    except Exception:
        logger.warning("stock_alerts: delivery failed sub=%s sku=%s", sub.pk, sub.sku, exc_info=True)
        return False
