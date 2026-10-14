"""Vitrine que ESPELHA a de outro canal: mesmos itens, mesmo preço, mesmas flags.

O WhatsApp (Concierge) vende para o mesmo cliente remoto da loja online, só que
conversando. A vitrine dele não é uma curadoria própria: é a da loja. Antes disto
o ``bootstrap_whatsapp_channel`` copiava os itens uma vez e, dali em diante, cada
produto novo, preço mudado ou item despublicado no site ficava para trás no
WhatsApp até alguém rodar o comando de novo (P1-14, ``docs/reference/cenarios-de-pedido.md``).

O ponteiro mora no canal: ``Channel.config["pricing"]["listing_from"] = "<ref>"``.
É lido CRU do canal, sem a cascata do ``ChannelConfig`` (um ``Shop.defaults`` com a
chave faria todo canal espelhar a loja). Mesmo desenho do ``display.prices_from``
dos canais de exibição (``services/display_prices.py``).

Por que materializar em vez de ler a vitrine do site na hora: a convenção
"``Listing.ref == Channel.ref``" atravessa preço (``handlers/pricing.py``),
disponibilidade (``services/availability.py``), Concierge, SSE, projeção e a
matriz do catálogo. Trocar a leitura em todos esses pontos espalharia o ponteiro
por uma dúzia de arquivos, e o que ficasse de fora divergiria em silêncio. Aqui a
vitrine do espelho continua existindo e é mantida igual à da fonte por um dono só:

- ``ListingItem`` salvo ou apagado na fonte → o espelho acompanha o produto, na
  mesma transação (receivers em ``handlers/listing_mirror.py``);
- ``ListingItem`` mexido direto no espelho → volta a ser o da fonte (o espelho não
  tem edição própria; a matriz do catálogo recusa antes, com o motivo);
- escrita em lote que não dispara signal (``bulk_update`` da matriz) chama
  ``realign`` ao terminar;
- ``Channel`` salvo com o ponteiro → ``realign`` (ligar o espelho no Admin já
  alinha tudo).

A gravação usa ``save()``/``delete()`` de cada item: histórico, porteiro fiscal,
SSE e projeção valem para o espelho como para qualquer vitrine.

Só a VITRINE espelha. Regra de preço por canal (Xepa só no balcão, promoção com
canais) mora no motor de regras e continua escopada pelo canal do pedido.
"""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field

from django.db import transaction

logger = logging.getLogger(__name__)

#: Ligado enquanto o próprio espelho grava, para os receivers não reagirem à
#: escrita dele.
_SYNCING: contextvars.ContextVar[bool] = contextvars.ContextVar("listing_mirror_syncing", default=False)

_FIELDS = ("price_q", "is_published", "is_sellable")


@dataclass(frozen=True)
class MirrorResult:
    created: int = 0
    updated: int = 0
    deleted: int = 0
    #: Uma linha legível por mudança (``+ PAO: R$ 5,50``), para o comando relatar.
    lines: tuple[str, ...] = field(default=(), compare=False)

    @property
    def changed(self) -> int:
        return self.created + self.updated + self.deleted

    def __add__(self, other: MirrorResult) -> MirrorResult:
        return MirrorResult(
            self.created + other.created,
            self.updated + other.updated,
            self.deleted + other.deleted,
            self.lines + other.lines,
        )


def is_syncing() -> bool:
    return _SYNCING.get()


@contextmanager
def _syncing():
    token = _SYNCING.set(True)
    try:
        yield
    finally:
        _SYNCING.reset(token)


def source_ref_from_config(config) -> str:
    """O ref da vitrine que este ``Channel.config`` espelha ("" = vitrine própria)."""
    pricing = (config or {}).get("pricing") if isinstance(config, dict) else None
    if not isinstance(pricing, dict):
        return ""
    return str(pricing.get("listing_from") or "").strip()


def source_ref(mirror_ref: str) -> str:
    """O ref da vitrine que o canal ``mirror_ref`` espelha, ou ""."""
    from shopman.shop.models import Channel

    config = Channel.objects.filter(ref=mirror_ref).values_list("config", flat=True).first()
    source = source_ref_from_config(config)
    return "" if source == mirror_ref else source


def mirror_refs(source: str) -> list[str]:
    """Os canais cuja vitrine espelha ``source``."""
    from shopman.shop.models import Channel

    if not source:
        return []
    return [
        ref
        for ref in Channel.objects.filter(config__pricing__listing_from=source)
        .order_by("ref")
        .values_list("ref", flat=True)
        if ref != source
    ]


def _mirror_listing(mirror_ref: str):
    from shopman.offerman.models import Listing

    from shopman.shop.models import Channel

    listing = Listing.objects.filter(ref=mirror_ref).first()
    if listing is not None:
        return listing
    name = Channel.objects.filter(ref=mirror_ref).values_list("name", flat=True).first() or mirror_ref
    return Listing.objects.create(ref=mirror_ref, name=name, is_active=True)


def sync(mirror_ref: str, source: str, *, product_ids=None) -> MirrorResult:
    """Deixa a vitrine ``mirror_ref`` igual à ``source`` (só ``product_ids``, se dado).

    Idempotente: sem diferença, não grava nada. Cria a vitrine do espelho se ela
    não existir. Sem a vitrine da fonte, não toca em nada (avisa no log): apagar o
    espelho inteiro por um ref digitado errado seria pior que deixá-lo como está.
    """
    from shopman.offerman.models import Listing, ListingItem

    if not mirror_ref or not source or mirror_ref == source:
        return MirrorResult()
    source_listing = Listing.objects.filter(ref=source).first()
    if source_listing is None:
        logger.warning("listing_mirror.source_missing mirror=%s source=%s", mirror_ref, source)
        return MirrorResult()

    with transaction.atomic(), _syncing():
        mirror = _mirror_listing(mirror_ref)
        wanted_qs = ListingItem.objects.filter(listing=source_listing)
        have_qs = ListingItem.objects.filter(listing=mirror)
        if product_ids is not None:
            ids = list(product_ids)
            wanted_qs = wanted_qs.filter(product_id__in=ids)
            have_qs = have_qs.filter(product_id__in=ids)
        wanted = {(row.product_id, row.min_qty): row for row in wanted_qs.select_related("product")}
        have = {
            (row.product_id, row.min_qty): row
            for row in have_qs.select_related("product").select_for_update(of=("self",))
        }

        created = updated = deleted = 0
        lines: list[str] = []
        for key, item in have.items():
            if key not in wanted:
                lines.append(f"- {_label(item)}")
                item.delete()
                deleted += 1
        for key, src in wanted.items():
            item = have.get(key)
            if item is None:
                lines.append(f"+ {_label(src)}")
                ListingItem.objects.create(
                    listing=mirror,
                    product_id=src.product_id,
                    min_qty=src.min_qty,
                    **{field: getattr(src, field) for field in _FIELDS},
                )
                created += 1
                continue
            changed = [field for field in _FIELDS if getattr(item, field) != getattr(src, field)]
            if changed:
                for name in changed:
                    setattr(item, name, getattr(src, name))
                lines.append(f"~ {_label(src)}")
                item.save(update_fields=[*changed, "updated_at"])
                updated += 1

    result = MirrorResult(created, updated, deleted, tuple(lines))
    if result.changed:
        logger.info(
            "listing_mirror.synced mirror=%s source=%s created=%d updated=%d deleted=%d",
            mirror_ref, source, created, updated, deleted,
        )
    return result


def _label(item) -> str:
    tier = "" if item.min_qty == 1 else f" (a partir de {item.min_qty.normalize()})"
    flags = ("" if item.is_published else " (não publicado)") + ("" if item.is_sellable else " (não vendável)")
    price = f"{item.price_q / 100:.2f}".replace(".", ",")
    return f"{item.product.sku}{tier}: R$ {price}{flags}"


def realign(listing_ref: str, *, product_ids=None) -> MirrorResult:
    """Realinha tudo que depende de ``listing_ref``: ela mesma, se é espelho, e os espelhos dela."""
    result = MirrorResult()
    if not listing_ref:
        return result
    own_source = source_ref(listing_ref)
    if own_source:
        result += sync(listing_ref, own_source, product_ids=product_ids)
    for mirror_ref in mirror_refs(listing_ref):
        result += sync(mirror_ref, listing_ref, product_ids=product_ids)
    return result
