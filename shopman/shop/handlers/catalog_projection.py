"""
Catalog projection handler + Offerman signal receivers.

CatalogProjectHandler — processes ``catalog.project_sku`` directives:
  - Checks iFood channel is active.
  - Resolves the SKU to a ProjectedItem via CatalogService.
  - Calls the backend adapter to push to the external API.
  - Handles 429 rate limiting (honoring Retry-After).
  - Uses DirectiveTransientError for retryable failures.

Os receivers agrupam sinais equivalentes enquanto a diretiva correspondente
ainda está na fila. Alterações durante um envio recebem outra ocorrência;
o mutex por SKU/canal serializa os envios.
"""

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import contextmanager
from datetime import timedelta
from threading import Lock
from uuid import uuid4
from weakref import WeakValueDictionary

from django.db import connection, transaction
from django.utils import timezone
from shopman.offerman.protocols.projection import ProjectedItem
from shopman.orderman.exceptions import DirectiveTransientError
from shopman.orderman.models import Directive

from shopman.shop.directives import CATALOG_PROJECT_SKU

logger = logging.getLogger(__name__)


# ── Handler ───────────────────────────────────────────────────────────────────


class CatalogProjectHandler:
    topic = CATALOG_PROJECT_SKU

    def __init__(self, backend=None) -> None:
        # backend kept for backward compat; at runtime we resolve per listing_ref.
        self._fallback_backend = backend

    def _resolve_backend(self, listing_ref: str):
        from shopman.offerman.conf import get_projection_backend

        backend = get_projection_backend(listing_ref)
        if backend is None and self._fallback_backend is not None:
            return self._fallback_backend
        return backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        payload = message.payload
        sku = payload["sku"]
        listing_ref = payload.get("listing_ref", "ifood")

        backend = self._resolve_backend(listing_ref)
        if backend is None:
            logger.warning("catalog_projection: no backend for listing_ref=%s, skipping", listing_ref)
            return

        if not _channel_or_feed_active(listing_ref):
            return

        failure = None
        with _sender_lock(sku, listing_ref) as acquired:
            if not acquired:
                # Contenção não é falha do provedor. Preserva o trabalho na fila
                # e libera o worker sem aguardar o HTTP de outra execução.
                message.status = "queued"
                message.attempts = max(0, message.attempts - 1)
                message.available_at = timezone.now() + timedelta(seconds=2)
                message.save(update_fields=["status", "attempts", "available_at", "updated_at"])
                return
            try:
                self._handle_locked(message, backend, sku, listing_ref)
            except DirectiveTransientError as exc:
                # Confirma o resultado registrado antes do retry do dispatcher.
                failure = exc
        if failure is not None:
            raise failure

    def _handle_locked(self, message, backend, sku, listing_ref):
        from shopman.shop.adapters.catalog_projection_google import GoogleMerchantRateLimitError
        from shopman.shop.adapters.catalog_projection_ifood import IFoodRateLimitError
        from shopman.shop.adapters.catalog_projection_meta import MetaRateLimitError

        # Retract-aware: read the SKU's CURRENT state and either upsert it (when
        # published + sellable) or retract it (paused, unpublished, or dropped
        # from the listing). Reading state at handle time makes the directive
        # idempotent to the final state, so rapid pause→resume converges.
        from shopman.shop.services import display_catalog, social_publish_rules

        item = _get_projected_item(sku, listing_ref)
        trigger = message.payload.get("trigger", "manual_resync")
        if display_catalog.is_platform_channel(listing_ref):
            # Canal de plataforma (Google, Meta): pausado, oculto e esgotado SEGUEM
            # na plataforma, cada um com o seu estado (``display_catalog``). Só sai
            # o item que deixou a composição do canal. Sem as regras de publicação:
            # barrar o envio de um item esgotado deixaria a plataforma anunciando
            # "em estoque" o que acabou.
            retracting = item is None
            try:
                result = backend.retract([sku], channel=listing_ref) if retracting else backend.project(
                    [item], channel=listing_ref
                )
            except (GoogleMerchantRateLimitError, MetaRateLimitError) as exc:
                self._defer_rate_limited(message, item, sku, listing_ref, exc.retry_after)
                return
            self._finish(result, item, sku, listing_ref, retracting=retracting)
            return

        retracting = not (item is not None and item.is_published and item.is_sellable)

        # Publish rules gate an UPSERT (not a retract): don't push an item the
        # channel_ref would reject (imageless) or that has no stock yet (→ pending,
        # re-projected when availability_changed fires).
        if not retracting:
            gate = social_publish_rules.projection_gate(item, listing_ref)
            if gate is not None:
                status, reason = gate
                _record_outcome(item, sku, listing_ref, status=status, error=reason)
                return

        try:
            if (
                item is not None
                and trigger in {"availability_changed", "stock_changed"}
                and hasattr(backend, "set_availability")
            ):
                result = backend.set_availability(item, channel=listing_ref)
                retracting = not (item.is_published and item.is_sellable)
            elif (
                not retracting
                and trigger in {"price_changed", "operator_price_intention"}
                and hasattr(backend, "update_price")
            ):
                result = backend.update_price(item, channel=listing_ref)
            elif not retracting:
                result = backend.project([item], channel=listing_ref)
            else:
                result = backend.retract([sku], channel=listing_ref)
        except IFoodRateLimitError as exc:
            self._defer_rate_limited(message, item, sku, listing_ref, exc.retry_after)
            return
        self._finish(result, item, sku, listing_ref, retracting=retracting)

    def _defer_rate_limited(self, message, item, sku, listing_ref, retry_after: int) -> None:
        """Rate limit: devolve a diretiva à fila com o Retry-After da plataforma."""
        _record_outcome(item, sku, listing_ref, status="pending", error="rate limited")
        message.status = "queued"
        message.available_at = timezone.now() + timedelta(seconds=retry_after)
        message.save(update_fields=["status", "available_at", "updated_at"])
        logger.warning(
            "catalog_projection: rate limited for %s/%s, retry in %ds",
            listing_ref, sku, retry_after,
        )

    def _finish(self, result, item, sku, listing_ref, *, retracting: bool) -> None:
        if result.success:
            _record_outcome(item, sku, listing_ref, status="retracted" if retracting else "synced")
            return

        error = "; ".join(result.errors)
        # Um item já projetado pode carregar uma pendência secundária, como a
        # foto. O estado mostra o trabalho restante sem esconder que os demais
        # dados chegaram ao canal.
        status = "pending" if result.projected else "error"
        _record_outcome(item, sku, listing_ref, status=status, error=error)
        raise DirectiveTransientError(error)


# ── Helpers ───────────────────────────────────────────────────────────────────


_local_locks = WeakValueDictionary()
_local_locks_guard = Lock()


@contextmanager
def _sender_lock(sku: str, listing_ref: str):
    """Serializa este handler sem bloquear as linhas editadas pelo operador.

    O advisory lock transacional mantém o backend PostgreSQL reservado mesmo
    com pooler transacional e não expira quando o reaper recupera a diretiva.
    SQLite usa mutex local ao processo, somente para desenvolvimento; a prova
    de concorrência roda em PostgreSQL. Chamadas diretas ao CatalogService ou
    ao CLI de sincronização não usam este mutex. Uma conexão perdida pode
    liberar o lock sem desfazer uma requisição já recebida pelo provedor.
    """
    key = int.from_bytes(hashlib.sha256(
        json.dumps([CATALOG_PROJECT_SKU, listing_ref, sku]).encode(),
    ).digest()[:8], "big", signed=True)
    if connection.vendor == "postgresql":
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [key])
                acquired = cursor.fetchone()[0]
            yield acquired
        return
    with _local_locks_guard:
        lock = _local_locks.get(key)
        if lock is None:
            lock = Lock()
            _local_locks[key] = lock
    acquired = lock.acquire(blocking=False)
    try:
        yield acquired
    finally:
        if acquired:
            lock.release()


@transaction.atomic
def _record_outcome(snapshot: ProjectedItem | None, sku: str, listing_ref: str, *, status: str, error: str = "") -> None:
    from shopman.shop.models import CatalogSyncState
    from shopman.shop.services import catalog_sync

    state, _ = CatalogSyncState.objects.get_or_create(sku=sku, channel_ref=listing_ref)
    CatalogSyncState.objects.select_for_update().get(pk=state.pk)
    # O operador pode confirmar uma edição durante o HTTP. Sob este lock curto,
    # compara o snapshot atual antes de declarar sincronização. Uma diretiva
    # irmã ainda running pode já ter finalizado seu HTTP; não invalida o resultado.
    # Leituras de domínio usam apenas MVCC: preserva a ordem domínio→sync.
    if _get_projected_item(sku, listing_ref) != snapshot:
        status, error = "pending", ""
    catalog_sync.record_sync(sku, listing_ref, status=status, error=error)


def _channel_or_feed_active(listing_ref: str) -> bool:
    from shopman.shop.models import Channel
    from shopman.shop.services import display_catalog

    # Canal de plataforma desligado continua sendo enviado: os itens vão como fora
    # de estoque (``display_catalog``), e é isso que a plataforma precisa saber.
    if display_catalog.is_platform_channel(listing_ref):
        return True
    if Channel.objects.filter(ref=listing_ref, is_active=True).exists():
        return True
    # Canal de exibição também é alvo de projeção (o catálogo Meta é um deles), e
    # agora chaveia por ref igual ao transacional — era por `kind`, duas chaves.
    if Channel.objects.filter(
        ref=listing_ref, is_active=True, commerce_policy=Channel.CommercePolicy.DISPLAY
    ).exists():
        return True
    return False


def _get_projected_item(sku: str, listing_ref: str) -> ProjectedItem | None:
    from shopman.offerman.service import CatalogService

    from shopman.shop.services import display_catalog

    if display_catalog.is_platform_channel(listing_ref):
        return display_projected_item(listing_ref, sku)
    items = CatalogService.get_projection_items(listing_ref)
    for item in items:
        if item.sku == sku:
            return item
    return None


def display_projected_item(listing_ref: str, sku: str) -> ProjectedItem | None:
    """O item do canal de plataforma, com a decisão de ``display_catalog`` inteira.

    O backend da plataforma lê ``metadata["display"]`` e só traduz; as flags
    espelham a decisão (oculto → não publicado, sem compra → não vendável) para a
    matriz e o estado de sync lerem igual aos outros canais.
    """
    from shopman.shop.services import display_catalog

    item = display_catalog.display_item(listing_ref, sku)
    if item is None:
        return None
    return ProjectedItem(
        sku=item.sku,
        name=item.title,
        description=item.description,
        unit="",
        price_q=item.price_q,
        is_published=not item.hidden,
        is_sellable=item.available,
        category=item.custom_label_0,
        image_url=item.image_link,
        metadata={"display": item},
    )


def _projection_listing_refs() -> list[str]:
    from shopman.offerman.conf import get_projection_backend_channels
    return get_projection_backend_channels()


# ── Signal receivers ──────────────────────────────────────────────────────────


def on_product_created(sender, instance, sku: str, **kwargs) -> None:
    from shopman.shop.services import catalog_sync, social_publish_rules

    for listing_ref in _projection_listing_refs():
        if not social_publish_rules.should_auto_publish_new(listing_ref):
            # Publish rule opted out of auto-entry — record it, wait for a manual
            # publish/resync. (Manual resync bypasses this guard.)
            catalog_sync.record_sync(
                sku, listing_ref, status="skipped", error="regra: não publicar ao criar",
            )
            continue
        _enqueue_project(sku, listing_ref, trigger="product_created", extra={})


def on_product_updated(sender, instance, sku: str, **kwargs) -> None:
    """Product data changed (name/description/publish) → re-project everywhere."""
    for listing_ref in _projection_listing_refs():
        _enqueue_project(sku, listing_ref, trigger="product_updated", extra={})


def on_price_changed(
    sender,
    instance,
    listing_ref: str,
    sku: str,
    old_price_q: int,
    new_price_q: int,
    **kwargs,
) -> None:
    from shopman.shop.services import display_catalog

    refs = set(_projection_listing_refs())
    if listing_ref in refs:
        _enqueue_project(
            sku,
            listing_ref,
            trigger="price_changed",
            extra={"old_price_q": old_price_q, "new_price_q": new_price_q},
        )
    # O preço dos canais de plataforma vem do canal apontado por ``prices_from``.
    for display_ref in display_catalog.channels_priced_from(listing_ref):
        if display_ref in refs:
            _enqueue_project(sku, display_ref, trigger="price_changed", extra={})


def on_availability_changed(sender, instance, listing_ref: str, sku: str, **kwargs) -> None:
    """Per-channel pause/resume → re-project (handler upserts or retracts)."""
    if listing_ref not in _projection_listing_refs():
        return
    _enqueue_project(sku, listing_ref, trigger="availability_changed", extra={})


def enqueue_project(sku: str, listing_ref: str, *, trigger: str = "manual_resync") -> Directive | None:
    """Public re-projection enqueue — used by the backstage "sincronizar agora" action."""
    return _enqueue_project(sku, listing_ref, trigger=trigger, extra={})


def enqueue_display_skus(listing_ref: str, skus, *, trigger: str = "display_changed") -> int:
    """Pausa, ocultação, coleções do canal de plataforma mudaram → reenvia esses SKUs.

    Sem backend configurado para o canal, não há para onde enviar: volta calado.
    """
    if listing_ref not in _projection_listing_refs():
        return 0
    count = 0
    for sku in sorted(set(skus)):
        _enqueue_project(sku, listing_ref, trigger=trigger, extra={})
        count += 1
    return count


@transaction.atomic
def _enqueue_project(sku: str, listing_ref: str, trigger: str, extra: dict) -> Directive | None:
    from shopman.shop.services import catalog_sync

    # A mutação do chamador e o indicador pendente confirmam juntos. Ordem dos
    # locks igual à operação: linhas de domínio, estado de sync e depois outbox.
    catalog_sync.record_sync(sku, listing_ref, status="pending")
    fingerprint_data = json.dumps({"listing_ref": listing_ref, "sku": sku, "trigger": trigger, **extra}, sort_keys=True)
    fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()
    dedupe_key = f"{CATALOG_PROJECT_SKU}:{listing_ref}:{sku}:{fingerprint[:16]}"
    if len(dedupe_key) > 95:  # Reserva espaço para o sufixo da ocorrência nos 128 caracteres.
        dedupe_key = f"{CATALOG_PROJECT_SKU}:{fingerprint[:48]}"

    # Agrupa apenas trabalho não iniciado. O envio em execução já leu o snapshot
    # e não pode representar uma edição recebida durante sua requisição HTTP.
    existing = Directive.objects.select_for_update().filter(
        dedupe_key__startswith=f"{dedupe_key}:",
        status="queued",
    ).first()
    if existing is not None:
        return existing

    from shopman.shop.directives import create_deduped

    created = create_deduped(
        CATALOG_PROJECT_SKU,
        payload={"sku": sku, "listing_ref": listing_ref, "trigger": trigger},
        dedupe_key=f"{dedupe_key}:{uuid4().hex}",
    )
    if created is None:
        raise RuntimeError("Falha ao registrar a sincronização do catálogo; alteração revertida.")
    logger.debug("catalog_projection: enqueued %s for %s/%s", trigger, listing_ref, sku)
    return created
