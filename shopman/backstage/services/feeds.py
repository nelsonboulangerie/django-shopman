"""
Mutações dos canais de EXIBIÇÃO para o Gestor — coleções, rotação, pausa e ocultação por item.

Ligar/desligar o canal (de venda OU de exibição) é o toggle "Ativo", que mora em
``shopman.shop.services.channel_switch``.

Escreve no ``Channel`` de ``commerce_policy="display"`` (as coleções e a pausa local
vivem no aspecto ``config.display``, sem migração — é o padrão de extensibilidade do
Core) e sinaliza a superfície para atualizar em tempo real.
"""

from __future__ import annotations

from django.db import transaction

from shopman.backstage.services.exceptions import CatalogError


def _notify(ref: str) -> None:
    """Empurra o evento SSE p/ a superfície de display (menuboard atualiza na hora)."""
    from shopman.shop.handlers._sse_emitters import emit_surface_changed

    emit_surface_changed(ref)




def _display_channel(ref: str):
    """O canal de exibição, ou erro nomeando o que o operador vê."""
    from shopman.shop.models import Channel

    channel = Channel.objects.select_for_update().filter(
        ref=ref, commerce_policy=Channel.CommercePolicy.DISPLAY
    ).first()
    if channel is None:
        raise CatalogError(f"Feed '{ref}' não encontrado.")
    return channel


def _display(channel) -> dict:
    return dict((channel.config or {}).get("display") or {})


def _save_display(channel, display: dict) -> None:
    channel.config = {**(channel.config or {}), "display": display}
    # `Channel` não tem timestamps (o `Feed` tinha) — só o campo que muda.
    channel.save(update_fields=["config"])


class FeedConflict(CatalogError):
    """The selected feed field changed after the operator read it."""


def revision(channel, field: str) -> str:
    from shopman.shop.services.menuboard_schedule import automatic_settings
    from shopman.shop.services.remote_mutations import mutation_fingerprint

    display = _display(channel)
    automatic_enabled, idle_messages = automatic_settings(channel)
    values = {
        "collections": display.get("collections") or [],
        "rotation": [display.get("rotate_seconds", 0), display.get("items_per_page", 0)],
        "automatic": [automatic_enabled, idle_messages],
    }
    return mutation_fingerprint({"version": 1, "ref": channel.ref, "policy": channel.commerce_policy,
        "format": display.get("format") or "", "field": field, "value": values[field]})


def _check_revision(channel, field: str, expected_revision):
    if expected_revision is not None and revision(channel, field) != expected_revision:
        raise FeedConflict("Este campo mudou. Seu rascunho foi preservado; confira o valor atual antes de salvar.")


@transaction.atomic
def set_collections(ref: str, collection_refs: list[str], *, expected_revision=None) -> None:
    """Define quais coleções o feed exibe (a ORDEM é global, via Collection.sort_order)."""
    from shopman.offerman.models import Collection

    sc = _display_channel(ref)
    _check_revision(sc, "collections", expected_revision)

    cleaned = [str(r).strip() for r in collection_refs if str(r).strip()]
    valid = set(Collection.objects.select_for_update().filter(ref__in=cleaned).order_by("pk").values_list("ref", flat=True))
    unknown = [r for r in cleaned if r not in valid]
    if unknown:
        raise CatalogError(f"Coleção(ões) inexistente(s): {', '.join(unknown)}.")

    # dedup preservando a ordem de chegada (a exibição reordena por sort_order de qq jeito)
    seen: set[str] = set()
    ordered = [r for r in cleaned if not (r in seen or seen.add(r))]
    display = _display(sc)
    if ordered != list(display.get("collections") or []):
        before = _composition_skus(ref)
        display["collections"] = ordered
        _save_display(sc, display)
        _notify(ref)
        # Quem entrou e quem saiu: o que ficou também, porque o custom_label pode mudar.
        _project(ref, before | _composition_skus(ref))


def _composition_skus(ref: str) -> set[str]:
    """SKUs do catálogo de plataforma; quadro (menuboard) não tem catálogo externo."""
    from shopman.shop.services import display_catalog

    if not display_catalog.is_platform_channel(ref):
        return set()
    return set(display_catalog.composition_skus(ref))


def _nonneg_int(value, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CatalogError(f"{label} deve ser um inteiro >= 0.")
    return value


@transaction.atomic
def set_rotation(ref: str, *, rotate_seconds: int, items_per_page: int, expected_revision=None) -> None:
    """Configura a rotação de páginas do quadro (menuboard).

    ``rotate_seconds`` = cadência da troca (0 desliga); ``items_per_page`` =
    teto de itens por tela (0 = tudo numa página). Só faz sentido no quadro —
    feed de plataforma (XML) não tem tela para rotacionar.
    """
    rotate_seconds = _nonneg_int(rotate_seconds, "rotate_seconds")
    items_per_page = _nonneg_int(items_per_page, "items_per_page")
    if 0 < rotate_seconds < 5:
        raise CatalogError("A rotação precisa de pelo menos 5 segundos por página.")
    # Um sem o outro é promessa vazia: rotação sem teto não tem página para
    # trocar, e teto sem rotação esconderia tudo além da primeira tela.
    if (rotate_seconds > 0) != (items_per_page > 0):
        raise CatalogError(
            "Defina a cadência E o teto de itens por tela (ou zere os dois para desligar)."
        )

    sc = _display_channel(ref)
    _check_revision(sc, "rotation", expected_revision)
    display = _display(sc)
    if display.get("format"):
        raise CatalogError(f"'{ref}' é um feed de plataforma: não tem páginas para rotacionar.")

    if (
        display.get("rotate_seconds", 0) != rotate_seconds
        or display.get("items_per_page", 0) != items_per_page
    ):
        display["rotate_seconds"] = rotate_seconds
        display["items_per_page"] = items_per_page
        _save_display(sc, display)
        _notify(ref)


@transaction.atomic
def set_automatic(ref: str, *, enabled: bool, idle_messages: list[str], expected_revision=None) -> None:
    """Liga/desliga a janela automática e configura até duas frases do descanso."""
    from shopman.shop.services.menuboard_schedule import MAX_IDLE_MESSAGE_LENGTH, normalize_idle_messages

    if not isinstance(enabled, bool):
        raise CatalogError("enabled deve ser verdadeiro ou falso.")
    if (
        not isinstance(idle_messages, list)
        or not 1 <= len(idle_messages) <= 2
        or not all(isinstance(value, str) for value in idle_messages)
    ):
        raise CatalogError("Informe uma ou duas mensagens de descanso.")
    messages = normalize_idle_messages(idle_messages)
    if any(len(message) > MAX_IDLE_MESSAGE_LENGTH for message in messages):
        raise CatalogError(f"Cada mensagem de descanso deve ter até {MAX_IDLE_MESSAGE_LENGTH} caracteres.")

    sc = _display_channel(ref)
    _check_revision(sc, "automatic", expected_revision)
    display = _display(sc)
    if display.get("format"):
        raise CatalogError(f"'{ref}' é um feed de plataforma: modo automático existe apenas no menuboard.")

    value = {"enabled": enabled, "idle_messages": list(messages)}
    if display.get("automatic") != value:
        display["automatic"] = value
        _save_display(sc, display)
        _notify(ref)


def _set_skus(ref: str, key: str, skus: list[str], *, on: bool) -> int:
    """Liga/desliga SKUs numa lista de ``config.display`` (``paused_skus``/``hidden_skus``)."""
    cleaned = [str(s).strip() for s in skus if str(s).strip()]
    if not cleaned:
        return 0
    sc = _display_channel(ref)

    current = {str(s) for s in (_display(sc).get(key) or [])}
    before = set(current)
    if on:
        current.update(cleaned)
    else:
        current.difference_update(cleaned)
    if current == before:
        return 0

    display = _display(sc)
    display[key] = sorted(current)
    _save_display(sc, display)
    _notify(ref)
    _project(ref, current ^ before)
    return len(current ^ before)


def _project(ref: str, skus) -> None:
    """A plataforma (Google, Meta) recebe na hora o que mudou neste canal."""
    from shopman.shop.handlers.catalog_projection import enqueue_display_skus

    enqueue_display_skus(ref, skus)


@transaction.atomic
def set_item_paused(ref: str, sku: str, *, paused: bool) -> bool:
    """Pausa/reativa UM item neste feed (equivalente a pausar num canal).

    Grava em ``config.display.paused_skus``. Retorna o estado final ``paused``. A
    pausa global do produto continua gateando por cima.
    """
    if not str(sku).strip():
        raise CatalogError("sku é obrigatório.")
    _set_skus(ref, "paused_skus", [sku], on=paused)
    return paused


@transaction.atomic
def set_items_paused(ref: str, skus: list[str], *, paused: bool) -> int:
    """Pausa/reativa em lote vários itens neste feed. Retorna quantos mudaram."""
    return _set_skus(ref, "paused_skus", skus, on=paused)


@transaction.atomic
def set_item_hidden(ref: str, sku: str, *, hidden: bool) -> bool:
    """Oculta/exibe UM item neste feed (equivalente a ocultar num canal).

    Grava em ``config.display.hidden_skus``. Oculto vence pausado: no quadro o item
    sai da tela, no feed de plataforma ele fica fora de todos os destinos.
    """
    if not str(sku).strip():
        raise CatalogError("sku é obrigatório.")
    _set_skus(ref, "hidden_skus", [sku], on=hidden)
    return hidden


@transaction.atomic
def set_items_hidden(ref: str, skus: list[str], *, hidden: bool) -> int:
    """Oculta/exibe em lote vários itens neste feed. Retorna quantos mudaram."""
    return _set_skus(ref, "hidden_skus", skus, on=hidden)
