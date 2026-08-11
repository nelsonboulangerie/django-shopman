"""CampaignService — evento operacional vira conteúdo, conteúdo vira announcement.

O fluxo inteiro (FOMO-MARKETING-SPECS §2.2):

    fornada concluída → evaluate() → casa Campaigns → resolve conteúdo
    → resolve audiência → cria Announcement → notifica o gestor
    → approve() → Directives por plataforma

Duas escolhas estruturais:

- **Directive por plataforma.** Publicar é I/O externo e falível. Cada
  plataforma vira uma Directive com dedupe_key própria, então retry e
  idempotência vêm de graça do Core (ADR-003) e uma falha no Instagram não
  derruba o Google Business.
- **A audiência é resolvida na criação, mas os destinatários não são
  persistidos.** ``Announcement.audience`` guarda só contagens; a lista real
  é recalculada no despacho. Anúncio que dorme 20 min esperando aprovação não
  pode disparar para uma audiência congelada e vencida.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from shopman.shop.directives import ANNOUNCEMENT_NOTIFY, ANNOUNCEMENT_PUBLISH, create_deduped
from shopman.shop.models import (
    QUALITY_LEVELS,
    Announcement,
    AnnouncementStatus,
    Campaign,
    Trigger,
)
from shopman.shop.services import audience as audience_service
from shopman.shop.services import campaign_schedule

logger = logging.getLogger(__name__)

#: Plataformas que publicam conteúdo (vs. notificar audiência direta).
POSTING_PLATFORMS = ("instagram", "facebook", "google_business")


class CampaignError(Exception):
    """Erro de negócio da campanha (announcement inexistente, estado inválido)."""


# ── Avaliação ────────────────────────────────────────────────────────


def evaluate(trigger: str, context: dict | None = None) -> list[Announcement]:
    """Avaliar as regras ativas de um trigger e criar os announcements que couberem.

    Args:
        trigger: valor de ``Trigger`` (ex.: ``production_finished``).
        context: snapshot do evento — ``sku``, ``quality``, ``quantity``,
            ``work_order_ref``, ``available_qty``…

    Returns:
        Os announcements criados. Lista vazia é resposta normal (nenhuma regra casou).
    """
    context = dict(context or {})
    rules = Campaign.objects.filter(trigger=trigger, is_active=True).select_related(
        "template"
    )

    announcements = []
    for rule in rules:
        try:
            if not matches_filter(rule, context):
                continue
            announcements.append(_create_announcement(rule, context))
        except Exception:
            # Uma regra quebrada não pode calar as outras nem derrubar a
            # transação da fornada que a disparou.
            logger.warning(
                "campaign.rule_failed rule=%s trigger=%s", rule.pk, trigger, exc_info=True
            )
    return announcements


def fire_now(
    campaign_id: int,
    *,
    context: dict | None = None,
    audience_rules: dict | None = None,
    body: str = "",
    author=None,
) -> Announcement:
    """Disparar UMA campanha agora, sem esperar evento. É a Action do gestor.

    Existe porque campanha manual não tem evento que a acorde: quem decide é a pessoa,
    e ela decide agora. Reusa `_create_announcement` inteiro em vez de duplicar a
    montagem de conteúdo, audiência, expiração e notificação — duplicar isso seria
    criar um segundo caminho de criação que divergiria do primeiro no primeiro ajuste.

    ``audience_rules`` permite escolher o público neste disparo sem alterar a campanha
    salva: a mesma campanha "novidade da semana" serve a públicos diferentes em semanas
    diferentes. Vazio usa o público da campanha.

    ``body`` é o texto que o gestor escreveu na hora. Quando ele vem, **o anúncio publica
    direto**, com o autor registrado como aprovador: não existe segundo par de olhos quando
    o autor e o revisor são a mesma pessoa (ADR-020 §8). Vazio mantém o caminho de sempre —
    o texto vem do modelo, então quem escreveu foi o sistema, e aí a revisão tem função.

    Levanta ``CampaignError`` se a campanha não existe ou está inativa — disparar uma
    campanha desligada é quase sempre engano, e o silêncio esconderia o engano.
    """
    rule = (
        Campaign.objects.filter(pk=campaign_id, is_active=True)
        .select_related("template")
        .first()
    )
    if rule is None:
        raise CampaignError("Campanha não encontrada ou inativa.")

    payload = dict(context or {})
    payload.setdefault("trigger", Trigger.MANUAL)

    if audience_rules:
        # A campanha salva NÃO muda — é escolha deste disparo. Mas a escolha tem de
        # VIAJAR COM O ANÚNCIO: o handler de envio re-resolve a audiência na hora de
        # despachar (de propósito, porque entre a criação e a aprovação favoritos e
        # alertas mudam), e sem isto ele releria as regras da campanha e alcançaria
        # ninguém — o anúncio prometeria 3 pessoas na tela e enviaria para 0.
        rule.audience_rules = dict(audience_rules)
        payload["audience_rules"] = dict(audience_rules)

    written = (body or "").strip()
    if written:
        # Escrito pelo gestor: não passa por revisão, e o `requires_approval` da campanha
        # não é atropelado em silêncio — ele vale para o que a OPERAÇÃO gerou (fornada,
        # estoque baixo), que é o caso em que existe alguém diferente para conferir.
        rule.requires_approval = False
    announcement = _create_announcement(rule, payload, body=written)

    if written and author is not None and getattr(author, "pk", None):
        # O autor fica gravado como aprovador porque foi ele quem decidiu publicar. Sem
        # isso, um anúncio publicado sem revisão não teria nenhum nome atrás.
        Announcement.objects.filter(pk=announcement.pk).update(
            approved_by=author, approved_at=timezone.now()
        )
        announcement.refresh_from_db(fields=["approved_by", "approved_at"])
    return announcement


def _create_announcement(
    rule: Campaign, context: dict, *, occurrence_key: str = "", body: str = ""
) -> Announcement:
    sku = context.get("sku", "")
    content = resolve_content(
        rule.template, context, promotion_ref=rule.promotion_ref, override_body=body
    )
    resolved = audience_service.resolve(rule.audience_rules, sku=sku)

    # Fora da janela preferida, o announcement nasce com hora marcada. Vale para os dois
    # caminhos: no automático o ``dispatch_due`` abre a porta na hora; no que
    # exige revisão a hora fica como sugestão da regra, e o gestor confirma ou
    # atropela.
    publish_at = campaign_schedule.next_publish_at(rule.schedule)

    announcement = Announcement.objects.create(
        rule=rule,
        template=rule.template,
        status=AnnouncementStatus.PENDING_REVIEW if rule.requires_approval else AnnouncementStatus.APPROVED,
        content=content,
        platform_content=_platform_content(rule.template, content),
        platforms=list(rule.platforms or []),
        audience=resolved.summary(),
        trigger_context=context,
        occurrence_key=occurrence_key,
        publish_at=publish_at,
        expires_at=_expiry(rule),
    )

    if rule.requires_approval:
        notify_reviewers(rule, announcement)
    elif publish_at is None:
        dispatch(announcement)
    return announcement


def matches_filter(rule: Campaign, context: dict) -> bool:
    """Condições extras do ``trigger_filter``. Filtro ausente = casa sempre."""
    rule_filter = rule.trigger_filter or {}

    collections = rule_filter.get("collections")
    if collections:
        item_collections = context.get("collections") or []
        if not any(ref in collections for ref in item_collections):
            return False

    skus = rule_filter.get("skus")
    if skus and context.get("sku") not in skus:
        return False

    quality_min = rule_filter.get("quality_min")
    if quality_min and not _quality_at_least(context.get("quality"), quality_min):
        return False

    max_remaining = rule_filter.get("max_remaining")
    if max_remaining is not None:
        try:
            if int(context.get("available_qty") or 0) > int(max_remaining):
                return False
        except (TypeError, ValueError):
            return False

    return True


def _quality_at_least(quality, minimum) -> bool:
    """Hierarquia excelente > bom > regular. Qualidade não informada = "bom"."""
    quality = str(quality or "bom")
    if quality not in QUALITY_LEVELS or minimum not in QUALITY_LEVELS:
        return False
    return QUALITY_LEVELS.index(quality) >= QUALITY_LEVELS.index(minimum)


def _expiry(rule: Campaign):
    minutes = int(rule.expires_after_minutes or 0)
    if minutes <= 0 or not rule.requires_approval:
        return None
    return timezone.now() + timedelta(minutes=minutes)


# ── Conteúdo ─────────────────────────────────────────────────────────


def resolve_content(
    template, context: dict, *, promotion_ref: str = "", override_body: str = ""
) -> dict:
    """Renderizar o template com as variáveis do evento.

    ``override_body`` vazio é o caminho normal; preenchido, é o gestor escrevendo na hora.

    Quando a campanha anuncia uma oferta, o `{{link}}` deixa de apontar para o produto e
    passa a apontar para a **oferta** — é o link que vai na mensagem, e mandar o cliente
    para a página do produto quando existe uma promoção atrás desperdiçaria o clique.
    A `Action` vai junto, para a superfície montar a sacola (ADR-012 + ADR-020 §9).
    """
    variables = resolve_variables(context, promotion_ref=promotion_ref)
    # `override_body` é o texto que o gestor escreveu, e ele vence tudo — inclusive a IA,
    # que **nem é chamada**: pedir sugestão para substituir por um texto que já existe
    # gastaria uma chamada para jogar fora. As outras chaves seguem vindo do modelo:
    # hashtags, imagem e link da oferta não são o que ele digitou.
    body = override_body or _ai_body(template, variables) or render(template.body, variables)
    content = {
        "body": body,
        "hashtags": variables["hashtags_list"],
        "link": variables["link"],
        "image_url": _image_url(template, context),
        "variables": {k: v for k, v in variables.items() if not k.endswith("_list")},
    }
    if promotion_ref:
        from shopman.shop.services.offers import offer_action

        content["actions"] = [offer_action(promotion_ref)]
    return content


def _ai_body(template, variables: dict) -> str:
    """Corpo escrito pela IA, quando o modelo pede. Vazio = usar o template.

    ⚠️ Falha da IA **nunca** trava a operação: a fornada saiu, e o anúncio dela precisa
    existir com ou sem assistente. Toda saída ruim (sem credencial, provedor mudo,
    resposta vazia) devolve vazio e o template renderizado vale — mesma assimetria do
    agendamento que adia, e pelo mesmo motivo.

    Este é o leitor que faltava: `use_ai_generation` e `ai_prompt` eram configuráveis no
    Admin, na API e na projection, e **ninguém os lia** — um interruptor ligado em nada.
    """
    if not getattr(template, "use_ai_generation", False):
        return ""

    from shopman.shop.services import copy_assist

    if not copy_assist.is_configured():
        logger.info("campaign.ai_body_skipped template=%s reason=not_configured", template.pk)
        return ""

    try:
        return copy_assist.suggest(_ai_prompt(template, variables), max_tokens=600)
    except Exception:
        logger.warning("campaign.ai_body_failed template=%s", template.pk, exc_info=True)
        return ""


@dataclass(frozen=True)
class TestSend:
    """O que saiu num envio de teste, e o que o transporte respondeu."""

    accepted: bool
    backend: str
    recipient: str
    fields: dict
    detail: str = ""


def send_test(
    recipient: str, *, sku: str = "", name: str = "", body: str = "", backend: str = "",
) -> TestSend:
    """Mandar UM anúncio de teste para UM destinatário. Sem audiência, sem consentimento.

    Existe porque "o painel diz enviado" e "o celular vibrou" são fatos diferentes, e só o
    segundo prova que o template aprovado renderiza. Manda as MESMAS chaves do caminho de
    produção, com valores REAIS do catálogo e da disponibilidade — um teste que mande
    menos prova só que o transporte responde.

    **Não é porta dos fundos do consentimento:** um destinatário por chamada, escolhido
    por quem tem a permissão de campanha, e nenhuma resolução de audiência. Serve para o
    gestor testar o próprio número, e é assim que a tela o oferece.
    """
    from shopman.shop.handlers.campaign import _whatsapp_backend
    from shopman.shop.notifications import notify

    target = (recipient or "").strip()
    if not target:
        raise CampaignError("Informe o WhatsApp (ou o subscriber) que vai receber o teste.")
    if "," in target or " " in target:
        # Um por chamada, de propósito: aceitar lista transformaria isto em disparo.
        raise CampaignError("Um destinatário por teste. Isto não faz lote.")

    transport = backend or _whatsapp_backend()
    if transport is None:
        raise CampaignError(
            "Nenhum transporte de WhatsApp configurado neste ambiente. Sem credencial, "
            "o teste não prova nada."
        )

    fields = test_fields(sku=sku, name=name)
    message = (body or "").strip() or (
        "Teste do Shopman: se você recebeu isto, o template está de pé."
    )
    try:
        result = notify(
            event="announcement_published",
            recipient=target,
            context={
                "body": message,
                "cta": "Garanta o seu:",
                "action_url": fields.get("link", ""),
                **fields,
            },
            backend=transport,
        )
    except Exception as exc:
        logger.warning("campaign.test_send_failed recipient=%s", target, exc_info=True)
        return TestSend(
            accepted=False, backend=transport, recipient=target,
            fields=fields, detail=str(exc),
        )

    accepted = bool(getattr(result, "success", False))
    return TestSend(
        accepted=accepted,
        backend=transport,
        recipient=target,
        fields=fields,
        detail="" if accepted else str(getattr(result, "error", "") or "o transporte recusou"),
    )


def test_fields(*, sku: str = "", name: str = "") -> dict:
    """As variáveis que o template aprovado espera, com valores reais quando houver.

    `available_qty` sai da disponibilidade de VERDADE: número inventado validaria a
    fiação e mentiria sobre o conteúdo. Vazio quando não dá para saber — a mensagem então
    sai sem número, que é honesto.
    """
    sku = (sku or "").strip()
    fields = {
        "customer_name": (name or "").strip(),
        "product_name": "",
        "product_sku": sku,
        "available_qty": "",
        "product_image_url": "",
        "link": "",
    }
    if not sku:
        return fields

    product = _product(sku)
    fields["product_name"] = getattr(product, "name", "") or sku
    fields["product_image_url"] = product_image_url(sku)

    try:
        from shopman.shop.handlers.campaign import _available_qty

        qty = _available_qty(sku)
        fields["available_qty"] = str(qty) if qty else ""
    except Exception:
        logger.warning("campaign.test_qty_failed sku=%s", sku, exc_info=True)

    fields["link"] = _product_link(sku)
    return fields


def preview(
    body: str, *, sku: str = "", promotion_ref: str = "", use_ai: bool = False,
) -> dict:
    """Como a mensagem VAI FICAR, resolvida pelo mesmo caminho do envio.

    Existe porque até agora o gestor escrevia `{{product_name}}` e só descobria o resultado
    quando a mensagem chegava no celular de um cliente. Variável com nome errado renderiza
    vazio em silêncio, e foi assim que passaram despercebidos um `customer_name` que ninguém
    mandava e uma foto em caminho relativo que a Meta não carrega.

    ⚠️ **Mesmo resolvedor do envio, de propósito.** Se a prévia tivesse a própria montagem,
    ela concordaria com o envio hoje e divergiria no primeiro ajuste — e uma prévia que mente
    é pior que prévia nenhuma, porque ela é acreditada.

    ⚠️ **A IA não é chamada aqui.** `use_ai` só informa a tela de que o corpo final será
    escrito por ela; gerar texto a cada tecla digitada gastaria chamada para jogar fora. Quem
    pede sugestão é o botão de reescrever, explicitamente.

    ``sku`` vazio escolhe um produto real da loja, para a prévia funcionar sem o gestor ter de
    saber um SKU de cabeça — e devolve qual usou, porque prévia com produto anônimo não
    explica o que está vendo.
    """
    sample = (sku or "").strip() or _sample_sku()
    variables = resolve_variables({"sku": sample}, promotion_ref=promotion_ref)

    return {
        "sku": sample,
        "body": render(body or "", variables),
        "product_name": variables["product_name"],
        "product_image_url": variables["product_image_url"],
        "link": variables["link"],
        "hashtags": variables["hashtags_list"],
        # Os campos discretos que o template aprovado recebe. É o que explica variável vazia
        # no aparelho antes de o aparelho existir.
        "fields": {
            key: variables[key]
            for key in ("customer_name", "product_name", "product_sku", "available_qty")
            if key in variables
        },
        "ai_writes": bool(use_ai),
    }


def _sample_sku() -> str:
    """Um produto real para a prévia, ou vazio numa loja sem catálogo."""
    try:
        from shopman.offerman.models import Product

        product = (
            Product.objects.filter(is_published=True, is_sellable=True)
            .order_by("name")
            .only("sku")
            .first()
        )
        return product.sku if product else ""
    except Exception:
        logger.warning("campaign.preview_sample_failed", exc_info=True)
        return ""


def rewrite_body(announcement_id: int, *, current_body: str = "") -> str:
    """Uma sugestão de corpo para um anúncio em revisão. Não grava nada.

    Existe porque o `use_ai_generation` do modelo decide no NASCIMENTO do anúncio, e o
    gestor às vezes quer a IA justamente no anúncio que nasceu do template. Aqui ele pede,
    lê e aceita ou descarta — quem persiste é o PATCH do anúncio, depois do "Aceitar".

    Levanta as exceções do `copy_assist` para a camada HTTP mapear (503 sem credencial).
    """
    from shopman.shop.services import copy_assist

    try:
        announcement = Announcement.objects.select_related("template", "rule").get(pk=announcement_id)
    except Announcement.DoesNotExist as exc:
        raise CampaignError("Anúncio não encontrado.") from exc

    if announcement.status not in (AnnouncementStatus.DRAFT, AnnouncementStatus.PENDING_REVIEW):
        raise CampaignError("Este anúncio já saiu. Não dá para reescrever o que já foi lido.")

    variables = resolve_variables(
        announcement.trigger_context or {},
        promotion_ref=announcement.rule.promotion_ref if announcement.rule_id else "",
    )
    template = announcement.template
    prompt = _ai_prompt(template, variables) if template else _ai_prompt(_BareTemplate(), variables)

    body = (current_body or (announcement.content or {}).get("body") or "").strip()
    if body:
        prompt += (
            "\n\nO anúncio está escrito assim agora. Proponha uma versão melhor, "
            f"mantendo os fatos:\n{body}"
        )
    return copy_assist.suggest(prompt, max_tokens=600)


class _BareTemplate:
    """Modelo ausente: anúncio órfão de template ainda merece sugestão."""

    pk = None
    body = ""
    ai_prompt = ""
    use_ai_generation = False


def _ai_prompt(template, variables: dict) -> str:
    """A instrução do modelo + o que aconteceu de fato.

    O contexto do evento vai junto porque sem ele a IA escreve propaganda genérica: o
    valor do anúncio é dizer que ESTE pão saiu do forno AGORA, e é isso que as variáveis
    carregam. O template renderizado entra como referência de formato, não para ser
    repetido.
    """
    facts = "\n".join(
        f"{key}: {value}"
        for key, value in variables.items()
        if value and not key.endswith("_list")
    )
    parts = [
        "O que acabou de acontecer na padaria:",
        facts,
        "",
        "Tarefa: escreva a mensagem do anúncio, 1 a 3 frases curtas, pronta para sair no "
        "WhatsApp e nas redes. Use só os fatos acima — não invente preço, prazo, sabor "
        "nem quantidade que não estejam aí.",
    ]
    instruction = (getattr(template, "ai_prompt", "") or "").strip()
    if instruction:
        parts += ["", "Instrução desta campanha:", instruction]
    reference = render(template.body, variables).strip()
    if reference:
        parts += ["", "Versão do modelo, como referência de formato (não repita):", reference]
    return "\n".join(parts)


def _platform_content(template, content: dict) -> dict:
    """Só grava override onde o template realmente diverge do corpo padrão."""
    out = {}
    for platform, variant in (template.platform_variants or {}).items():
        if not isinstance(variant, dict) or not variant.get("body"):
            continue
        out[platform] = {**variant, "body": content["body"]}
    return out


def render(body: str, variables: dict) -> str:
    """Substituir ``{{var}}`` pelos valores. Variável desconhecida vira vazio.

    Deixar o ``{{cru}}`` na tela seria pior que o silêncio: o gestor aprovaria
    sem perceber e o cliente veria o template.
    """
    import re

    def _replace(match):
        return str(variables.get(match.group(1).strip(), ""))

    rendered = re.sub(r"\{\{\s*([\w_]+)\s*\}\}", _replace, body or "")
    # Um {{price}} vazio no meio da frase deixa espaço duplo.
    return re.sub(r"[ \t]{2,}", " ", rendered).strip()


def resolve_variables(context: dict, *, promotion_ref: str = "") -> dict:
    """As variáveis disponíveis para um template (FOMO-MARKETING-SPECS §3.2)."""
    sku = context.get("sku", "")
    product = _product(sku)
    hashtags = _hashtags(product)

    return {
        "product_name": getattr(product, "name", "") or sku,
        #: ⚠️ Havia `sku` E `product_sku` aqui, com o MESMO valor e as duas anunciadas ao
        #: gestor — duas formas de escrever a mesma coisa num vocabulário que existe para
        #: ser pequeno. `sku` saiu: `product_sku` é o nome que a mensagem usa (o sufixo que
        #: o template gruda no fim do link do botão) e o único que vira campo no ManyChat.
        #: O `sku` interno continua vivo onde é interno, no `trigger_context`.
        "product_sku": sku,
        "price": _price(product),
        "hashtags": " ".join(f"#{tag}" for tag in hashtags),
        "hashtags_list": hashtags,
        "link": _offer_link(promotion_ref) if promotion_ref else _product_link(sku),
        #: Quantas há AGORA — a única contagem que a mensagem conhece. O nome é o mesmo
        #: do caminho de alerta de estoque, de propósito: um template genérico serve os
        #: dois, e dois nomes para a mesma pergunta garantiriam que um renderizasse vazio.
        #:
        #: ⚠️ Não existe variável de "quantas saíram na fornada", e é decisão do dono:
        #: essa contagem não interessa a quem recebe, e oferecê-la só criaria a chance de
        #: anunciar um número que já não é verdade.
        "available_qty": str(context.get("available_qty", "") or ""),
        #: Foto do produto, absoluta. O prefixo `product_` é namespacing: o campo vive no
        #: perfil do assinante no ManyChat, ao lado de tudo o que já existe lá, e
        #: `image_url` solto colidiria com qualquer outra imagem que a conta use.
        #:
        #: ⚠️ Não confundir com `content["image_url"]`, que é a imagem DO ANÚNCIO (card
        #: do gestor e post externo). Consumidores diferentes, nomes diferentes.
        "product_image_url": product_image_url(sku),
        "time": timezone.localtime().strftime("%Hh%M"),
        "store_name": _brand_name(),
        "quality": str(context.get("quality", "") or ""),
    }


def available_variables() -> tuple[str, ...]:
    """Nomes válidos num template — documentação viva para o Admin."""
    return (
        "product_name", "product_sku", "price", "hashtags", "link",
        "available_qty", "product_image_url", "time", "store_name", "quality",
        "customer_name",
    )


def _product(sku: str):
    if not sku:
        return None
    try:
        from shopman.shop.projections import catalog_context

        return catalog_context.get_product(sku)
    except Exception:
        logger.debug("campaign.product_lookup_failed sku=%s", sku, exc_info=True)
        return None


def _price(product) -> str:
    if product is None:
        return ""
    try:
        from shopman.utils.monetary import format_money

        price_q = int(getattr(product, "base_price_q", 0) or 0)
        return f"R$ {format_money(price_q)}" if price_q else ""
    except Exception:
        logger.debug("campaign.price_failed", exc_info=True)
        return ""


def _hashtags(product) -> list[str]:
    """Hashtags do PIM social, em ``Product.metadata["social"]["hashtags"]``.

    Leitura direta do JSONField (schema em docs/reference/data-schemas.md) em
    vez de importar ``offerman.contrib.social``: o shop consome APIs públicas
    do kernel, nunca submódulos internos.
    """
    metadata = getattr(product, "metadata", None)
    if not isinstance(metadata, dict):
        return []
    social = metadata.get("social")
    if not isinstance(social, dict):
        return []
    tags = social.get("hashtags") or []
    return [str(tag) for tag in tags if str(tag).strip()]


def _offer_link(promotion_ref: str) -> str:
    """Link NÃO autenticado da oferta. Ver `services/offers.py` para o porquê."""
    try:
        from shopman.shop.services import storefront_links

        return storefront_links.offer_url(promotion_ref)
    except Exception:
        logger.debug("campaign.offer_link_failed ref=%s", promotion_ref, exc_info=True)
        return ""


def _product_link(sku: str) -> str:
    if not sku:
        return ""
    try:
        from shopman.shop.services import storefront_links

        return storefront_links.product_url(sku)
    except Exception:
        logger.debug("campaign.link_failed sku=%s", sku, exc_info=True)
        return ""


def _brand_name() -> str:
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        return (getattr(shop, "brand_name", "") or getattr(shop, "name", "")) if shop else ""
    except Exception:
        logger.debug("campaign.brand_failed", exc_info=True)
        return ""


def product_image_url(sku: str) -> str:
    """Foto do produto, sempre ABSOLUTA — ou vazia.

    O cabeçalho de mídia de um template aprovado é buscado pelos servidores da Meta, não
    pelo navegador do cliente: caminho relativo simplesmente não carrega, e o template
    chega sem imagem. Então relativo é resolvido contra a base da loja, e o que não der
    para absolutizar volta vazio — melhor sem foto que com foto quebrada.
    """
    raw = str(getattr(_product(sku), "image_url", "") or "").strip()
    if not raw or raw.startswith(("http://", "https://")):
        return raw
    try:
        from shopman.shop.services import storefront_links

        base = storefront_links.storefront_base_url()
    except Exception:
        logger.warning("campaign.image_base_failed sku=%s", sku, exc_info=True)
        return ""
    if not base:
        return ""
    return f"{base}/{raw.lstrip('/')}"


def _image_url(template, context: dict) -> str:
    source = getattr(template, "image_source", "product")
    if source == "none":
        return ""
    if source == "custom":
        return str((template.platform_variants or {}).get("image_url") or "")
    product = _product(context.get("sku", ""))
    return str(getattr(product, "image_url", "") or "")


# ── Aprovação e despacho ─────────────────────────────────────────────


def approve(announcement_id: int, user, *, publish_at=None, respect_schedule: bool = True) -> Announcement:
    """Gestor aprova e o announcement sai. Idempotente para quem clica duas vezes.

    Com ``publish_at`` no futuro, o announcement fica APROVADO e agendado: quem
    despacha é ``dispatch_due`` no ciclo de manutenção. Reagendar um announcement que
    ainda não saiu é permitido (só muda a hora); um já despachado, não.

    Sem ``publish_at``, a hora sugerida pela regra na criação (janela preferida)
    é honrada — aprovar às 5h um announcement cuja regra pede 7h agenda para as 7h.
    ``respect_schedule=False`` é o "Publicar agora" do gestor, que vence a
    janela.
    """
    try:
        announcement = Announcement.objects.get(pk=announcement_id)
    except Announcement.DoesNotExist as exc:
        raise CampaignError("Anúncio não encontrado.") from exc

    now = timezone.now()
    if publish_at is None and respect_schedule:
        publish_at = announcement.publish_at
    scheduled = publish_at is not None and publish_at > now

    if announcement.status in (AnnouncementStatus.PUBLISHED, AnnouncementStatus.PUBLISHING):
        return announcement
    if announcement.status == AnnouncementStatus.APPROVED and not announcement.publish_at:
        # Já despachado (aprovação imediata anterior) — nada a refazer.
        return announcement
    if announcement.status == AnnouncementStatus.EXPIRED or announcement.is_expired(now=now):
        raise CampaignError("Este announcement expirou. O momento dele já passou.")
    # ⚠️ Recusado não é publicável. Antes de a recusa existir como estado, ela virava
    # `expired` e caía na guarda acima por acidente; agora precisa da sua própria, ou
    # um anúncio recusado com prazo em aberto voltaria ao ar por uma segunda aprovação.
    if announcement.status == AnnouncementStatus.REJECTED:
        raise CampaignError("Este anúncio foi recusado. Crie outro em vez de reaproveitar.")

    announcement.status = AnnouncementStatus.APPROVED
    announcement.approved_by = user if getattr(user, "pk", None) else None
    announcement.approved_at = now
    announcement.publish_at = publish_at if scheduled else None
    announcement.save(update_fields=["status", "approved_by", "approved_at", "publish_at"])

    if not scheduled:
        dispatch(announcement)
    return announcement


def update_content(
    announcement_id: int, *, body=None, hashtags=None, platforms=None, image_url=None
) -> Announcement:
    """Editar o announcement antes de aprovar. Só o que o gestor de fato mexeu.

    Texto gerado por regra é rascunho, não sentença: o gestor ajusta o tom e as
    plataformas no próprio card. Depois de sair, não se reescreve o passado.
    """
    try:
        announcement = Announcement.objects.get(pk=announcement_id)
    except Announcement.DoesNotExist as exc:
        raise CampaignError("Anúncio não encontrado.") from exc

    if announcement.status not in (AnnouncementStatus.DRAFT, AnnouncementStatus.PENDING_REVIEW):
        raise CampaignError("Este announcement não está mais em revisão.")

    content = dict(announcement.content or {})
    if body is not None:
        content["body"] = str(body)
    if hashtags is not None:
        content["hashtags"] = [str(tag).strip() for tag in hashtags if str(tag).strip()]
    if image_url is not None:
        content["image_url"] = str(image_url)

    announcement.content = content
    announcement.platform_content = _platform_content(announcement.template, content) if announcement.template_id else {}
    if platforms is not None:
        announcement.platforms = [str(platform) for platform in platforms]
    announcement.save(update_fields=["content", "platform_content", "platforms"])
    return announcement


def reject(announcement_id: int, by=None, *, reason: str = "") -> Announcement:
    """Recusar um anúncio: o gestor viu e disse não.

    ⚠️ Antes isto marcava `expired`, colapsando duas coisas diferentes. Vencimento é o
    relógio ganhando de todo mundo; recusa é decisão de alguém — e só a segunda diz algo
    sobre o modelo de campanha. Uma campanha cujos anúncios são recusados toda semana
    está configurada errado, e essa pergunta era literalmente impossível de responder.

    O motivo é opcional de propósito: exigir justificativa só ensina o gestor a digitar
    "não" para se livrar do campo.
    """
    try:
        announcement = Announcement.objects.get(pk=announcement_id)
    except Announcement.DoesNotExist as exc:
        raise CampaignError("Anúncio não encontrado.") from exc

    # `publishing` entra junto: as Directives já estão na fila, então "recusar" daria
    # ao gestor a impressão de ter parado algo que sai de qualquer jeito. Aprovado COM
    # hora marcada segue recusável de propósito — esse ainda está na mão dele.
    if announcement.status in (AnnouncementStatus.PUBLISHED, AnnouncementStatus.PUBLISHING):
        raise CampaignError("Este anúncio já saiu. Não dá para recusar o que foi publicado.")

    announcement.status = AnnouncementStatus.REJECTED
    announcement.rejected_by = by if by is not None and getattr(by, "pk", None) else None
    announcement.rejected_at = timezone.now()
    announcement.rejected_reason = (reason or "").strip()[:200]
    announcement.save(
        update_fields=["status", "rejected_by", "rejected_at", "rejected_reason"]
    )
    return announcement


def dispatch(announcement: Announcement) -> int:
    """Enfileirar uma Directive por plataforma. Retorna quantas foram criadas."""
    announcement.status = AnnouncementStatus.PUBLISHING
    announcement.save(update_fields=["status"])

    created = 0
    for platform in announcement.platforms or []:
        if platform in POSTING_PLATFORMS:
            created += _queue_announcement(announcement, platform)
        elif platform == "whatsapp":
            created += _queue_notify(announcement)
        else:
            logger.warning("campaign.unknown_platform announcement=%s platform=%s", announcement.pk, platform)

    if not created:
        logger.info("campaign.nothing_dispatched announcement=%s", announcement.pk)
    return created


def _queue_announcement(announcement: Announcement, platform: str) -> int:
    directive = create_deduped(
        ANNOUNCEMENT_PUBLISH,
        payload={"announcement_id": announcement.pk, "platform": platform},
        dedupe_key=f"announcement:{announcement.pk}:{platform}",
    )
    return 1 if directive else 0


def _queue_notify(announcement: Announcement) -> int:
    """WhatsApp: uma onda por directive. VIP-first vira duas, com atraso.

    A audiência é resolvida de novo no handler, não aqui: entre a criação do
    announcement e a aprovação, favoritos e alertas mudam.

    O plano sai de ``AudienceResult.waves()``: o VIP abre, o geral espera
    ``vip_first_minutes``, e quem tem hora habitual conhecida ganha onda própria
    dentro da janela da regra (F11 + F12). Sem VIP na audiência a divisão por
    privilégio é abandonada lá dentro, para ninguém esperar à toa.

    A resolução aqui serve só para *planejar* as ondas; quem envia resolve de
    novo com ``audience.select_wave(rules, wave_key, sku=sku)``, porque entre a
    aprovação e o disparo favoritos e alertas mudam. Por isso a onda-base sai
    mesmo com audiência vazia agora: quem entrar na fila do "me avise" no
    intervalo ainda é alcançado, e o envio no-op se ela seguir vazia.
    """
    rules = (announcement.rule.audience_rules or {}) if announcement.rule_id else {}
    sku = (announcement.trigger_context or {}).get("sku", "")

    waves = audience_service.resolve(rules, sku=sku).waves()

    created = 0
    for wave in waves:
        directive = create_deduped(
            ANNOUNCEMENT_NOTIFY,
            payload={
                "announcement_id": announcement.pk,
                "wave": wave.key,
                "sku": sku,
                "waves_expected": len(waves),
            },
            dedupe_key=f"announcement:{announcement.pk}:wa:{wave.key}",
            available_at=(
                timezone.now() + timedelta(minutes=wave.delay_minutes)
                if wave.delay_minutes
                else None
            ),
        )
        created += 1 if directive else 0
    return created



# ── Notificação do gestor ────────────────────────────────────────────


def notify_reviewers(rule: Campaign, announcement: Announcement) -> int:
    """Criar ``UserNotification`` acionável para quem pode aprovar.

    Destinatários: ``rule.notify_users`` quando declarado, senão todo mundo
    com ``shop.manage_campaigns``. Retorna quantas notificações criou.
    """
    from shopman.shop.models import NotificationCategory, UserNotification

    users = _reviewers(rule)
    if not users:
        logger.warning("campaign.no_reviewers announcement=%s rule=%s", announcement.pk, rule.pk)
        return 0

    total = announcement.audience.get("total", 0)
    message = announcement.body
    if total:
        message = f"{message}\n\nAudiência: {total} cliente(s)."

    created = 0
    for user in users:
        notification = UserNotification.objects.create(
            user=user,
            category=NotificationCategory.CAMPAIGN,
            title=f"Anúncio pronto para revisão: {rule.name}",
            message=message,
            action_url=f"/campaign/announcements/{announcement.pk}/",
            action_data={"announcement_id": announcement.pk},
            is_actionable=True,
        )
        push_user_notification(notification)
        created += 1
    return created


def _reviewers(rule: Campaign):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    explicit = [int(uid) for uid in (rule.notify_users or []) if str(uid).isdigit()]
    if explicit:
        return list(User.objects.filter(pk__in=explicit, is_active=True))

    from django.db.models import Q

    return list(
        User.objects.filter(
            Q(is_superuser=True)
            | Q(user_permissions__codename="manage_campaigns")
            | Q(groups__permissions__codename="manage_campaigns"),
            is_active=True,
        ).distinct()
    )


def push_user_notification(notification) -> None:
    """Push SSE no canal pessoal ``user-<id>`` (ADR-016: só avisa que chegou)."""
    payload = {"id": notification.pk, "category": notification.category}
    user_id = notification.user_id

    def _send():
        try:
            from django_eventstream import send_event

            send_event(f"user-{user_id}", "user-notification", payload)
        except ImportError:
            return
        except Exception:
            logger.warning("campaign.user_push_failed user=%s", user_id, exc_info=True)

    transaction.on_commit(_send)


# ── Manutenção ───────────────────────────────────────────────────────


def arm_scheduled(*, now=None, horizon_minutes: int = 60) -> int:
    """Armar as ocasiões que vão acontecer no próximo horizonte. Retorna quantas.

    **A vassoura arma; a fila dispara.** Este é o ponto todo da F9: em vez de esperar o
    ciclo de manutenção coincidir com as 17h30 (o que dá até 5 minutos de atraso numa
    relâmpago cuja graça é o minuto), o ciclo cria uma Directive com ``available_at`` no
    instante exato. Quem executa é ``process_directives --watch``, que roda a cada ~2
    segundos.

    Nenhum threshold da ADR-003 muda, e não entra broker: é o mesmo padrão que o atraso
    da onda VIP já usa e que o ``PREORDER_ACTIVATE`` estabeleceu.

    O ``dedupe_key`` é a ocasião. Rodar duas vezes, ou dois workers ao mesmo tempo, não
    arma em dobro — e se a Directive já foi consumida, o unique parcial de
    ``Announcement.occurrence_key`` fecha a segunda porta.
    """
    from shopman.shop.directives import CAMPAIGN_OCCUR, create_deduped
    from shopman.shop.services import campaign_schedule

    now = now or timezone.now()
    horizon = now + timedelta(minutes=max(1, horizon_minutes))

    armed = 0
    campaigns = Campaign.objects.filter(is_active=True, trigger=Trigger.SCHEDULE)
    for rule in campaigns:
        try:
            moment = campaign_schedule.next_occurrence(rule.schedule, now=now)
        except Exception:
            logger.warning("campaign.occurrence_failed rule=%s", rule.pk, exc_info=True)
            continue
        if moment is None or moment > horizon:
            continue

        key = occurrence_key(rule, moment)
        directive = create_deduped(
            CAMPAIGN_OCCUR,
            payload={"campaign_id": rule.pk, "occurrence_key": key, "at": moment.isoformat()},
            dedupe_key=key,
            available_at=moment,
        )
        if directive:
            armed += 1
    return armed


def occurrence_key(rule, moment) -> str:
    """Identidade de UMA ocasião: campanha + instante, ao minuto.

    Ao minuto, e não ao segundo, porque o instante vem de config em ``HH:MM`` — arredondar
    para baixo garante que dois cálculos da mesma janela produzam a mesma chave, que é o
    que faz o dedupe funcionar.
    """
    stamp = timezone.localtime(moment).strftime("%Y%m%dT%H%M")
    return f"campaign:{rule.pk}:{stamp}"


def create_for_occurrence(campaign_id: int, *, key: str, context: dict | None = None):
    """Criar o anúncio de uma ocasião agendada. Devolve ``None`` se já existia.

    ``None`` não é erro: é o dedupe funcionando. Duas tentativas para a mesma ocasião
    acontecem em operação normal (retry da fila, dois workers), e a segunda tem de ser
    silenciosa em vez de mandar a mensagem de novo.
    """
    from django.db import IntegrityError, transaction

    rule = (
        Campaign.objects.filter(pk=campaign_id, is_active=True)
        .select_related("template")
        .first()
    )
    if rule is None:
        logger.info("campaign.occurrence_rule_gone campaign=%s", campaign_id)
        return None

    if Announcement.objects.filter(occurrence_key=key).exists():
        return None

    payload = dict(context or {})
    payload.setdefault("trigger", Trigger.SCHEDULE)
    payload.setdefault("occurrence_key", key)

    try:
        with transaction.atomic():
            return _create_announcement(rule, payload, occurrence_key=key)
    except IntegrityError:
        # O unique parcial ganhou a corrida: outro worker criou a mesma ocasião.
        logger.info("campaign.occurrence_deduped key=%s", key)
        return None


def dispatch_due(*, now=None) -> int:
    """Despachar os announcements agendados cuja hora chegou. Retorna quantos saíram.

    ``publish_at`` volta a NULL no despacho: é a marca de "ainda não saiu", e
    zerá-la impede que um ciclo seguinte despache o mesmo announcement de novo.
    """
    now = now or timezone.now()
    due = Announcement.objects.filter(
        status=AnnouncementStatus.APPROVED, publish_at__isnull=False, publish_at__lte=now
    )

    dispatched = 0
    for announcement in due:
        try:
            announcement.publish_at = None
            announcement.save(update_fields=["publish_at"])
            dispatch(announcement)
            dispatched += 1
        except Exception:
            logger.warning("campaign.scheduled_dispatch_failed announcement=%s", announcement.pk, exc_info=True)
    return dispatched


def expire_stale_announcements(*, now=None) -> int:
    """Caducar announcements pendentes que passaram do prazo. Retorna quantos."""
    now = now or timezone.now()
    return Announcement.objects.filter(
        status=AnnouncementStatus.PENDING_REVIEW,
        expires_at__isnull=False,
        expires_at__lte=now,
    ).update(status=AnnouncementStatus.EXPIRED)
