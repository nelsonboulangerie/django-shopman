"""
Mutações dos canais de EXIBIÇÃO para o Gestor — ligar/pausar + escolher coleções.

Escreve no ``Channel`` de ``commerce_policy="display"`` (as coleções e a pausa local
vivem no aspecto ``config.display``, sem migração — é o padrão de extensibilidade do
Core) e sinaliza a superfície para atualizar em tempo real.
"""

from __future__ import annotations

from shopman.backstage.services.exceptions import CatalogError


def _notify(ref: str) -> None:
    """Empurra o evento SSE p/ a superfície de display (menuboard atualiza na hora)."""
    from shopman.shop.handlers._sse_emitters import emit_surface_changed

    emit_surface_changed(ref)




def _display_channel(ref: str):
    """O canal de exibição, ou erro nomeando o que o operador vê."""
    from shopman.shop.models import Channel

    channel = Channel.objects.filter(
        ref=ref, commerce_policy=Channel.CommercePolicy.DISPLAY
    ).first()
    if channel is None:
        raise CatalogError(f"Feed '{ref}' não encontrado.")
    return channel


def _display(channel) -> dict:
    return dict((channel.config or {}).get("display") or {})


def _save_display(channel, display: dict) -> None:
    channel.config = {**(channel.config or {}), "display": display}
    # `Channel` não tem timestamps (o `Showcase` tinha) — só o campo que muda.
    channel.save(update_fields=["config"])


def _paused(channel) -> set[str]:
    return {str(s) for s in (_display(channel).get("paused_skus") or [])}


def set_active(ref: str, is_active: bool) -> None:
    sc = _display_channel(ref)
    if sc.is_active != is_active:
        sc.is_active = is_active
        sc.save(update_fields=["is_active"])
        _notify(ref)


def set_collections(ref: str, collection_refs: list[str]) -> None:
    """Define quais coleções o feed exibe (a ORDEM é global, via Collection.sort_order)."""
    from shopman.offerman.models import Collection

    sc = _display_channel(ref)

    cleaned = [str(r).strip() for r in collection_refs if str(r).strip()]
    valid = set(Collection.objects.filter(ref__in=cleaned).values_list("ref", flat=True))
    unknown = [r for r in cleaned if r not in valid]
    if unknown:
        raise CatalogError(f"Coleção(ões) inexistente(s): {', '.join(unknown)}.")

    # dedup preservando a ordem de chegada (a exibição reordena por sort_order de qq jeito)
    seen: set[str] = set()
    ordered = [r for r in cleaned if not (r in seen or seen.add(r))]
    display = _display(sc)
    if ordered != list(display.get("collections") or []):
        display["collections"] = ordered
        _save_display(sc, display)
        _notify(ref)


def set_item_paused(ref: str, sku: str, *, paused: bool) -> bool:
    """Pausa/reativa UM item neste feed (equivalente a pausar num canal).

    Grava em ``config.display.paused_skus``. Retorna o estado final ``paused``. A
    pausa global do produto continua gateando por cima.
    """
    sku = str(sku).strip()
    if not sku:
        raise CatalogError("sku é obrigatório.")
    sc = _display_channel(ref)

    current = _paused(sc)
    if paused and sku not in current:
        current.add(sku)
    elif not paused and sku in current:
        current.discard(sku)
    else:
        return paused  # sem mudança

    display = _display(sc)
    display["paused_skus"] = sorted(current)
    _save_display(sc, display)
    _notify(ref)
    return paused


def set_items_paused(ref: str, skus: list[str], *, paused: bool) -> int:
    """Pausa/reativa em lote vários itens neste feed. Retorna quantos mudaram."""
    cleaned = [str(s).strip() for s in skus if str(s).strip()]
    if not cleaned:
        return 0
    sc = _display_channel(ref)

    current = _paused(sc)
    before = set(current)
    if paused:
        current.update(cleaned)
    else:
        current.difference_update(cleaned)
    if current == before:
        return 0

    display = _display(sc)
    display["paused_skus"] = sorted(current)
    _save_display(sc, display)
    _notify(ref)
    return len(current ^ before)
