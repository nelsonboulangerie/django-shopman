"""Isolação por construção dos flows do ManyChat e os três modos do Marketing.

O flow aprovado mora DENTRO do ManyChat e lê variáveis dos campos personalizados do
assinante — estado persistente do contato. A sequência do adapter é "gravar N campos
→ ``sendFlow``", e o flow renderiza depois, assíncrono. Duas mensagens com flow para
a MESMA pessoa em sequência próxima podiam intercalar: a segunda escrita troca nome,
preço e link antes de o primeiro flow ler.

A prova externa ("o fornecedor não mistura") é fraca, porque a corrida depende de
tempo. A decisão (ADR-009, emenda de 17/09) é tornar a mistura impossível do nosso
lado: **uma mensagem com flow por assinante por vez**, reservada no cache
compartilhado durante a janela de assentamento
(``SHOPMAN_MANYCHAT_FLOW_SETTLE_SECONDS``). Quem não consegue reservar não escreve
nada e volta mais tarde — resultado retentável, nunca falha final nem ``unknown``.

A abertura é por etapas, pelo modo ``SHOPMAN_MARKETING_WHATSAPP_MODE``:

- ``blocked`` (padrão): nenhum evento de Marketing sai por WhatsApp;
- ``canary``: só sai para os ``customer_ref`` listados em
  ``SHOPMAN_MARKETING_WHATSAPP_CANARY_CUSTOMER_REFS``;
- ``open``: sai para todo contato elegível.

``canary`` e ``open`` exigem cache compartilhado entre processos. Com cache local
(LocMem/Dummy/arquivo) a reserva de um processo não é vista pelo outro, a
serialização não vale, e o estado continua bloqueado — falha fechado.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from shopman.shop.services.marketing_contracts import MarketingContractError

BLOCK_CODE = "manychat_custom_fields_unverified"
CANARY_CONTACTS_MISSING_CODE = "manychat_canary_contacts_missing"
SERIALIZATION_UNAVAILABLE_CODE = "manychat_flow_serialization_unavailable"
CANARY_RECIPIENT_EXCLUDED_CODE = "whatsapp_canary_recipient_excluded"

#: O assinante já tem uma mensagem com flow assentando: nada foi escrito.
SUBSCRIBER_BUSY_CODE = "subscriber_busy"
#: O cache não respondeu à reserva: nada foi escrito, e não dá para saber se está livre.
FLOW_RESERVATION_UNAVAILABLE_CODE = "flow_reservation_unavailable"
#: Resultados que significam "não saiu nada, tente depois da janela" — nunca falha.
FLOW_DEFERRAL_CODES = frozenset({SUBSCRIBER_BUSY_CODE, FLOW_RESERVATION_UNAVAILABLE_CODE})

MODE_BLOCKED = "blocked"
MODE_CANARY = "canary"
MODE_OPEN = "open"
MODES = frozenset({MODE_BLOCKED, MODE_CANARY, MODE_OPEN})

STATE_BLOCKED = "blocked_unverified"
STATE_CANARY = "canary"
STATE_SAFE = "safe"

DEFAULT_FLOW_SETTLE_SECONDS = 120
#: Chave da reserva no cache compartilhado: ``<prefixo><subscriber_id>``.
FLOW_RESERVATION_KEY_PREFIX = "manychat:flow-busy:"
#: Teto do ``retry_after_seconds`` aceito pelo ledger de entregas.
_MAX_FLOW_SETTLE_SECONDS = 86_400

MARKETING_FLOW_EVENTS = frozenset({
    "announcement_published",
    "production_ready",
    "stock_arrived",
})

#: O conjunto COMPLETO de campos personalizados que cada evento de Marketing grava.
#:
#: ⚠️ Campo personalizado é estado PERSISTENTE do contato. Gravar só o que o contexto
#: traz deixava no perfil o valor da mensagem ANTERIOR: a campanha da Baguete com
#: ``{{price}}`` seguida de um aviso sem preço fazia o flow do aviso mostrar o preço da
#: Baguete — a mesma mistura que a reserva por assinante existe para impedir, só que em
#: sequência em vez de em corrida. Para estes eventos o adapter grava TODOS os campos
#: declarados, com string vazia para o que o contexto não tiver, dentro da reserva.
#:
#: As listas saem do que os emissores montam e do que os textos semeados e a prévia
#: usam: ``campaign.available_variables`` + envelope do anúncio (``body``/``cta``/
#: ``action_url``) para ``announcement_published``; o contexto de
#: ``storefront.services.stock_alerts._deliver`` para os dois avisos. Chave fora da
#: lista não vai para o ManyChat nestes eventos. ``customer_name_greeting`` e
#: ``product_label`` são derivadas por ``derive_context`` para todo envio.
_ALERT_FLOW_FIELDS = (
    "action_url",
    "availability_phrase",
    "available_qty",
    "cta",
    "customer_name",
    "customer_name_greeting",
    "deadline_note",
    "management_note",
    "product_image_url",
    "product_label",
    "product_name",
    "product_sku",
    "product_url",
    "reserve_note",
)
MARKETING_FLOW_FIELDS: dict[str, tuple[str, ...]] = {
    "announcement_published": (
        "action_url",
        "availability_phrase",
        "available_qty",
        "body",
        "cta",
        "customer_name",
        "customer_name_greeting",
        "hashtags",
        "link",
        "price",
        "product_image_url",
        "product_label",
        "product_name",
        "product_sku",
        "quality",
        "store_name",
        "time",
    ),
    "production_ready": _ALERT_FLOW_FIELDS,
    "stock_arrived": _ALERT_FLOW_FIELDS,
}

#: Backends de cache que TODOS os processos (web, workers) enxergam igual. Lista de
#: permissão, não de proibição: backend desconhecido não prova compartilhamento.
_SHARED_CACHE_BACKENDS = frozenset({
    "django.core.cache.backends.redis.RedisCache",
    "django_redis.cache.RedisCache",
    "django.core.cache.backends.db.DatabaseCache",
    "django.core.cache.backends.memcached.PyMemcacheCache",
    "django.core.cache.backends.memcached.PyLibMCCache",
})

_SANDBOX_MARKER_KEY = "__shopman_marketing_sandbox_probe__"
_SANDBOX_MARKER = object()


@dataclass(frozen=True, slots=True)
class ManyChatMarketingSafety:
    safe: bool
    state: str
    reason_code: str
    reason: str
    action: str
    mode: str = MODE_BLOCKED
    #: Quantos contatos recebem no ensaio. Zero fora do modo ``canary``.
    canary_size: int = 0

    @property
    def allows_delivery(self) -> bool:
        """Algum contato pode receber agora: aberto de vez ou em ensaio."""

        return self.safe or self.state == STATE_CANARY


def whatsapp_mode() -> str:
    """O modo configurado; valor desconhecido conta como ``blocked``."""

    raw = str(getattr(settings, "SHOPMAN_MARKETING_WHATSAPP_MODE", MODE_BLOCKED) or "")
    mode = raw.strip().lower()
    return mode if mode in MODES else MODE_BLOCKED


def canary_customer_refs() -> frozenset[str]:
    """Os refs do ensaio. Aceita tupla/lista (settings) ou texto separado por vírgula."""

    raw = getattr(settings, "SHOPMAN_MARKETING_WHATSAPP_CANARY_CUSTOMER_REFS", ()) or ()
    values = raw.split(",") if isinstance(raw, str) else raw
    return frozenset(str(value).strip() for value in values if str(value or "").strip())


def flow_settle_seconds() -> int:
    """A janela de assentamento de uma mensagem com flow; inválido volta ao padrão."""

    try:
        value = int(getattr(settings, "SHOPMAN_MANYCHAT_FLOW_SETTLE_SECONDS", DEFAULT_FLOW_SETTLE_SECONDS))
    except (TypeError, ValueError):
        # Valor não numérico na env não pode desligar a janela: o padrão é a
        # escolha segura, e o check de deploy não precisa derrubar nada por isso.
        return DEFAULT_FLOW_SETTLE_SECONDS
    if value <= 0:
        return DEFAULT_FLOW_SETTLE_SECONDS
    return min(value, _MAX_FLOW_SETTLE_SECONDS)


def serialization_available() -> bool:
    """A reserva por assinante vale entre processos só com cache compartilhado."""

    caches = getattr(settings, "CACHES", {}) or {}
    backend = str((caches.get("default") or {}).get("BACKEND") or "")
    return backend in _SHARED_CACHE_BACKENDS


def safety_state() -> ManyChatMarketingSafety:
    """O estado do Marketing por WhatsApp, lido do modo e da serialização."""

    mode = whatsapp_mode()
    if mode == MODE_BLOCKED:
        return ManyChatMarketingSafety(
            safe=False,
            state=STATE_BLOCKED,
            reason_code=BLOCK_CODE,
            reason=(
                "O envio de Marketing por WhatsApp está fechado neste ambiente: o flow "
                "lê campos persistentes do contato."
            ),
            action=(
                "Pedir à Platform Owner para abrir o ensaio com contatos escolhidos; "
                "até lá, nenhuma mensagem de Marketing sai por WhatsApp"
            ),
            mode=mode,
        )
    if not serialization_available():
        return ManyChatMarketingSafety(
            safe=False,
            state=STATE_BLOCKED,
            reason_code=SERIALIZATION_UNAVAILABLE_CODE,
            reason=(
                "Sem cache compartilhado, duas mensagens para a mesma pessoa podem "
                "trocar nome, preço e link."
            ),
            action="Ligar o cache compartilhado (Redis) antes de abrir o WhatsApp",
            mode=mode,
        )
    if mode == MODE_CANARY:
        refs = canary_customer_refs()
        if not refs:
            return ManyChatMarketingSafety(
                safe=False,
                state=STATE_BLOCKED,
                reason_code=CANARY_CONTACTS_MISSING_CODE,
                reason="O ensaio do WhatsApp está ligado sem nenhum contato escolhido.",
                action="Informar os contatos do ensaio ou voltar o modo para bloqueado",
                mode=mode,
            )
        return ManyChatMarketingSafety(
            safe=False,
            state=STATE_CANARY,
            reason_code="",
            reason="",
            action="",
            mode=mode,
            canary_size=len(refs),
        )
    return ManyChatMarketingSafety(
        safe=True,
        state=STATE_SAFE,
        reason_code="",
        reason="",
        action="",
        mode=mode,
    )


def recipient_refusal(customer_ref: str | None, *, state: ManyChatMarketingSafety | None = None) -> str:
    """O código que impede ESTE contato de receber Marketing agora, ou ``""``.

    Assinatura anônima (sem ``customer_ref``) nunca entra no ensaio.
    """

    current = state or safety_state()
    if not current.allows_delivery:
        return current.reason_code or BLOCK_CODE
    if current.state == STATE_CANARY:
        ref = str(customer_ref or "").strip()
        if not ref or ref not in canary_customer_refs():
            return CANARY_RECIPIENT_EXCLUDED_CODE
    return ""


def canary_excludes(customer_ref: str | None) -> bool:
    """Em ensaio, este contato fica de fora? Fora do ensaio a resposta é sempre não.

    É a barreira da resolução/claim: em ``blocked`` o comportamento de hoje continua
    (o adapter recusa); em ``canary`` quem está fora da lista é suprimido antes de
    virar tentativa, para a tela não prometer o que o envio recusa.
    """

    state = safety_state()
    return (
        state.state == STATE_CANARY
        and recipient_refusal(customer_ref, state=state) == CANARY_RECIPIENT_EXCLUDED_CODE
    )


def is_flow_deferral(code: object) -> bool:
    """O resultado diz "nada foi escrito, tente depois da janela"?"""

    return isinstance(code, str) and code in FLOW_DEFERRAL_CODES


def require_safe_delivery() -> None:
    # A local rehearsal never calls ManyChat and therefore cannot exhibit the
    # persistent-custom-field race guarded below.  This exception is derived
    # from the adapter boundary, not from a production-facing toggle alone.
    from shopman.shop.services.marketing_delivery_runtime import (
        is_hermetic_simulation,
    )

    if is_hermetic_simulation("whatsapp"):
        return
    state = safety_state()
    if not state.allows_delivery:
        raise MarketingContractError(
            code=state.reason_code,
            detail=f"{state.reason} {state.action}.",
            field_errors={"platforms.whatsapp": (state.action,)},
        )


def sandbox_probe_context(context: dict) -> dict:
    """Mark one server-authorized max-1 sandbox probe; marker never leaves process."""

    return dict(context) | {_SANDBOX_MARKER_KEY: _SANDBOX_MARKER}


def consume_sandbox_probe(context: dict) -> bool:
    """Remove and recognize the non-serializable in-process sandbox sentinel."""

    return context.pop(_SANDBOX_MARKER_KEY, None) is _SANDBOX_MARKER
