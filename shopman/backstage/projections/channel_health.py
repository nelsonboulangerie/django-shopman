"""O checklist vivo de cada canal na aba Canais do Gestor.

A pergunta que cada card responde: *o que falta para este canal funcionar, e
onde se resolve?* Não é tutorial que se faz uma vez — é lido de novo a cada
abertura, a partir do que a casa já registra:

- **iFood**: credenciais (``SHOPMAN_IFOOD``), a conferência do módulo Merchant
  (``IFoodStoreStatus``: horário gravado, polling, erro de leitura), os vínculos
  do cardápio importado (``CatalogSnapshot`` × ``CatalogBinding``) e o resultado
  do envio de produtos (``CatalogSyncState``).
- **TV (menuboard)**: ligada, coleções escolhidas e com produto, e as TVs
  autorizadas (``TrustedDevice`` com ``subject_type="display"``) — a TV busca o
  quadro a cada 30 s, e cada busca carimba ``last_used_at``.
- **Feed Google/Meta**: ligado (pausado, a plataforma recebe 404) e com coleções
  que têm produto.
- **Loja online**: a prontidão de Pix, cartão e código de login
  (``integration_readiness``) — sem eles o cliente não entra ou não paga.

Cada item traz a AÇÃO que o resolve, com destino declarado (``gestor`` = rota do
app, ``admin`` = Admin, ``pair`` = mostrar o endereço e o QR para abrir na TV,
``collections`` = abrir a escolha de coleções do próprio card). Item que exigiria
dado que a casa não guarda fica de fora, em vez de adivinhado.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

#: A conferência com o iFood roda no maintenance-worker a cada ~5 min; duas voltas
#: sem ela é o worker parado, não atraso.
IFOOD_CHECK_STALE_AFTER = timedelta(minutes=10)
#: A TV busca o quadro a cada 30 s. Cinco minutos sem busca é TV desligada, sem
#: rede ou com a página fechada.
DISPLAY_SEEN_STALE_AFTER = timedelta(minutes=5)
#: Uma TV só conta como "em uso" se buscou o quadro no último dia — autorização
#: antiga de uma TV trocada não deve acender aviso de vencimento.
DISPLAY_IN_USE_WINDOW = timedelta(days=1)
#: A autorização da TV vence (``DEVICE_TRUST_TTL_DAYS``) e ela passa a receber
#: 403. Avisar com uma semana de folga.
DISPLAY_EXPIRY_WARNING = timedelta(days=7)

OK = "ok"
TODO = "todo"

_DISPLAY_SUBJECT = "display"


@dataclass(frozen=True)
class ChannelHealthItem:
    key: str
    state: str  # ok | todo
    label: str
    hint: str = ""
    action_label: str = ""
    # gestor | admin | pair | collections — quem resolve o caminho.
    action_target: str = ""
    action_path: str = ""


@dataclass(frozen=True)
class ChannelHealthLink:
    label: str
    target: str  # django | external
    path: str


@dataclass(frozen=True)
class ChannelHealthProjection:
    ref: str
    ready: bool
    summary: str
    items: tuple[ChannelHealthItem, ...]
    preview: tuple[ChannelHealthLink, ...] = ()


@dataclass(frozen=True)
class ChannelHealthBoardProjection:
    channels: tuple[ChannelHealthProjection, ...]


def _hhmm(value: datetime, now: datetime) -> str:
    local = timezone.localtime(value)
    if local.date() == timezone.localtime(now).date():
        return local.strftime("%H:%M")
    return local.strftime("%d/%m às %H:%M")


def _plural(count: int, one: str, many: str) -> str:
    return one if count == 1 else many


def _health(ref: str, items: list[ChannelHealthItem], preview=()) -> ChannelHealthProjection:
    todo = sum(1 for item in items if item.state == TODO)
    summary = "Tudo certo" if not todo else f"{todo} {_plural(todo, 'pendência', 'pendências')}"
    return ChannelHealthProjection(ref=ref, ready=not todo, summary=summary, items=tuple(items), preview=tuple(preview))


# ── iFood ─────────────────────────────────────────────────────────────────────


def _ifood_items(channel, *, now: datetime) -> list[ChannelHealthItem]:
    from shopman.shop.models import CatalogBinding, CatalogSnapshot, IFoodStoreStatus
    from shopman.shop.models.catalog_sync import CatalogSyncState
    from shopman.shop.services import business_calendar, ifood_merchant

    cfg = getattr(settings, "SHOPMAN_IFOOD", {}) or {}
    items: list[ChannelHealthItem] = []

    has_credentials = bool(str(cfg.get("client_id") or "").strip() and str(cfg.get("client_secret") or "").strip())
    items.append(ChannelHealthItem(
        key="credentials",
        state=OK if has_credentials else TODO,
        label="Credenciais do iFood configuradas" if has_credentials else "Faltam as credenciais do iFood",
        hint="" if has_credentials else "IFOOD_CLIENT_ID e IFOOD_CLIENT_SECRET, no deploy.",
    ))
    merchant = ifood_merchant.merchant_id()
    items.append(ChannelHealthItem(
        key="merchant",
        state=OK if merchant else TODO,
        label="Loja do iFood vinculada" if merchant else "Falta dizer qual é a loja no iFood",
        hint="" if merchant else "IFOOD_MERCHANT_ID, no deploy.",
    ))

    # Horário: só é "gravado" quando o módulo Merchant está ligado E a casa
    # declarou grade semanal — sem grade não há o que gravar (ver `governs`).
    status = IFoodStoreStatus.objects.filter(merchant_id=merchant).first() if merchant else None
    merchant_on = ifood_merchant.enabled()
    if not merchant_on:
        items.append(ChannelHealthItem(
            key="hours", state=TODO,
            label="O horário do iFood ainda é o do Portal do Parceiro",
            hint="Ligue IFOOD_MERCHANT_SYNC no deploy para a casa gravar horário, feriados e pausas no iFood.",
        ))
    elif not business_calendar.has_regular_hours():
        items.append(ChannelHealthItem(
            key="hours", state=TODO,
            label="A loja não tem horário semanal declarado",
            hint="Sem ele, não há horário para gravar no iFood.",
            action_label="Declarar horário", action_target="admin", action_path="/admin/shop/shop/",
        ))
    elif status is None or status.synced_at is None:
        items.append(ChannelHealthItem(
            key="hours", state=TODO,
            label="O horário da loja ainda não foi gravado no iFood",
            hint="A gravação sai na próxima conferência do iFood.",
        ))
    else:
        items.append(ChannelHealthItem(
            key="hours", state=OK, label=f"Horário da loja gravado no iFood ({_hhmm(status.synced_at, now)})",
        ))

    # Conferência e polling: só se sabe com o módulo Merchant ligado — é ele que lê
    # o `GET /status`, e é o `is-connected` do iFood que diz se o polling chega.
    if merchant_on and business_calendar.has_regular_hours():
        if status is not None and status.last_error:
            items.append(ChannelHealthItem(
                key="polling", state=TODO,
                label="A última conferência com o iFood falhou",
                hint=status.last_error[:200],
            ))
        elif status is None or status.checked_at is None:
            items.append(ChannelHealthItem(
                key="polling", state=TODO,
                label="O iFood ainda não foi conferido",
                hint="A conferência roda no maintenance-worker, a cada ~5 min.",
            ))
        elif now - status.checked_at > IFOOD_CHECK_STALE_AFTER:
            items.append(ChannelHealthItem(
                key="polling", state=TODO,
                label=f"A conferência com o iFood parou ({_hhmm(status.checked_at, now)})",
                hint="Confira se o maintenance-worker está no ar.",
            ))
        elif any(isinstance(p, dict) and p.get("code") == "is-connected" for p in status.problems or []):
            items.append(ChannelHealthItem(
                key="polling", state=TODO,
                label="O iFood não está recebendo o polling da casa",
                hint="Sem ele o iFood fecha a loja. Confira se o ifood-poll-worker está no ar.",
            ))
        else:
            items.append(ChannelHealthItem(
                key="polling", state=OK,
                label=f"O iFood recebe o polling da casa (conferido às {_hhmm(status.checked_at, now)})",
            ))

    # Vínculos: o cardápio importado do iFood × os produtos da casa.
    catalog_path = f"/channels/{channel.ref}/catalog"
    snapshot = CatalogSnapshot.objects.filter(channel=channel).defer("raw_json").first()
    if snapshot is None:
        items.append(ChannelHealthItem(
            key="bindings", state=TODO,
            label="O cardápio do iFood ainda não foi importado",
            hint="Importe para ligar cada item do iFood a um produto da casa.",
            action_label="Importar", action_target="gestor", action_path=catalog_path,
        ))
    else:
        bound = CatalogBinding.objects.filter(
            channel=channel, provider=snapshot.provider, account_ref=snapshot.account_ref,
            catalog_ref=snapshot.catalog_ref, context=snapshot.context,
        ).count()
        unbound = max(snapshot.item_count - bound, 0)
        if unbound:
            items.append(ChannelHealthItem(
                key="bindings", state=TODO,
                label=f"{unbound} {_plural(unbound, 'item do iFood sem produto vinculado', 'itens do iFood sem produto vinculado')}",
                action_label="Vincular", action_target="gestor", action_path=catalog_path,
            ))
        else:
            items.append(ChannelHealthItem(key="bindings", state=OK, label="Todos os itens do iFood vinculados"))

    # Recusas: o envio de produtos que o iFood devolveu com erro.
    sync = CatalogSyncState.objects.filter(channel_ref=channel.ref).aggregate(
        observed=Count("pk"), errors=Count("pk", filter=Q(status="error")),
    )
    if sync["errors"]:
        errors = sync["errors"]
        items.append(ChannelHealthItem(
            key="refused", state=TODO,
            label=f"{errors} {_plural(errors, 'produto recusado', 'produtos recusados')} pelo iFood",
            action_label="Ver e corrigir", action_target="gestor",
            action_path=f"/catalog?surface={channel.ref}&sync=error",
        ))
    elif sync["observed"]:
        items.append(ChannelHealthItem(key="refused", state=OK, label="Nenhum produto recusado pelo iFood"))
    return items


# ── Menuboard e feeds ─────────────────────────────────────────────────────────


def _collection_items(display: dict) -> list[ChannelHealthItem]:
    from shopman.offerman.models import Collection

    refs = [str(ref) for ref in (display.get("collections") or [])]
    if not refs:
        return [ChannelHealthItem(
            key="collections", state=TODO, label="Nenhuma coleção escolhida: nada a exibir",
            action_label="Escolher coleções", action_target="collections",
        )]
    existing = {c.ref: c for c in Collection.objects.filter(ref__in=refs, is_active=True)}
    items: list[ChannelHealthItem] = []
    gone = [ref for ref in refs if ref not in existing]
    if gone:
        items.append(ChannelHealthItem(
            key="collections_gone", state=TODO,
            label=f"{len(gone)} {_plural(len(gone), 'coleção escolhida não existe mais', 'coleções escolhidas não existem mais')}",
            action_label="Revisar coleções", action_target="collections",
        ))
    if not any(collection.product_queryset().exists() for collection in existing.values()):
        items.append(ChannelHealthItem(
            key="collections", state=TODO, label="As coleções escolhidas estão sem produtos",
            action_label="Escolher coleções", action_target="collections",
        ))
    elif not gone:
        count = len(existing)
        items.append(ChannelHealthItem(
            key="collections", state=OK,
            label=f"{count} {_plural(count, 'coleção escolhida', 'coleções escolhidas')}, com produtos",
        ))
    return items


def _active_item(channel, *, paused_label: str) -> ChannelHealthItem:
    if channel.is_active:
        return ChannelHealthItem(key="active", state=OK, label="Ligado")
    return ChannelHealthItem(key="active", state=TODO, label=paused_label, hint="Ligue no interruptor do card.")


def _display_devices(channel, *, now: datetime) -> list[ChannelHealthItem]:
    """TVs autorizadas, a última busca do quadro e o vencimento da autorização."""
    from shopman.doorman.conf import doorman_settings
    from shopman.doorman.models import TrustedDevice

    # Menuboard público (escotilha explícita) ou sem confiança de dispositivo: a TV
    # não precisa de autorização, e a busca dela não deixa rastro — nada a medir.
    if getattr(settings, "SHOPMAN_MENUBOARD_PUBLIC", False) or not doorman_settings.DEVICE_TRUST_ENABLED:
        return []
    devices = [d for d in TrustedDevice.active_for(_DISPLAY_SUBJECT, channel.ref) if d.expires_at > now]
    if not devices:
        return [ChannelHealthItem(
            key="paired", state=TODO, label="Nenhuma TV autorizada a mostrar este quadro",
            hint="Abra o endereço na TV e entre uma vez com um operador.",
            action_label="Parear uma TV", action_target="pair",
        )]
    items = [ChannelHealthItem(
        key="paired", state=OK,
        label=f"{len(devices)} {_plural(len(devices), 'TV autorizada', 'TVs autorizadas')}",
    )]
    seen = [d.last_used_at for d in devices if d.last_used_at]
    last_seen = max(seen) if seen else None
    if last_seen is None:
        items.append(ChannelHealthItem(
            key="seen", state=TODO, label="Nenhuma TV buscou o quadro ainda",
            hint="Confira se a TV está ligada e com o endereço aberto.",
            action_label="Parear uma TV", action_target="pair",
        ))
    elif now - last_seen > DISPLAY_SEEN_STALE_AFTER:
        items.append(ChannelHealthItem(
            key="seen", state=TODO, label=f"Nenhuma TV buscou o quadro desde {_hhmm(last_seen, now)}",
            hint="Confira se a TV está ligada, com rede e com o endereço aberto.",
            action_label="Parear uma TV", action_target="pair",
        ))
    else:
        items.append(ChannelHealthItem(key="seen", state=OK, label=f"A TV buscou o quadro às {_hhmm(last_seen, now)}"))
    in_use = [d for d in devices if d.last_used_at and now - d.last_used_at <= DISPLAY_IN_USE_WINDOW]
    expiring = [d for d in in_use if d.expires_at - now <= DISPLAY_EXPIRY_WARNING]
    if expiring:
        soonest = min(d.expires_at for d in expiring)
        days = max((soonest - now).days, 0)
        when = "hoje" if days == 0 else "amanhã" if days == 1 else f"em {days} dias"
        items.append(ChannelHealthItem(
            key="expiry", state=TODO, label=f"A autorização da TV vence {when}",
            hint="Vencida, a TV para de mostrar o quadro. Renove abrindo o endereço na TV com um operador.",
            action_label="Renovar", action_target="pair",
        ))
    return items


def _display_health(channel, *, now: datetime) -> ChannelHealthProjection:
    from shopman.backstage.projections.feeds import _output_path

    display = (channel.config or {}).get("display") or {}
    fmt = display.get("format") or ""
    output = _output_path(channel.ref, fmt)
    if not fmt:
        items = [_active_item(channel, paused_label="Pausado: a TV não mostra o cardápio")]
        items += _collection_items(display)
        items += _display_devices(channel, now=now)
        preview = (ChannelHealthLink(label="Ver a tela da TV", target="django", path=output),)
    else:
        platform = "o Google" if fmt == "google_merchant" else "a Meta" if fmt == "meta_catalog" else "a plataforma"
        items = [_active_item(channel, paused_label=f"Pausado: {platform} recebe erro ao buscar o feed")]
        items += _collection_items(display)
        preview = (ChannelHealthLink(label="Ver o feed", target="django", path=output),)
    return _health(channel.ref, items, preview)


# ── Loja online ───────────────────────────────────────────────────────────────


def _storefront_health(channel) -> ChannelHealthProjection:
    from shopman.backstage.services.integration_readiness import (
        efi_pix_readiness,
        otp_delivery_readiness,
        stripe_card_readiness,
    )

    items: list[ChannelHealthItem] = []
    if not channel.is_active:
        items.append(ChannelHealthItem(key="active", state=TODO, label="A loja online está desligada"))
    for key, readiness, ok_label, todo_label in (
        ("login", otp_delivery_readiness(), "O cliente recebe o código para entrar", "O cliente não recebe o código para entrar"),
        ("pix", efi_pix_readiness(), "Pix pronto para cobrar", "O Pix não está pronto para cobrar"),
        ("card", stripe_card_readiness(), "Cartão pronto para cobrar", "O cartão não está pronto para cobrar"),
    ):
        if readiness.ready:
            items.append(ChannelHealthItem(key=key, state=OK, label=ok_label))
        else:
            items.append(ChannelHealthItem(
                key=key, state=TODO, label=todo_label, hint=readiness.message,
                action_label="Ver integrações", action_target="admin", action_path="/admin/diagnostics/",
            ))
    base = str(getattr(settings, "SHOPMAN_STOREFRONT_BASE_URL", "") or "").strip().rstrip("/")
    preview = ()
    if base.startswith(("http://", "https://")):
        preview = (ChannelHealthLink(label="Ver a loja como o cliente", target="external", path=base),)
    return _health(channel.ref, items, preview)


# ── Board ─────────────────────────────────────────────────────────────────────


def build_channel_health(*, now: datetime | None = None) -> ChannelHealthBoardProjection:
    from shopman.shop.models import Channel

    now = now or timezone.now()
    storefront_ref = getattr(settings, "SHOPMAN_STOREFRONT_CHANNEL_REF", "web")
    channels: list[ChannelHealthProjection] = []
    for channel in Channel.objects.order_by("name", "ref"):
        if channel.commerce_policy == Channel.CommercePolicy.DISPLAY:
            channels.append(_display_health(channel, now=now))
        elif channel.ref == "ifood":
            channels.append(_health(channel.ref, _ifood_items(channel, now=now)))
        elif channel.ref == storefront_ref:
            channels.append(_storefront_health(channel))
    return ChannelHealthBoardProjection(channels=tuple(channels))


__all__ = [
    "ChannelHealthBoardProjection",
    "ChannelHealthItem",
    "ChannelHealthLink",
    "ChannelHealthProjection",
    "build_channel_health",
]
