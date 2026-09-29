"""Provider capability inventory for Marketing composition.

This module describes what each provider can represent independently from what
Shopman can dispatch today.  The executable allow-list intentionally remains in
``marketing_capabilities``: adding an item here must never authorize a new
external effect by accident.

The catalog is static, versioned product knowledge.  Account permissions,
quotas, eligibility and connection health are runtime facts and belong to a
future connection capability snapshot.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

PROVIDER_CAPABILITY_SCHEMA_VERSION = 2

ConnectorState = Literal["active", "dormant"]
ImplementationState = Literal["ready", "partial", "planned", "gated"]
ProviderDeliveryKind = Literal["publication", "direct_message", "creator_handoff"]
FieldKind = Literal["text", "url", "boolean", "choice", "datetime", "template_variable"]
CtaModel = Literal["none", "link", "provider_choice", "template_defined"]


@dataclass(frozen=True, slots=True)
class ProviderFieldCapability:
    ref: str
    label: str
    kind: FieldKind
    required: bool = False
    max_length: int | None = None
    choices: tuple[str, ...] = ()
    availability_note: str = ""


@dataclass(frozen=True, slots=True)
class ProviderMediaCapability:
    min_items: int = 0
    max_items: int | None = 0
    kinds: tuple[str, ...] = ()
    image_formats: tuple[str, ...] = ()
    video_formats: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderFormatCapability:
    ref: str
    label: str
    delivery_kind: ProviderDeliveryKind
    implementation_state: ImplementationState
    implemented_variants: tuple[str, ...]
    fields: tuple[ProviderFieldCapability, ...]
    media: ProviderMediaCapability
    cta_model: CtaModel = "none"
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    platform: str
    label: str
    connector_state: ConnectorState
    formats: tuple[ProviderFormatCapability, ...]
    notes: tuple[str, ...] = ()

    def format(self, ref: str) -> ProviderFormatCapability | None:
        normalized = str(ref or "").strip().lower()
        return next((item for item in self.formats if item.ref == normalized), None)


def _field(
    ref: str,
    label: str,
    kind: FieldKind,
    *,
    required: bool = False,
    max_length: int | None = None,
    choices: tuple[str, ...] = (),
    availability_note: str = "",
) -> ProviderFieldCapability:
    return ProviderFieldCapability(
        ref=ref,
        label=label,
        kind=kind,
        required=required,
        max_length=max_length,
        choices=choices,
        availability_note=availability_note,
    )


_INSTAGRAM_COMMON_FIELDS = (
    _field("caption", "Legenda", "text", max_length=2200),
    _field("location_id", "Localização", "text"),
    _field("user_tags", "Pessoas marcadas", "text"),
    _field("collaborators", "Colaboradores", "text"),
    _field("is_ai_generated", "Conteúdo gerado por IA", "boolean"),
    _field(
        "paid_partnership",
        "Parceria paga",
        "boolean",
        availability_note="Disponível apenas para contas e formatos elegíveis.",
    ),
)

_PROVIDER_CAPABILITIES = (
    ProviderCapability(
        platform="instagram",
        label="Instagram",
        connector_state="active",
        formats=(
            ProviderFormatCapability(
                ref="feed",
                label="Feed",
                delivery_kind="publication",
                implementation_state="partial",
                implemented_variants=("image",),
                fields=_INSTAGRAM_COMMON_FIELDS
                + (_field("alt_text", "Texto alternativo", "text"),),
                media=ProviderMediaCapability(
                    min_items=1,
                    max_items=1,
                    kinds=("image", "video"),
                    image_formats=("jpeg",),
                    video_formats=("mp4", "mov"),
                    notes=("Shopman publica somente a variante de imagem hoje.",),
                ),
                notes=("O fluxo orgânico não oferece botão CTA genérico.",),
            ),
            ProviderFormatCapability(
                ref="story",
                label="Story",
                delivery_kind="publication",
                implementation_state="partial",
                implemented_variants=("image",),
                fields=(
                    _field("is_ai_generated", "Conteúdo gerado por IA", "boolean"),
                ),
                media=ProviderMediaCapability(
                    min_items=1,
                    max_items=1,
                    kinds=("image", "video"),
                    image_formats=("jpeg",),
                    video_formats=("mp4", "mov"),
                    notes=("Shopman publica somente a variante de imagem hoje.",),
                ),
                notes=(
                    "A elegibilidade de Story deve ser confirmada para a conta conectada.",
                    "O fluxo orgânico não oferece botão CTA genérico.",
                ),
            ),
            ProviderFormatCapability(
                ref="reel",
                label="Reel",
                delivery_kind="publication",
                implementation_state="planned",
                implemented_variants=(),
                fields=_INSTAGRAM_COMMON_FIELDS
                + (
                    _field("share_to_feed", "Compartilhar também no Feed", "boolean"),
                    _field("cover_url", "Capa", "url"),
                    _field("thumb_offset", "Posição da capa", "text"),
                    _field("trial_reel", "Reel de teste", "boolean"),
                ),
                media=ProviderMediaCapability(
                    min_items=1,
                    max_items=1,
                    kinds=("video",),
                    video_formats=("mp4", "mov"),
                    notes=("A duração e o codec precisam ser validados antes de criar o container.",),
                ),
                notes=("O fluxo orgânico não oferece botão CTA genérico.",),
            ),
            ProviderFormatCapability(
                ref="carousel",
                label="Carrossel",
                delivery_kind="publication",
                implementation_state="planned",
                implemented_variants=(),
                fields=_INSTAGRAM_COMMON_FIELDS,
                media=ProviderMediaCapability(
                    min_items=2,
                    max_items=10,
                    kinds=("image", "video"),
                    image_formats=("jpeg",),
                    video_formats=("mp4", "mov"),
                    notes=("Imagens e vídeos podem ser combinados no mesmo carrossel.",),
                ),
                notes=("Um carrossel conta como uma publicação para o limite de publicação.",),
            ),
        ),
        notes=(
            "Consultar content_publishing_limit; não fixar no frontend a quota de 24 horas.",
            "Containers de publicação expiram e exigem lifecycle explícito.",
        ),
    ),
    ProviderCapability(
        platform="facebook",
        label="Facebook",
        connector_state="active",
        formats=(
            ProviderFormatCapability(
                ref="feed",
                label="Feed da Página",
                delivery_kind="publication",
                implementation_state="partial",
                implemented_variants=("text", "link", "image"),
                fields=(
                    _field("message", "Mensagem", "text"),
                    _field("link", "Link", "url"),
                    _field("scheduled_publish_time", "Publicar em", "datetime"),
                    _field("targeting", "Segmentação geográfica", "text"),
                ),
                media=ProviderMediaCapability(
                    min_items=0,
                    max_items=None,
                    kinds=("image", "video"),
                    image_formats=("jpeg", "png"),
                    video_formats=("mp4", "mov"),
                    notes=("O limite de mídia depende do endpoint e deve vir do schema da variante.",),
                ),
                cta_model="link",
                notes=("Link não equivale a um botão CTA arbitrário.",),
            ),
            ProviderFormatCapability(
                ref="reel",
                label="Reel",
                delivery_kind="publication",
                implementation_state="planned",
                implemented_variants=(),
                fields=(
                    _field("title", "Título", "text"),
                    _field("description", "Descrição", "text"),
                    _field("collaborator_id", "Colaborador", "text"),
                    _field(
                        "video_state",
                        "Estado",
                        "choice",
                        choices=("DRAFT", "SCHEDULED", "PUBLISHED"),
                    ),
                    _field("scheduled_publish_time", "Publicar em", "datetime"),
                ),
                media=ProviderMediaCapability(
                    min_items=1,
                    max_items=1,
                    kinds=("video",),
                    video_formats=("mp4", "mov"),
                    notes=("A resolução mínima documentada é 540p.",),
                ),
                notes=(
                    "Reels de Página desse fluxo são públicos.",
                    "O limite documentado é 30 Reels em 24 horas.",
                ),
            ),
        ),
        notes=("Descobrir todas as Pages autorizadas; não assumir uma única Page.",),
    ),
    ProviderCapability(
        platform="google_business",
        label="Google Business Profile",
        connector_state="active",
        formats=(
            ProviderFormatCapability(
                ref="standard",
                label="Atualização",
                delivery_kind="publication",
                implementation_state="ready",
                implemented_variants=("standard",),
                fields=(
                    _field("summary", "Resumo", "text", max_length=1500),
                    _field(
                        "call_to_action",
                        "Botão",
                        "choice",
                        choices=("BOOK", "ORDER", "SHOP", "LEARN_MORE", "SIGN_UP", "CALL", "NONE"),
                    ),
                    _field("action_url", "URL do botão", "url"),
                    _field("scheduled_time", "Publicar em", "datetime"),
                ),
                media=ProviderMediaCapability(
                    min_items=0,
                    max_items=1,
                    kinds=("image",),
                    image_formats=("jpeg", "png"),
                ),
                cta_model="provider_choice",
            ),
            ProviderFormatCapability(
                ref="event",
                label="Evento",
                delivery_kind="publication",
                implementation_state="ready",
                implemented_variants=("event",),
                fields=(
                    _field("summary", "Resumo", "text", max_length=1500),
                    _field("event_title", "Título do evento", "text", required=True),
                    _field("event_start", "Início", "datetime", required=True),
                    _field("event_end", "Fim", "datetime", required=True),
                    _field(
                        "call_to_action",
                        "Botão",
                        "choice",
                        choices=("BOOK", "ORDER", "SHOP", "LEARN_MORE", "SIGN_UP", "CALL", "NONE"),
                    ),
                    _field("action_url", "URL do botão", "url"),
                ),
                media=ProviderMediaCapability(
                    min_items=0,
                    max_items=1,
                    kinds=("image",),
                    image_formats=("jpeg", "png"),
                ),
                cta_model="provider_choice",
            ),
            ProviderFormatCapability(
                ref="offer",
                label="Oferta",
                delivery_kind="publication",
                implementation_state="partial",
                implemented_variants=("offer_without_coupon",),
                fields=(
                    _field("summary", "Resumo", "text", max_length=1500),
                    _field("offer_title", "Título da oferta", "text", required=True),
                    _field("offer_start", "Início", "datetime", required=True),
                    _field("offer_end", "Fim", "datetime", required=True),
                    _field("coupon_code", "Código do cupom", "text"),
                    _field("redeem_online_url", "URL de resgate", "url"),
                    _field("terms_conditions", "Termos e condições", "text"),
                ),
                media=ProviderMediaCapability(
                    min_items=0,
                    max_items=1,
                    kinds=("image",),
                    image_formats=("jpeg", "png"),
                ),
                cta_model="link",
                notes=("O Google ignora callToAction em Offer.",),
            ),
            ProviderFormatCapability(
                ref="alert",
                label="Alerta",
                delivery_kind="publication",
                implementation_state="gated",
                implemented_variants=(),
                fields=(_field("summary", "Resumo", "text", max_length=1500),),
                media=ProviderMediaCapability(
                    min_items=0,
                    max_items=1,
                    kinds=("image",),
                    image_formats=("jpeg", "png"),
                ),
                notes=("Expor somente quando a política e a categoria da location permitirem.",),
            ),
        ),
        notes=(
            "Product posts não podem ser criados por esta API.",
            "Descobrir locations pela Business Information v1 com paginação de até 100 por página.",
        ),
    ),
    ProviderCapability(
        platform="whatsapp",
        label="WhatsApp via ManyChat",
        connector_state="active",
        formats=(
            ProviderFormatCapability(
                ref="template",
                label="Template aprovado",
                delivery_kind="direct_message",
                implementation_state="partial",
                implemented_variants=("manychat_flow",),
                fields=(
                    _field("template_ref", "Template", "choice", required=True),
                    _field("body_variables", "Variáveis do corpo", "template_variable"),
                    _field("header_variables", "Variáveis do cabeçalho", "template_variable"),
                ),
                media=ProviderMediaCapability(
                    min_items=0,
                    max_items=1,
                    kinds=("image", "video", "document"),
                    notes=("O tipo do cabeçalho é fixado pelo template aprovado.",),
                ),
                cta_model="template_defined",
                notes=(
                    "O template pode ter um botão URL ou até três botões de resposta, sem misturar os grupos.",
                    "Opt-in e template aprovado são gates de envio.",
                ),
            ),
            ProviderFormatCapability(
                ref="session_message",
                label="Mensagem na janela de atendimento",
                delivery_kind="direct_message",
                implementation_state="gated",
                implemented_variants=(),
                fields=(_field("body", "Mensagem", "text", required=True),),
                media=ProviderMediaCapability(
                    min_items=0,
                    max_items=None,
                    kinds=("image", "video", "document"),
                ),
                notes=("Só é elegível dentro da janela de atendimento de 24 horas por contato.",),
            ),
        ),
        notes=("Sincronizar contas e templates/flows; não assumir um flow_ns global.",),
    ),
    ProviderCapability(
        platform="tiktok",
        label="TikTok",
        connector_state="dormant",
        formats=(
            ProviderFormatCapability(
                ref="photo_draft",
                label="Rascunho de fotos",
                delivery_kind="creator_handoff",
                implementation_state="planned",
                implemented_variants=(),
                fields=(
                    _field("title", "Título inicial", "text", max_length=90),
                    _field("description", "Descrição inicial", "text", max_length=4000),
                ),
                media=ProviderMediaCapability(
                    min_items=1,
                    max_items=35,
                    kinds=("image",),
                    image_formats=("jpeg", "webp"),
                    notes=("O operador conclui a edição e a publicação dentro do TikTok.",),
                ),
                notes=(
                    "Usa post_mode MEDIA_UPLOAD e o escopo video.upload.",
                    "O TikTok envia uma notificação ao creator para concluir o rascunho.",
                ),
            ),
            ProviderFormatCapability(
                ref="video_draft",
                label="Rascunho de vídeo",
                delivery_kind="creator_handoff",
                implementation_state="planned",
                implemented_variants=(),
                fields=(),
                media=ProviderMediaCapability(
                    min_items=1,
                    max_items=1,
                    kinds=("video",),
                    video_formats=("mp4", "mov", "webm"),
                    notes=("O operador conclui legenda, música, privacidade e publicação no TikTok.",),
                ),
                notes=(
                    "Usa /v2/post/publish/inbox/video/init/ e o escopo video.upload.",
                    "É o caminho compatível com um produto operacional de uso privado.",
                ),
            ),
            ProviderFormatCapability(
                ref="photo",
                label="Publicação direta de fotos",
                delivery_kind="publication",
                implementation_state="gated",
                implemented_variants=(),
                fields=(
                    _field("title", "Título", "text", max_length=90),
                    _field("description", "Descrição", "text", max_length=4000),
                    _field("privacy_level", "Privacidade", "choice", required=True),
                    _field("disable_comment", "Desativar comentários", "boolean"),
                    _field("auto_add_music", "Adicionar música", "boolean"),
                    _field("brand_content_toggle", "Parceria paga", "boolean", required=True),
                    _field("brand_organic_toggle", "Marca própria", "boolean", required=True),
                    _field("is_aigc", "Conteúdo gerado por IA", "boolean"),
                ),
                media=ProviderMediaCapability(
                    min_items=1,
                    max_items=35,
                    kinds=("image",),
                    image_formats=("jpeg", "webp"),
                    notes=("Cada imagem tem limite documentado de 20 MB e 1080p.",),
                ),
                notes=("Privacidade deve vir de creator_info/query, nunca de choices fixas do frontend.",),
            ),
            ProviderFormatCapability(
                ref="video",
                label="Publicação direta de vídeo",
                delivery_kind="publication",
                implementation_state="gated",
                implemented_variants=(),
                fields=(
                    _field("title", "Legenda", "text", max_length=2200),
                    _field("privacy_level", "Privacidade", "choice", required=True),
                    _field("disable_comment", "Desativar comentários", "boolean"),
                    _field("disable_duet", "Desativar Duet", "boolean"),
                    _field("disable_stitch", "Desativar Stitch", "boolean"),
                    _field("brand_content_toggle", "Parceria paga", "boolean", required=True),
                    _field("brand_organic_toggle", "Marca própria", "boolean", required=True),
                    _field("is_aigc", "Conteúdo gerado por IA", "boolean"),
                ),
                media=ProviderMediaCapability(
                    min_items=1,
                    max_items=1,
                    kinds=("video",),
                    video_formats=("mp4", "mov", "webm"),
                ),
                notes=(
                    "Privacidade deve vir de creator_info/query, nunca de choices fixas do frontend.",
                    "Clientes não auditados não podem publicar conteúdo público.",
                    "A auditoria não aceita utilitário privado limitado às contas da própria equipe.",
                ),
            ),
        ),
        notes=(
            "Connector dormente: oferecer primeiro o handoff de rascunho, não Direct Post.",
            "Direct Post público exige auditoria e produto destinado a uma audiência ampla.",
            "O endpoint de direct post limita cada token de usuário a seis requisições por minuto.",
        ),
    ),
)

PROVIDER_CAPABILITIES: tuple[ProviderCapability, ...] = _PROVIDER_CAPABILITIES
PROVIDER_CAPABILITIES_BY_PLATFORM: Mapping[str, ProviderCapability] = MappingProxyType(
    {item.platform: item for item in PROVIDER_CAPABILITIES}
)


def provider_platform_refs(*, include_dormant: bool = True) -> tuple[str, ...]:
    return tuple(
        item.platform
        for item in PROVIDER_CAPABILITIES
        if include_dormant or item.connector_state == "active"
    )


def provider_capability(platform: str) -> ProviderCapability | None:
    return PROVIDER_CAPABILITIES_BY_PLATFORM.get(str(platform or "").strip().lower())
