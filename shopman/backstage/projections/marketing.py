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
    #: Quem recusou e por quê. Vazio em tudo que não foi recusado — mostrar "recusado
    #: por —" num anúncio publicado seria ruído.
    rejected_by: str
    rejected_reason: str


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
class PlatformProjection:
    """Uma plataforma e tudo o que o gestor precisa saber para confiar nela.

    Diferente de `ReachLimitProjection`, que só reporta PROBLEMA das plataformas em uso:
    aqui vem TODA plataforma, pronta ou não. A tela de Plataformas responde "por onde eu
    consigo falar?", e uma lista que esconde as saudáveis não responde isso — ela força o
    gestor a deduzir ausência de aviso como boa notícia.
    """

    platform: str
    label: str
    #: `publication` (uma peça na plataforma) ou `direct_message` (uma mensagem por pessoa).
    #: A exigência de cada um é diferente, e é isso que o cartão explica.
    kind: str
    ready: bool
    reason: str = ""
    action: str = ""
    limitation: str = ""
    #: Alguma campanha ATIVA aponta para esta plataforma? Ligar credencial de algo que
    #: ninguém usa é trabalho jogado fora, e desligado-e-sem-uso não é problema.
    in_use: bool = False


@dataclass(frozen=True)
class CampaignBoardProjection:
    pending: tuple[AnnouncementProjection, ...]
    recent: tuple[AnnouncementProjection, ...]
    stats: CampaignStatsProjection
    reach_limits: tuple[ReachLimitProjection, ...] = ()
    #: Há credencial de IA neste ambiente? A tela pergunta ANTES de oferecer o botão de
    #: reescrever: oferecer e falhar depois ensina o gestor a não confiar no recurso.
    ai_assist_available: bool = False


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
    #: `Promotion.ref` da oferta anunciada. Vazio = campanha sem desconto atrás.
    promotion_ref: str
    schedule: dict
    #: Frase pronta do agendamento, decidida no servidor. O Admin e o app do gestor
    #: mostram a MESMA leitura porque nenhum dos dois reinterpreta o JSON.
    schedule_label: str
    #: Este agendamento cria a ocasião sozinho (`once`/`recurring`)?
    fires_on_its_own: bool
    #: Desempenho: as três perguntas que dizem se a campanha funciona, atreladas a uma
    #: decisão tomável na própria tela (desmarcar plataforma, arrumar credencial, mudar o
    #: texto). Não é dashboard — é o Histórico dissolvido onde ele serve.
    sent_count: int
    reached_total: int
    failed_count: int
    #: A razão da ÚLTIMA falha, por extenso. "Falhou" mudo é a informação que não ajuda.
    last_failure: str
    #: Dispara sozinho mas já não tem próxima ocasião — data passada ou período findo.
    #: Sem isto, uma campanha esgotada é indistinguível de uma que ainda não disparou.
    exhausted: bool
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
    #: ⚠️ A API aceitava GRAVAR `ai_prompt` e a projection não o devolvia: o gestor
    #: escrevia a instrução da IA e nunca mais a via. Config que só se escreve é config
    #: que ninguém confere.
    ai_prompt: str
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
    #: As faixas de preço (`PriceTier`) — varejo, atacado, staff.
    price_tiers: tuple[ChoiceProjection, ...] = ()
    #: As etiquetas que o operador criou (`CustomerTag`). É o único público que ele monta
    #: sozinho: RFM e churn são calculados, faixa é comercial, aniversário é cadastral.
    tags: tuple[ChoiceProjection, ...] = ()
    rfm_segments: tuple[ChoiceProjection, ...] = ()
    #: Ofertas vivas que a campanha pode anunciar. Só as que MONTAM sacola: uma promoção
    #: que vale para o cardápio todo não tem itens para montar, e oferecê-la aqui daria
    #: ao gestor um botão que promete o que não cumpre.
    offers: tuple[ChoiceProjection, ...] = ()


# ── Quantas pessoas isto alcança ─────────────────────────────────────
#
# ⚠️ Nasceu de uma pergunta do dono que não tinha como ser respondida pela tela: "nem sei
# quais ou quantas combinações temos". Escolher público era escolher no escuro e descobrir
# o tamanho depois do envio — quando já não tem desfazer.
#
# Só NÚMEROS, nunca destinatário: a mesma lei do `Announcement.audience`.

#: Rótulo de cada contagem que o resolvedor devolve. A ordem é a da leitura, não a do
#: dicionário: primeiro quem foi escolhido, depois quem se qualificou.
_AUDIENCE_PART_LABELS: tuple[tuple[str, str], ...] = (
    ("chosen_count", "Escolhidos um a um"),
    ("price_tiers_count", "Faixa de preço"),
    ("tags_count", "Etiquetas"),
    ("rfm_count", "Comportamento de compra"),
    ("churn_risk_count", "Estão sumindo"),
    ("birthday_count", "Aniversariantes de hoje"),
    ("bought_chosen_count", "Compraram o que você escolheu"),
    ("favorites_count", "Favoritaram o produto"),
    ("alerts_count", "Pediram para ser avisados"),
    ("bought_count", "Compraram o produto"),
)


@dataclass(frozen=True)
class AudiencePartProjection:
    """Quanta gente UMA regra achou, por si só."""

    label: str
    count: int


@dataclass(frozen=True)
class AudienceCountProjection:
    """O tamanho do público antes de enviar, e de onde ele vem.

    ``parts`` são contagens de ANTES da combinação. É a leitura das duas juntas que ensina
    o gestor o que somar e cruzar fazem: "leais 5, atacado 2, total 5" contra "leais 5,
    atacado 2, total 2" diz tudo sem uma linha de explicação.
    """

    total: int
    #: ``any`` soma as regras, ``all`` cruza.
    match: str
    match_label: str
    parts: tuple[AudiencePartProjection, ...]
    #: Quantos recebem primeiro quando a vantagem VIP está ligada. 0 = ninguém espera.
    vip_count: int
    #: Ninguém escolhido ainda — separa "não pedi nada" de "pedi e não achei ninguém",
    #: que na tela precisam dizer coisas diferentes.
    empty_selection: bool


def build_audience_count(rules: dict | None, *, sku: str = "") -> AudienceCountProjection:
    """Resolver o público SÓ para contar, pelo mesmo caminho do envio.

    Pelo mesmo caminho de propósito (``services/audience.resolve``): uma contagem com
    lógica própria concordaria hoje e divergiria no primeiro ajuste, e contagem que mente
    é pior que nenhuma, porque é acreditada.
    """
    from shopman.shop.services import audience as audience_service

    rules = dict(rules or {})
    result = audience_service.resolve(rules, sku=sku)
    counts = result.counts or {}

    parts = tuple(
        AudiencePartProjection(label=label, count=int(counts.get(key) or 0))
        for key, label in _AUDIENCE_PART_LABELS
        if key in counts
    )
    return AudienceCountProjection(
        total=result.total,
        match=result.match,
        match_label=(
            "cruzando as regras" if result.match == audience_service.MATCH_ALL
            else "somando as regras"
        ),
        parts=parts,
        vip_count=len(result.vip),
        empty_selection=not parts,
    )


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
    rejecter = announcement.rejected_by

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
        rejected_by=(rejecter.get_full_name() or rejecter.username) if rejecter else "",
        rejected_reason=announcement.rejected_reason,
    )


def _announcements_queryset():
    return Announcement.objects.select_related("rule", "template", "approved_by", "rejected_by")


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
        ai_assist_available=_ai_assist_available(),
    )


def _ai_assist_available() -> bool:
    from shopman.shop.services import copy_assist

    return copy_assist.is_configured()


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


def build_platforms() -> tuple[PlatformProjection, ...]:
    """O estado de entrega de TODAS as plataformas, na ordem do vocabulário.

    O cálculo é do `delivery_readiness` — ele foi escrito exatamente para isto, e nasceu de
    uma correção do dono: a primeira versão só sabia falar de WhatsApp.
    """
    from shopman.shop.models import Campaign
    from shopman.shop.services import delivery_readiness

    used: set[str] = set()
    for campaign in Campaign.objects.filter(is_active=True).only("platforms"):
        used.update(campaign.platforms or [])

    labels = dict(PLATFORM_CHOICES)
    states = delivery_readiness.readiness_for([ref for ref, _label in PLATFORM_CHOICES])
    return tuple(
        PlatformProjection(
            platform=state.platform,
            label=labels.get(state.platform, state.platform),
            kind=state.kind,
            ready=state.ready,
            reason=state.reason,
            action=state.action,
            limitation=state.limitation,
            in_use=state.platform in used,
        )
        for state in states
    )


def build_history(*, limit: int = 100, now=None) -> tuple[AnnouncementProjection, ...]:
    """Tudo que já saiu (ou tentou sair), do mais recente para o mais antigo."""
    now = now or timezone.now()
    announcements = _announcements_queryset().filter(
        status__in=(AnnouncementStatus.PUBLISHED, AnnouncementStatus.PUBLISHING, AnnouncementStatus.FAILED)
    )[:limit]
    return tuple(build_announcement(announcement, now=now) for announcement in announcements)


# ── Regras e modelos ─────────────────────────────────────────────────


def build_rule(rule: Campaign, *, performance: dict | None = None) -> CampaignProjection:
    """Uma campanha. ``performance`` pronto evita N+1 quando a lista inteira é montada."""
    from shopman.shop.services import campaign_schedule as sched

    fires = sched.fires_on_its_own(rule.schedule)
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
        promotion_ref=rule.promotion_ref,
        schedule=dict(rule.schedule or {}),
        **(performance if performance is not None else _performance_by_rule([rule.pk])[rule.pk]),
        schedule_label=sched.describe_occurrence(rule.schedule) if fires else sched.describe(rule.schedule),
        fires_on_its_own=fires,
        exhausted=fires and sched.next_occurrence(rule.schedule) is None,
        requires_approval=rule.requires_approval,
        expires_after_minutes=rule.expires_after_minutes,
        is_active=rule.is_active,
    )


def _stated_reason(result: dict) -> str:
    """A razão escrita da falha, ou vazio. Sem cair no resumo de contagem."""
    for key in ("detail", "reason", "error"):
        value = result.get(key)
        if value:
            return str(value)
    return ""


def _performance_by_rule(rule_ids: list[int]) -> dict[int, dict]:
    """Desempenho de VÁRIAS campanhas em UMA consulta.

    ⚠️ Uma consulta por campanha seria N+1 na tela que lista todas — a mesma dívida que o
    PR #114 pagou. O dado já existe em `platform_results`; agregar aqui evita inventar
    tabela de agregação, que a ADR-020 §11 proíbe com razão.
    """
    blank = {"sent_count": 0, "reached_total": 0, "failed_count": 0, "last_failure": ""}
    out = {rule_id: dict(blank) for rule_id in rule_ids}
    if not rule_ids:
        return out

    announcements = (
        Announcement.objects.filter(rule_id__in=rule_ids)
        .only("rule_id", "audience", "platform_results", "created_at")
        .order_by("-created_at")
    )
    for announcement in announcements:
        bucket = out.get(announcement.rule_id)
        if bucket is None:
            continue
        entries = [
            entry for entry in (announcement.platform_results or {}).values()
            if isinstance(entry, dict)
        ]
        if any(entry.get("status") == "published" for entry in entries):
            bucket["sent_count"] += 1
            bucket["reached_total"] += int((announcement.audience or {}).get("total") or 0)
        broken = [entry for entry in entries if entry.get("status") == "failed"]
        if broken:
            bucket["failed_count"] += 1
            # ⚠️ Só razão EXPLÍCITA. `_result_detail` cai num resumo de contagem
            # ("0 enviados, 3 falharam") quando não há motivo escrito, e contagem prefixada
            # por "1 falha:" lê como causa sem ser — confunde mais que o silêncio.
            bucket["last_failure"] = bucket["last_failure"] or _stated_reason(broken[0])
    return out


def build_rules() -> tuple[CampaignProjection, ...]:
    rules = list(Campaign.objects.select_related("template").all())
    performance = _performance_by_rule([rule.pk for rule in rules])
    return tuple(build_rule(rule, performance=performance[rule.pk]) for rule in rules)


def build_template(template: AnnouncementTemplate) -> AnnouncementTemplateProjection:
    return AnnouncementTemplateProjection(
        pk=template.pk,
        name=template.name,
        body=template.body,
        variables=tuple(template.variables or ()),
        use_ai_generation=template.use_ai_generation,
        ai_prompt=template.ai_prompt,
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
        price_tiers=_price_tier_choices(),
        tags=_tag_choices(),
        rfm_segments=_rfm_segment_choices(),
        offers=_offer_choices(),
    )


def _offer_choices() -> tuple[ChoiceProjection, ...]:
    """Promoções vivas que nomeiam itens, para o seletor de oferta da campanha."""
    from shopman.shop.services import offers as offer_service
    from shopman.shop.services import promotions as promotion_service

    try:
        live = promotion_service.get_active_promotions(timezone.now())
    except Exception:
        logger.warning("marketing.offers_failed", exc_info=True)
        return ()

    return tuple(
        ChoiceProjection(value=promotion.ref, label=promotion.name)
        for promotion in live
        if offer_service.offer_skus(promotion)
    )


def _price_tier_choices() -> tuple[ChoiceProjection, ...]:
    """Grupos de cliente do guestman, para o seletor de público."""
    try:
        from shopman.guestman.models import PriceTier

        return tuple(
            ChoiceProjection(value=tier.ref, label=tier.name)
            for tier in PriceTier.objects.all().order_by("name")
        )
    except Exception:
        logger.warning("marketing.price_tiers_failed", exc_info=True)
        return ()


def _tag_choices() -> tuple[ChoiceProjection, ...]:
    """Etiquetas existentes, com quantos clientes cada uma tem.

    A contagem vai no rótulo porque etiqueta sem gente é o erro mais comum aqui: alguém
    cria "corredores", nunca etiqueta ninguém, e a campanha alcança zero sem dizer por quê.
    """
    try:
        from django.db.models import Count
        from shopman.guestman.models import CustomerTag

        return tuple(
            ChoiceProjection(
                value=tag.slug,
                label=f"{tag.name} ({tag.people})" if tag.people else f"{tag.name} (ninguém)",
            )
            for tag in CustomerTag.objects.annotate(people=Count("tagged_items")).order_by("name")
        )
    except Exception:
        logger.warning("marketing.tags_failed", exc_info=True)
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
