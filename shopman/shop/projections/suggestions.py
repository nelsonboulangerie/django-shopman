"""Um motor de sugestão, para o site e para o chat.

Antes disto havia uma regra por superfície, e a que estava no ar era "o item
mais popular que não está na sacola" — que ofereceu **Água** a quem levava pão.
Aqui há um lugar só, e ele combina três coisas:

1. **Co-ocorrência** — o que a casa vende junto, da tabela de afinidade
   (``ProductAffinity``, calculada de noite). Lift, não contagem: aparecer com
   tudo é o oposto de combinar com algo.
2. **Pareamentos configuráveis** — ``suggestion.complement`` em ``RuleConfig``.
   O motor não conhece "natureza" nem "sabor": ele lê a regra e obedece, e
   atributo novo no Admin amplia o vocabulário sem deploy.
3. **Portões** — visível no canal, vendável, disponível agora, fora da sacola.
   Sugestão que não passa nos portões não existe.

⚠️ **Portão é portão; sinal é sinal.** Preço não é portão: um filtro duro de
preço calaria a sugestão numa sacola barata, e "sugestão que não sai" é pior
que "sugestão um pouco cara". ``price: below_cart_average`` é preferência, e
entra na pontuação. Já o ``context`` (não sugerir sorvete numa entrega) é
portão de verdade — ali a sugestão seria uma promessa que a casa não cumpre.

⚠️ **Regra em branco não quebra.** Sem pareamento cadastrado o motor roda só com
co-ocorrência e portões. Cada atributo cadastrado acrescenta sinal; nenhum é
pré-requisito.

Toda sugestão carrega ``reasons`` citando **a regra que a produziu** — é o que
torna o ajuste no Admin mensurável, em vez de fé.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)

COMPLEMENT = "complement"
SUBSTITUTE = "substitute"

#: Candidatos considerados antes da pontuação. Alto o bastante para o pareamento
#: ter de onde escolher quando a afinidade é fina, baixo o bastante para a
#: consulta de disponibilidade não virar varredura de catálogo.
CANDIDATE_POOL = 40


@dataclass(frozen=True)
class Suggestion:
    """Um SKU oferecido, com o preço que o checkout cobraria e o porquê."""

    sku: str
    name: str
    unit_price_q: int
    image_url: str | None
    score: float
    #: Códigos citando a regra que produziu a sugestão. Ex.:
    #: ``("affinity:BAG", "pairing:natureza=comida→bebida")``.
    reasons: tuple[str, ...]


def suggest(
    objective: str,
    *,
    cart_skus: set[str],
    channel_ref: str,
    anchor_sku: str | None = None,
    context: dict | None = None,
    surface: str = "web",
    limit: int | None = None,
) -> tuple[Suggestion, ...]:
    """Sugestões ordenadas para ``objective``, já passadas pelos portões.

    ``surface`` escolhe o limite em ``per_surface`` quando ``limit`` não vem.
    ``context`` é o que a superfície sabe do pedido (``{"fulfillment":
    "delivery"}``) e alimenta os filtros de contexto da regra.
    """
    if objective == SUBSTITUTE:
        # O substituto é da F2 (refino do `find_substitutes` no Offerman).
        # Devolver vazio aqui seria dizer "não há substituto", que é falso.
        raise NotImplementedError(
            "suggest('substitute') chega na F2; hoje o caminho é "
            "shopman.shop.services.substitutes.find."
        )
    if objective != COMPLEMENT:
        raise ValueError(f"Objetivo desconhecido: {objective!r}.")

    rule = _complement_rule()
    limit = _resolve_limit(limit, rule, surface)
    if limit <= 0:
        return ()

    candidates = _candidates(cart_skus, rule)
    if not candidates:
        return ()

    products = _passing_the_gates(list(candidates), channel_ref=channel_ref)
    if not products:
        return ()

    scored = _score(
        products, cart_skus=cart_skus, anchor_sku=anchor_sku,
        rule=rule, context=context or {}, channel_ref=channel_ref,
    )
    return tuple(scored[:limit])


# --- a regra ---------------------------------------------------------------


def _complement_rule() -> dict:
    """Params de ``suggestion.complement``, ou ``{}`` se não houver regra ativa."""
    from shopman.shop.rules.engine import get_rule_params

    return get_rule_params("suggestion.complement") or {}


def _resolve_limit(limit: int | None, rule: dict, surface: str) -> int:
    if limit is not None:
        return limit
    per_surface = rule.get("per_surface") or {}
    return int(per_surface.get(surface, 1))


# --- candidatos ------------------------------------------------------------


def _candidates(cart_skus: set[str], rule: dict) -> dict[str, dict]:
    """``{sku: {"affinity": lift, "reasons": [...]}}`` — quem sequer entra na fila.

    A afinidade traz os pares que o histórico conhece. Os pareamentos trazem o
    resto: sem eles, um produto novo (sem histórico) nunca seria sugerido.
    """
    candidates: dict[str, dict] = {}

    for sku, lift, partner in _affinity_partners(cart_skus):
        entry = candidates.setdefault(sku, {"affinity": 0.0, "reasons": []})
        if lift > entry["affinity"]:
            entry["affinity"] = lift
            entry["reasons"] = [f"affinity:{partner}"]

    if rule.get("pairings"):
        for sku in _pairing_pool(cart_skus, len(candidates)):
            candidates.setdefault(sku, {"affinity": 0.0, "reasons": []})

    for sku in cart_skus:
        candidates.pop(sku, None)
    return candidates


def _affinity_partners(cart_skus: set[str]):
    """``(sku, lift, parceiro)`` para o que o histórico associa à sacola."""
    from shopman.shop.models import ProductAffinity

    if not cart_skus:
        return
    rows = (
        ProductAffinity.objects.filter(sku_a__in=cart_skus)
        .exclude(sku_b__in=cart_skus)
        .order_by("-lift")[: CANDIDATE_POOL * 2]
    )
    for row in rows:
        yield row.sku_b, row.lift, row.sku_a


def _pairing_pool(cart_skus: set[str], already: int) -> list[str]:
    """SKUs vendáveis para o pareamento avaliar, além dos que a afinidade trouxe.

    Ordenado por nome só para ser determinístico: quem ordena de verdade é a
    pontuação, logo abaixo.
    """
    from shopman.offerman.models import Product

    room = max(0, CANDIDATE_POOL - already)
    if not room:
        return []
    return list(
        Product.objects.filter(is_published=True, is_sellable=True)
        .exclude(sku__in=cart_skus)
        .order_by("sku")
        .values_list("sku", flat=True)[:room]
    )


# --- os portões ------------------------------------------------------------


def _passing_the_gates(skus: list[str], *, channel_ref: str) -> dict[str, object]:
    """``{sku: Product}`` do que dá para ADICIONAR agora, neste canal.

    Os mesmos portões do cardápio, e pela mesma razão que o carrinho já os
    usava: o trilho desenha um CTA ativo sem receber campo de disponibilidade,
    então sugerir esgotado vira convite que termina em 409. Aqui a
    disponibilidade é filtro de CANDIDATO, não estado a renderizar.
    """
    from shopman.offerman.models import Product

    from shopman.shop.projections import catalog_context
    from shopman.shop.projections.cart import _availability

    visible = catalog_context.visible_skus_in_channel(skus, channel_ref)
    listing_sellable = catalog_context.listing_sellable_map(skus, channel_ref)
    avail_map, _own = _availability(skus, "", channel_ref)

    products = {
        p.sku: p
        for p in Product.objects.filter(
            sku__in=skus, is_published=True, is_sellable=True,
        ).prefetch_related("keywords")
    }

    passing: dict[str, object] = {}
    for sku in skus:
        if visible is not None and sku not in visible:
            continue
        if not listing_sellable.get(sku, True):
            continue
        product = products.get(sku)
        if product is None:
            continue
        resolved = catalog_context.basic_availability(
            avail_map.get(sku),
            is_sellable=True,
            # O limiar só separa AVAILABLE de LOW_STOCK, e os dois são
            # adicionáveis — a pergunta aqui é só "dá para pôr na sacola?".
            low_stock_threshold=Decimal("0"),
        )
        if not resolved.can_add_to_cart:
            continue
        passing[sku] = product
    return passing


# --- pontuação -------------------------------------------------------------


def _score(
    products: dict,
    *,
    cart_skus: set[str],
    anchor_sku: str | None,
    rule: dict,
    context: dict,
    channel_ref: str,
) -> list[Suggestion]:
    from shopman.shop.services import attributes

    affinity_weight = float(rule.get("affinity_weight", 1) or 0)
    pairings = rule.get("pairings") or []

    cart_products = _cart_products(cart_skus)
    excluded = _context_exclusions(rule, context)

    prices = _listed_prices(list(products), channel_ref)
    cart_average = _cart_average(cart_skus, channel_ref)
    prefers_cheaper = rule.get("price") == "below_cart_average"

    # Uma leitura de atributo por definição, não por produto.
    everyone = list(products.values()) + cart_products
    values = {
        d.ref: attributes.get_many(everyone, d.ref)
        for d in attributes.for_purpose("rule")
    }

    affinity = _affinity_map(cart_skus, set(products))

    out: list[Suggestion] = []
    for sku, product in products.items():
        if _is_excluded(sku, excluded, values):
            continue

        reasons: list[str] = []
        score = 0.0

        lift, partner = affinity.get(sku, (0.0, None))
        if lift and affinity_weight:
            # Lift 1 é o acaso; o que pontua é o quanto ele passa disso.
            score += affinity_weight * max(0.0, lift - 1.0)
            reasons.append(f"affinity:{partner}")

        for pairing in pairings:
            reason = _pairing_reason(pairing, sku, cart_skus, values, product)
            if reason:
                score += float(pairing.get("weight", 1))
                reasons.append(reason)

        price_q = prices.get(sku)
        if prefers_cheaper and price_q is not None and cart_average and price_q < cart_average:
            score += 0.5
            reasons.append("price:below_cart_average")

        if not reasons:
            # Sem um motivo, não é sugestão — é um item aleatório do catálogo.
            continue

        out.append(Suggestion(
            sku=sku,
            name=getattr(product, "name", "") or "",
            unit_price_q=int(price_q or getattr(product, "base_price_q", 0) or 0),
            image_url=getattr(product, "image_url", None) or None,
            score=round(score, 4),
            reasons=tuple(reasons),
        ))

    # Empate desfeito pelo SKU, para a sugestão não dançar entre dois requests.
    out.sort(key=lambda s: (-s.score, s.sku))
    return out


def _pairing_reason(pairing, sku, cart_skus, values, product) -> str | None:
    """O código do motivo, se este pareamento casa; ``None`` se não casa.

    O motivo nomeia o valor que **de fato casou**, não o primeiro que a regra
    declarou. Com ``in: [acompanhamento, bebida]``, oferecer um café e explicar
    "→ acompanhamento" seria uma explicação errada — e explicação errada é pior
    que explicação nenhuma, porque o gestor ajusta a regra errada.
    """
    when = pairing.get("when") or {}
    suggest_side = pairing.get("suggest") or {}

    when_ref = when.get("attr")
    when_values = _side_values(when)
    if not when_ref:
        return None

    by_sku = values.get(when_ref) or {}
    matched_when = None
    for cart_sku in cart_skus:
        matched_when = _matched(by_sku.get(cart_sku), when_values)
        if matched_when is not None:
            break
    if matched_when is None:
        return None

    if "tag" in suggest_side:
        tag = str(suggest_side["tag"]).strip().lower()
        keywords = {k.lower() for k in product.keywords.names()}
        if tag not in keywords:
            return None
        return f"pairing:{when_ref}={matched_when}→tag:{tag}"

    suggest_ref = suggest_side.get("attr")
    if not suggest_ref:
        return None
    matched_suggest = _matched(
        (values.get(suggest_ref) or {}).get(sku), _side_values(suggest_side),
    )
    if matched_suggest is None:
        return None
    return f"pairing:{when_ref}={matched_when}→{suggest_ref}={matched_suggest}"


def _side_values(side: dict) -> tuple[str, ...]:
    if "in" in side:
        return tuple(str(v) for v in side["in"])
    if "value" in side:
        return (str(side["value"]),)
    return ()


def _matched(value, wanted: tuple[str, ...]) -> str | None:
    """O valor de ``wanted`` que ``value`` satisfaz, ou ``None``."""
    if value is None or not wanted:
        return None
    candidates = [str(v) for v in value] if isinstance(value, list) else [str(value)]
    for candidate in candidates:
        if candidate in wanted:
            return candidate
    return None


def _matches(value, wanted: tuple[str, ...]) -> bool:
    return _matched(value, wanted) is not None


def _context_exclusions(rule: dict, context: dict) -> list[dict]:
    """Cláusulas de exclusão que valem para ESTE contexto.

    A chave da regra casa com qualquer valor do contexto — ``{"delivery": ...}``
    vale quando o pedido é ``fulfillment="delivery"``.
    """
    clauses = rule.get("context") or {}
    active = {str(v) for v in context.values() if v}
    return [
        clause["exclude"]
        for name, clause in clauses.items()
        if name in active and isinstance(clause, dict) and "exclude" in clause
    ]


def _is_excluded(sku: str, excluded: list[dict], values: dict) -> bool:
    for clause in excluded:
        ref = clause.get("attr")
        if ref and _matches((values.get(ref) or {}).get(sku), _side_values(clause)):
            return True
    return False


def _affinity_map(cart_skus: set[str], candidate_skus: set[str]) -> dict:
    """``{sku: (melhor lift, parceiro)}`` — o par mais forte de cada candidato."""
    from shopman.shop.models import ProductAffinity

    if not (cart_skus and candidate_skus):
        return {}
    out: dict[str, tuple[float, str]] = {}
    rows = ProductAffinity.objects.filter(
        sku_a__in=cart_skus, sku_b__in=candidate_skus,
    ).order_by("-lift")
    for row in rows:
        # Ordenado por lift: o primeiro que aparece já é o mais forte.
        out.setdefault(row.sku_b, (row.lift, row.sku_a))
    return out


def _cart_products(cart_skus: set[str]) -> list:
    from shopman.offerman.models import Product

    if not cart_skus:
        return []
    return list(Product.objects.filter(sku__in=cart_skus))


def _listed_prices(skus: list[str], channel_ref: str) -> dict[str, int]:
    """Preço que o checkout cobraria, por SKU, neste canal."""
    from shopman.offerman.models import ListingItem

    if not skus:
        return {}
    prices: dict[str, int] = {}
    items = (
        ListingItem.objects.filter(
            listing__ref=channel_ref, listing__is_active=True,
            product__sku__in=skus, is_published=True,
        )
        .select_related("product")
        .order_by("-min_qty")
    )
    for item in items:
        # `-min_qty` primeiro; o último a escrever é o degrau de menor
        # quantidade, que é o preço de uma unidade.
        prices[item.product.sku] = int(item.price_q or 0)
    return prices


def _cart_average(cart_skus: set[str], channel_ref: str) -> int | None:
    from shopman.offerman.models import Product

    if not cart_skus:
        return None
    prices = _listed_prices(list(cart_skus), channel_ref)
    for product in Product.objects.filter(sku__in=cart_skus):
        prices.setdefault(product.sku, int(product.base_price_q or 0))
    values = [p for p in prices.values() if p]
    return sum(values) // len(values) if values else None


__all__ = ["COMPLEMENT", "SUBSTITUTE", "Suggestion", "suggest"]
