"""Handlers de campanha — evento operacional → CampaignService.evaluate().

Os receivers aqui são a ponte entre o que acontece na padaria e o engine de
campanha. Três cuidados que valem por todo o módulo:

- **Depois do COMMIT.** A avaliação lê estoque e catálogo; rodar dentro da
  transação da fornada leria estado ainda não visível.
- **Nunca derruba quem disparou.** Marketing não pode quebrar a operação: toda
  falha vira log, jamais exceção de volta para o ``finish`` da fornada.
- **Contexto rico na origem.** O evaluate() recebe coleções, qualidade e
  quantidade já resolvidas, porque só aqui elas estão baratas de obter.
"""

from __future__ import annotations

import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def connect() -> None:
    """Conectar os receivers às fontes de evento."""
    from shopman.craftsman.signals import production_changed

    production_changed.connect(
        on_production_changed,
        dispatch_uid="shopman.shop.handlers.campaign.on_production_changed",
        weak=False,
    )

    try:
        from shopman.offerman.signals import availability_changed, product_created

        availability_changed.connect(
            on_availability_changed,
            dispatch_uid="shopman.shop.handlers.campaign.on_availability_changed",
            weak=False,
        )
        product_created.connect(
            on_product_created,
            dispatch_uid="shopman.shop.handlers.campaign.on_product_created",
            weak=False,
        )
    except ImportError:
        pass


# ── Receivers ────────────────────────────────────────────────────────


def on_production_changed(sender, product_ref, date, action, work_order, **kwargs) -> None:
    """Fornada concluída → avalia as regras de ``production_finished``."""
    if action != "finished" or not product_ref:
        return

    meta = getattr(work_order, "meta", None) or {}
    context = {
        "sku": product_ref,
        "trigger": "production_finished",
        "quality": meta.get("quality", "bom"),
        "quantity": str(getattr(work_order, "finished", "") or ""),
        "work_order_ref": getattr(work_order, "ref", ""),
        "finished_at": _iso(getattr(work_order, "finished_at", None)),
        "collections": _collections(product_ref),
    }
    _evaluate_later("production_finished", context)


def on_availability_changed(sender, instance=None, sku=None, listing_ref=None, **kwargs) -> None:
    """Disponibilidade mudou → ``low_stock`` ou ``stock_back``, nunca os dois.

    O trigger sai da quantidade atual: zero não anuncia nada (não há o que
    vender), pouco vira escassez, e voltar do zero vira reposição.
    """
    sku = sku or getattr(instance, "sku", "") or getattr(
        getattr(instance, "product", None), "sku", ""
    )
    if not sku:
        return

    available = _available_qty(sku)
    was_out = bool(kwargs.get("was_out_of_stock"))

    if was_out and available > 0:
        trigger = "stock_back"
    elif 0 < available <= _low_stock_threshold():
        trigger = "low_stock"
    else:
        return

    _evaluate_later(
        trigger,
        {
            "sku": sku,
            "trigger": trigger,
            "available_qty": available,
            "listing_ref": listing_ref or "",
            "collections": _collections(sku),
        },
    )


def on_product_created(sender, instance=None, sku=None, **kwargs) -> None:
    """Produto novo no catálogo → ``product_created``."""
    sku = sku or getattr(instance, "sku", "")
    if not sku:
        return
    _evaluate_later(
        "product_created",
        {"sku": sku, "trigger": "product_created", "collections": _collections(sku)},
    )


# ── Helpers ──────────────────────────────────────────────────────────


def _evaluate_later(trigger: str, context: dict) -> None:
    transaction.on_commit(lambda: _evaluate(trigger, context))


def _evaluate(trigger: str, context: dict) -> None:
    from shopman.shop.services import campaign

    try:
        announcements = campaign.evaluate(trigger, context)
    except Exception:
        logger.warning("campaign.evaluate_failed trigger=%s", trigger, exc_info=True)
        return
    if announcements:
        logger.info(
            "campaign.evaluated trigger=%s sku=%s announcements=%d",
            trigger, context.get("sku", ""), len(announcements),
        )


def _collections(sku: str) -> list[str]:
    try:
        from shopman.shop.projections import catalog_context

        return list(catalog_context.collection_refs_by_sku([sku]).get(sku, []))
    except Exception:
        logger.debug("campaign.collections_failed sku=%s", sku, exc_info=True)
        return []


def _available_qty(sku: str) -> int:
    from decimal import Decimal

    try:
        from shopman.shop.services import availability

        result = availability.check(sku, Decimal("1"))
        return int(result.get("available_qty") or 0)
    except Exception:
        logger.debug("campaign.availability_failed sku=%s", sku, exc_info=True)
        return 0


def _low_stock_threshold() -> int:
    try:
        from shopman.shop.config import ChannelConfig

        return int(ChannelConfig().stock.low_stock_threshold)
    except Exception:
        logger.debug("campaign.threshold_failed", exc_info=True)
        return 5


def _iso(value) -> str:
    return value.isoformat() if value is not None else ""


# ── Directive handlers ───────────────────────────────────────────────


class AnnouncementHandler:
    """Publica o announcement numa plataforma externa. Topic: announcement.publish

    Enquanto não houver adapter de posting configurado (F5/F6 das specs), o
    handler registra o conteúdo como **pendente de publicação manual** em vez
    de falhar: o gestor copia o texto pronto para o app nativo. Falhar aqui
    encheria a fila de retries por uma credencial que ainda não existe.
    """

    topic = "announcement.publish"

    def handle(self, *, message, ctx: dict) -> None:
        from shopman.shop.models import Announcement

        payload = message.payload or {}
        platform = payload.get("platform", "")
        announcement = Announcement.objects.filter(pk=payload.get("announcement_id")).first()
        if announcement is None:
            logger.warning("campaign.announcement_missing directive=%s", message.pk)
            return

        adapter = _posting_adapter(platform)
        if adapter is None:
            _record_result(
                announcement, platform,
                {"status": "pending_manual", "reason": "sem adapter de posting configurado"},
            )
            _settle(announcement)
            return

        try:
            result = adapter.publish(announcement, platform=platform)
        except Exception as exc:
            _record_result(announcement, platform, {"status": "failed", "error": str(exc)})
            _settle(announcement)
            raise  # retry/backoff do worker cuida do resto

        _record_result(announcement, platform, {"status": "published", **(result or {})})
        _settle(announcement)


class AnnouncementNotifyHandler:
    """Dispara a audiência direta (WhatsApp). Topic: announcement.notify

    A audiência é resolvida AQUI, não na criação do announcement: entre a fornada e a
    aprovação do gestor, favoritos e alertas mudam. Cada onda (vip/general)
    chega numa directive própria.
    """

    topic = "announcement.notify"

    def handle(self, *, message, ctx: dict) -> None:
        from shopman.shop.models import Announcement
        from shopman.shop.services import audience as audience_service

        payload = message.payload or {}
        wave = payload.get("wave", "all")
        announcement = Announcement.objects.filter(pk=payload.get("announcement_id")).first()
        if announcement is None:
            logger.warning("campaign.notify_announcement_missing directive=%s", message.pk)
            return

        sku = (announcement.trigger_context or {}).get("sku", "")
        rules = (announcement.rule.audience_rules or {}) if announcement.rule_id else {}
        resolved = audience_service.resolve(rules, sku=sku)

        recipients = {
            "vip": resolved.vip,
            "general": resolved.general,
            "all": resolved.all_recipients(),
        }.get(wave, ())

        sent, failed = _send_to(recipients, announcement=announcement)
        _record_wave(announcement, wave, sent=sent, failed=failed,
                     expected=int(payload.get("waves_expected") or 1))
        _settle(announcement)
        logger.info(
            "campaign.notified announcement=%s wave=%s sent=%d failed=%d", announcement.pk, wave, sent, failed
        )


def _send_to(recipients, *, announcement) -> tuple[int, int]:
    from shopman.shop.notifications import notify

    body = announcement.body
    link = (announcement.content or {}).get("link", "")
    sent = failed = 0
    for recipient in recipients:
        try:
            result = notify(
                event="announcement.published",
                recipient=recipient.phone,
                context={"body": body, "action_url": link, "cta": "Garanta o seu:"},
            )
            sent += 1 if getattr(result, "success", False) else 0
            failed += 0 if getattr(result, "success", False) else 1
        except Exception:
            failed += 1
            logger.warning("campaign.send_failed announcement=%s", announcement.pk, exc_info=True)
    return sent, failed


def _posting_adapter(platform: str):
    """Adapter de posting da plataforma, ou ``None`` enquanto não houver."""
    try:
        from shopman.shop.adapters import get_adapter

        return get_adapter("posting", method=platform)
    except Exception:
        logger.debug("campaign.no_posting_adapter platform=%s", platform, exc_info=True)
        return None


def _record_result(announcement, platform: str, result: dict, *, merge: bool = False) -> None:
    results = dict(announcement.platform_results or {})
    if merge and isinstance(results.get(platform), dict):
        results[platform] = {**results[platform], **result}
    else:
        results[platform] = result
    announcement.platform_results = results
    announcement.save(update_fields=["platform_results"])


def _platform_settled(platform: str, entry) -> bool:
    """Esta plataforma já respondeu por inteiro?

    O WhatsApp é o único que responde em partes: com VIP-first, dar o announcement por
    publicado na primeira onda marcaria como concluído um disparo que ainda tem
    a metade geral por sair.
    """
    if not isinstance(entry, dict):
        return False
    if platform == "whatsapp":
        expected = int(entry.get("waves_expected") or 1)
        return len(entry.get("waves") or []) >= expected
    return bool(entry.get("status"))


def _record_wave(announcement, wave: str, *, sent: int, failed: int, expected: int) -> None:
    """Acumular o resultado de uma onda de WhatsApp no mesmo registro.

    Ondas são disparos independentes (o geral sai 15 min depois do VIP), então
    os totais somam e as ondas concluídas ficam listadas: é o que permite ao
    ``_settle`` saber que o WhatsApp ainda tem gente para receber.
    """
    entry = dict((announcement.platform_results or {}).get("whatsapp") or {})
    waves = list(entry.get("waves") or [])
    if wave not in waves:
        waves.append(wave)

    _record_result(announcement, "whatsapp", {
        "status": "sent",
        "waves": waves,
        "waves_expected": expected,
        "sent": int(entry.get("sent") or 0) + sent,
        "failed": int(entry.get("failed") or 0) + failed,
    })


def _settle(announcement) -> None:
    """Fechar o announcement quando toda plataforma já respondeu.

    ``pending_manual`` conta como resposta: o sistema fez a parte dele e
    entregou o conteúdo pronto. Qualquer falha marca o announcement inteiro como
    falho, para o gestor ver que algo não saiu.
    """
    from django.utils import timezone

    from shopman.shop.models import AnnouncementStatus

    results = announcement.platform_results or {}
    if not all(_platform_settled(name, results.get(name)) for name in announcement.platforms or []):
        return

    statuses = {entry.get("status") for entry in results.values() if isinstance(entry, dict)}
    announcement.status = AnnouncementStatus.FAILED if "failed" in statuses else AnnouncementStatus.PUBLISHED
    announcement.published_at = announcement.published_at or timezone.now()
    announcement.save(update_fields=["status", "published_at"])
