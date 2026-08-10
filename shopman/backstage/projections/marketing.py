"""
Projeção da Campanha para o gestor — o lado REVISÃO do marketing operacional.

A operação gera o announcement; o gestor decide se ele sai. Esta projeção é o que a
superfície `surfaces/marketing-nuxt` lê: os announcements que pedem decisão agora, os
que já saíram, e as regras/modelos que governam tudo isso.

Read-only. Frozen dataclasses convertidos por ``backstage.api.projections``.

Duas escolhas deliberadas:

- **Contagem, nunca destinatário.** ``audience`` traz só números (o serviço já
  persiste assim, sem PII). A superfície formata a frase; o backend não manda
  string pronta.
- **Prazo em minutos, não instante.** Frescor de fornada é efêmero: o card
  precisa mostrar "expira em 12 min", e um ISO cru obrigaria a superfície a
  reimplementar a régua de expiração.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    AnnouncementTemplate,
    Campaign,
    Trigger,
)

#: Plataformas que uma regra pode alvejar, na ordem em que aparecem no formulário.
PLATFORM_CHOICES: tuple[tuple[str, str], ...] = (
    ("instagram", "Instagram"),
    ("facebook", "Facebook"),
    ("google_business", "Google Meu Negócio"),
    ("whatsapp", "WhatsApp"),
    ("tv", "TV da loja"),
)

#: Janela do "publicados recentemente" no painel.
RECENT_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class PlatformResultProjection:
    """Como foi em UMA plataforma. Uma falha no Instagram não some do painel."""

    platform: str
    label: str
    status: str  # published | pending_manual | failed | queued
    detail: str
    url: str


@dataclass(frozen=True)
class AnnouncementProjection:
    pk: int
    status: str
    status_label: str
    body: str
    image_url: str
    hashtags: tuple[str, ...]
    link: str
    platforms: tuple[str, ...]
    audience: dict
    audience_total: int
    platform_results: tuple[PlatformResultProjection, ...]
    trigger: str
    trigger_label: str
    rule_name: str
    template_name: str
    sku: str
    created_at: str
    expires_at: str
    expires_in_minutes: int  # -1 = não expira
    published_at: str
    approved_by: str


@dataclass(frozen=True)
class CampaignStatsProjection:
    """Números do dia. Poucos e honestos — não é dashboard de engajamento."""

    pending_count: int
    published_today: int
    audience_reached_today: int
    failed_today: int


@dataclass(frozen=True)
class ReachLimitProjection:
    """O que impede (ou limita) a entrega de UMA plataforma, visto antes de publicar.

    A primeira versão disto só falava de WhatsApp, porque nasceu num teste de WhatsApp —
    e o dono apontou o erro: anúncio sai por várias plataformas, e cada uma tem exigência
    própria. Agora o formato é genérico (plataforma, bloqueio ou limitação, o que fazer) e
    a razão vem de `services/delivery_readiness.py`, que sabe a diferença entre publicar
    (IG/Facebook/Google) e mandar mensagem (WhatsApp).

    ``blocking=True`` significa que nada sai por ali. ``blocking=False`` é o meio-termo
    honesto: sai, mas não para todo mundo.
    """

    code: str
    platform: str
    platform_label: str
    title: str
    detail: str
    action: str = ""
    blocking: bool = True


@dataclass(frozen=True)
class CampaignBoardProjection:
    pending: tuple[AnnouncementProjection, ...]
    recent: tuple[AnnouncementProjection, ...]
    stats: CampaignStatsProjection
    reach_limits: tuple[ReachLimitProjection, ...] = ()


@dataclass(frozen=True)
class CampaignProjection:
    pk: int
    name: str
    trigger: str
    trigger_label: str
    trigger_filter: dict
    template_id: int
    template_name: str
    platforms: tuple[str, ...]
    audience_rules: dict
    schedule: dict
    requires_approval: bool
    expires_after_minutes: int
    is_active: bool


@dataclass(frozen=True)
class AnnouncementTemplateProjection:
    pk: int
    name: str
    body: str
    variables: tuple[str, ...]
    use_ai_generation: bool
    image_source: str
    is_active: bool


@dataclass(frozen=True)
class ChoiceProjection:
    value: str
    label: str


@dataclass(frozen=True)
class CampaignOptionsProjection:
    """O que o formulário de regra precisa saber sem hardcodar o domínio.

    O vocabulário de PÚBLICO vem daqui pelo mesmo motivo dos gatilhos: grupo novo no
    guestman aparece no seletor sem deploy de front, e a tela nunca oferece um segmento
    que o resolvedor não conhece.
    """

    triggers: tuple[ChoiceProjection, ...]
    platforms: tuple[ChoiceProjection, ...]
    templates: tuple[AnnouncementTemplateProjection, ...]
    variables: tuple[str, ...]
    customer_groups: tuple[ChoiceProjection, ...] = ()
    rfm_segments: tuple[ChoiceProjection, ...] = ()


# ── Posts ────────────────────────────────────────────────────────────


def _platform_label(platform: str) -> str:
    return dict(PLATFORM_CHOICES).get(platform, platform)


def _expires_in_minutes(announcement: Announcement, *, now) -> int:
    """Minutos até caducar. -1 = não expira; 0 = já passou da hora."""
    if not announcement.expires_at:
        return -1
    remaining = (announcement.expires_at - now).total_seconds() / 60
    return max(0, int(remaining))


def _result_detail(result: dict) -> str:
    """O PORQUÊ, venha da chave que vier.

    O handler grava ``reason`` no pending_manual e ``error`` na falha (nunca um
    ``detail`` genérico). Ler só uma das chaves deixaria o gestor com um "falhou"
    mudo — justamente a informação que ele precisa para agir.
    """
    for key in ("detail", "reason", "error"):
        value = result.get(key)
        if value:
            return str(value)

    # WhatsApp não falha em bloco: ele conta entregas. "38 enviados, 2 falharam"
    # é o resultado real de uma onda.
    if "sent" in result:
        sent = int(result.get("sent") or 0)
        failed = int(result.get("failed") or 0)
        parts = [f"{sent} enviados"]
        if failed:
            parts.append(f"{failed} falharam")
        return ", ".join(parts)
    return ""


def _platform_results(announcement: Announcement) -> tuple[PlatformResultProjection, ...]:
    """Resultado por plataforma, com as ainda sem resposta marcadas como `queued`.

    Plataforma alvejada e sem resultado não some da lista: silêncio no painel
    esconde exatamente o caso que o gestor precisa ver.
    """
    results = announcement.platform_results or {}
    return tuple(
        PlatformResultProjection(
            platform=platform,
            label=_platform_label(platform),
            status=str((results.get(platform) or {}).get("status") or "queued"),
            detail=_result_detail(results.get(platform) or {}),
            url=str((results.get(platform) or {}).get("url") or ""),
        )
        for platform in (announcement.platforms or [])
    )


def _iso(value) -> str:
    return value.isoformat() if value else ""


def build_announcement(announcement: Announcement, *, now=None) -> AnnouncementProjection:
    now = now or timezone.now()
    content = announcement.content or {}
    context = announcement.trigger_context or {}
    audience = announcement.audience or {}
    approver = announcement.approved_by

    return AnnouncementProjection(
        pk=announcement.pk,
        status=announcement.status,
        status_label=announcement.get_status_display(),
        body=str(content.get("body") or ""),
        image_url=str(content.get("image_url") or ""),
        hashtags=tuple(content.get("hashtags") or ()),
        link=str(content.get("link") or ""),
        platforms=tuple(announcement.platforms or ()),
        audience=dict(audience),
        audience_total=int(audience.get("total") or 0),
        platform_results=_platform_results(announcement),
        trigger=announcement.rule.trigger if announcement.rule_id else "",
        trigger_label=announcement.rule.get_trigger_display() if announcement.rule_id else "",
        rule_name=announcement.rule.name if announcement.rule_id else "",
        template_name=announcement.template.name if announcement.template_id else "",
        sku=str(context.get("sku") or ""),
        created_at=_iso(announcement.created_at),
        expires_at=_iso(announcement.expires_at),
        expires_in_minutes=_expires_in_minutes(announcement, now=now),
        published_at=_iso(announcement.published_at),
        approved_by=(approver.get_full_name() or approver.username) if approver else "",
    )


def _announcements_queryset():
    return Announcement.objects.select_related("rule", "template", "approved_by")


def build_board(*, now=None) -> CampaignBoardProjection:
    """Painel do gestor: o que pede decisão, o que já saiu, e o placar do dia."""
    now = now or timezone.now()
    today = timezone.localdate()

    pending = [
        announcement
        for announcement in _announcements_queryset().filter(status=AnnouncementStatus.PENDING_REVIEW)
        if not announcement.is_expired(now=now)
    ]
    recent = list(
        _announcements_queryset().filter(
            status__in=(AnnouncementStatus.PUBLISHED, AnnouncementStatus.PUBLISHING, AnnouncementStatus.FAILED),
            created_at__gte=now - RECENT_WINDOW,
        )[:50]
    )

    published_today = [
        announcement for announcement in recent
        if announcement.published_at and timezone.localtime(announcement.published_at).date() == today
    ]
    reached = sum(int((announcement.audience or {}).get("total") or 0) for announcement in published_today)

    return CampaignBoardProjection(
        pending=tuple(build_announcement(announcement, now=now) for announcement in pending),
        recent=tuple(build_announcement(announcement, now=now) for announcement in recent),
        stats=CampaignStatsProjection(
            pending_count=len(pending),
            published_today=len(published_today),
            audience_reached_today=reached,
            failed_today=sum(1 for announcement in recent if announcement.status == AnnouncementStatus.FAILED),
        ),
        reach_limits=_reach_limits(),
    )


def _reach_limits() -> tuple[ReachLimitProjection, ...]:
    """O que hoje impede ou limita a entrega, POR PLATAFORMA que as campanhas usam.

    Só reporta plataforma que alguma campanha ativa realmente pede: avisar sobre
    Instagram numa loja que só usa WhatsApp é ruído, e ruído treina o gestor a ignorar
    avisos.
    """
    from shopman.shop.models import Campaign
    from shopman.shop.services import delivery_readiness

    wanted: list[str] = []
    for campaign in Campaign.objects.filter(is_active=True):
        for platform in campaign.platforms or []:
            if platform not in wanted:
                wanted.append(platform)
    if not wanted:
        return ()

    limits: list[ReachLimitProjection] = []
    for state in delivery_readiness.readiness_for(wanted):
        if state.ready and not state.limitation:
            continue
        label = _platform_label(state.platform)
        if not state.ready:
            limits.append(
                ReachLimitProjection(
                    code=f"{state.platform}_blocked",
                    platform=state.platform,
                    platform_label=label,
                    title=f"{label}: não vai publicar",
                    detail=state.reason,
                    action=state.action,
                    blocking=True,
                )
            )
        else:
            limits.append(
                ReachLimitProjection(
                    code=f"{state.platform}_limited",
                    platform=state.platform,
                    platform_label=label,
                    title=f"{label}: alcance limitado",
                    detail=state.limitation,
                    action=state.action,
                    blocking=False,
                )
            )
    return tuple(limits)


def build_history(*, limit: int = 100, now=None) -> tuple[AnnouncementProjection, ...]:
    """Tudo que já saiu (ou tentou sair), do mais recente para o mais antigo."""
    now = now or timezone.now()
    announcements = _announcements_queryset().filter(
        status__in=(AnnouncementStatus.PUBLISHED, AnnouncementStatus.PUBLISHING, AnnouncementStatus.FAILED)
    )[:limit]
    return tuple(build_announcement(announcement, now=now) for announcement in announcements)


# ── Regras e modelos ─────────────────────────────────────────────────


def build_rule(rule: Campaign) -> CampaignProjection:
    return CampaignProjection(
        pk=rule.pk,
        name=rule.name,
        trigger=rule.trigger,
        trigger_label=rule.get_trigger_display(),
        trigger_filter=dict(rule.trigger_filter or {}),
        template_id=rule.template_id,
        template_name=rule.template.name if rule.template_id else "",
        platforms=tuple(rule.platforms or ()),
        audience_rules=dict(rule.audience_rules or {}),
        schedule=dict(rule.schedule or {}),
        requires_approval=rule.requires_approval,
        expires_after_minutes=rule.expires_after_minutes,
        is_active=rule.is_active,
    )


def build_rules() -> tuple[CampaignProjection, ...]:
    rules = Campaign.objects.select_related("template").all()
    return tuple(build_rule(rule) for rule in rules)


def build_template(template: AnnouncementTemplate) -> AnnouncementTemplateProjection:
    return AnnouncementTemplateProjection(
        pk=template.pk,
        name=template.name,
        body=template.body,
        variables=tuple(template.variables or ()),
        use_ai_generation=template.use_ai_generation,
        image_source=template.image_source,
        is_active=template.is_active,
    )


def build_templates() -> tuple[AnnouncementTemplateProjection, ...]:
    return tuple(build_template(template) for template in AnnouncementTemplate.objects.all())


def build_options() -> CampaignOptionsProjection:
    from shopman.shop.services.campaign import available_variables

    return CampaignOptionsProjection(
        triggers=tuple(
            ChoiceProjection(value=value, label=label) for value, label in Trigger.choices
        ),
        platforms=tuple(
            ChoiceProjection(value=value, label=label) for value, label in PLATFORM_CHOICES
        ),
        templates=build_templates(),
        variables=available_variables(),
        customer_groups=_customer_group_choices(),
        rfm_segments=_rfm_segment_choices(),
    )


def _customer_group_choices() -> tuple[ChoiceProjection, ...]:
    """Grupos de cliente do guestman, para o seletor de público."""
    try:
        from shopman.guestman.models import CustomerGroup

        return tuple(
            ChoiceProjection(value=group.ref, label=group.name)
            for group in CustomerGroup.objects.all().order_by("name")
        )
    except Exception:
        logger.warning("marketing.customer_groups_failed", exc_info=True)
        return ()


def _rfm_segment_choices() -> tuple[ChoiceProjection, ...]:
    """Segmentos RFM — vocabulário fechado, com dono no guestman."""
    try:
        from shopman.guestman.contrib.insights.models import RFM_SEGMENTS

        return tuple(
            ChoiceProjection(value=value, label=label) for value, label in RFM_SEGMENTS
        )
    except Exception:
        logger.warning("marketing.rfm_segments_failed", exc_info=True)
        return ()
