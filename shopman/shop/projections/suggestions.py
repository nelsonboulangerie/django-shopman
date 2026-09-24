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
3. **Portões** — visível no canal, vendável, disponível agora, fora da sacola,
   e **de outra função** que a da sacola. Sugestão que não passa nos portões
   não existe.

⚠️ **Adicional é complemento, não substituto** (dono, 23/09). A sacola com
Croque Madame recebeu Croque Monsieur: mesmo prato, mesma coleção, mais barato e
com lift alto no histórico (quem pede um croque para a mesa pede o outro). Nada
no motor dizia que "outro do mesmo" não é adicional. Agora há dois portões para
isso — uma coleção em comum (a categoria do Offerman) e ``distinct_from_cart``
(os atributos que definem a função, ``natureza`` + ``sabor`` por default) — e
uma ordem: **o pareamento é a regra da casa**; a afinidade ordena dentro dele e
só fala sozinha quando nenhum pareamento casa.

⚠️ **O histórico desempata, não decide** (dono, 23/09: preferências "não devem
excluir cruzamentos diferentes", e o sistema não pode ser "desumano ou
engessado"). Pareamento pesa em inteiros; histórico e preço somam juntos menos
de 1 (``AFFINITY_TIEBREAK`` + ``PRICE_TIEBREAK``), então escolhem entre as
bebidas geladas qual oferecer, mas nunca trocam a gelada pela quente que o
salgado não pede. ``one_per_cart`` é o portão de "bebida com bebida, não". O
estresse contra o cardápio inteiro, com nota de atendente por sacola, mora em
``shop/tests/test_suggestion_stress.py``.

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

#: Teto do que o histórico (lift) soma, e do que "mais barato" soma. Juntos
#: ficam abaixo de 1, o menor degrau entre dois pesos de pareamento: histórico e
#: preço desempatam DENTRO de uma preferência e nunca a invertem.
AFFINITY_TIEBREAK = 0.6
PRICE_TIEBREAK = 0.3


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

    ⚠️ As duas filas são independentes. Antes, o pareamento só ganhava a vaga
    que a afinidade deixasse, e em ordem alfabética de SKU: um item com 40
    parceiros no histórico (o Croque Madame) nunca via uma bebida que não
    tivesse sido comprada junto com ele — o pareamento "comida → bebida" ficava
    escrito e sem ninguém para avaliar.
    """
    candidates: dict[str, dict] = {}

    for sku, lift, partner in _affinity_partners(cart_skus):
        entry = candidates.setdefault(sku, {"affinity": 0.0, "reasons": []})
        if lift > entry["affinity"]:
            entry["affinity"] = lift
            entry["reasons"] = [f"affinity:{partner}"]

    if rule.get("pairings"):
        for sku in _pairing_pool(cart_skus, rule):
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


def _pairing_pool(cart_skus: set[str], rule: dict) -> list[str]:
    """Os SKUs vendáveis que algum pareamento da regra de fato casa.

    O catálogo inteiro é avaliado (são centenas de linhas, não milhares) e só
    quem casa entra; a fila fica com os ``CANDIDATE_POOL`` de maior peso. É o
    que garante que "comida → bebida" encontre a bebida, em vez de depender de
    ela cair entre os primeiros SKUs do alfabeto.
    """
    from shopman.offerman.models import Product

    from shopman.shop.services import attributes

    pairings = rule.get("pairings") or []
    if not (pairings and cart_skus):
        return []

    products = list(
        Product.objects.filter(is_published=True, is_sellable=True)
        .exclude(sku__in=cart_skus)
        .prefetch_related("keywords")
    )
    everyone = products + _cart_products(cart_skus)
    values = {
        d.ref: attributes.get_many(everyone, d.ref)
        for d in attributes.for_purpose("rule")
    }

    weighted: list[tuple[float, str]] = []
    for product in products:
        weight = sum(
            float(p.get("weight", 1))
            for p in pairings
            if _pairing_reason(p, product.sku, cart_skus, values, product)
        )
        if weight > 0:
            weighted.append((weight, product.sku))
    weighted.sort(key=lambda w: (-w[0], w[1]))
    return [sku for _, sku in weighted[:CANDIDATE_POOL]]


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
    distinct_refs = list(rule.get("distinct_from_cart") or [])
    for ref in distinct_refs:
        # A validação garante que o atributo existe; ele só pode não servir a
        # "rule" — e ler assim mesmo é melhor que o portão se calar.
        if ref not in values:
            values[ref] = attributes.get_many(everyone, ref)

    one_per_cart = rule.get("one_per_cart") or []
    for condition in _conditions(one_per_cart):
        ref = condition.get("attr")
        if ref and ref not in values:
            values[ref] = attributes.get_many(everyone, ref)

    affinity = _affinity_map(cart_skus, set(products))
    same_role = _same_role_as_cart(set(products), cart_skus, distinct_refs, values)

    ranked: list[tuple[bool, Suggestion]] = []
    for sku, product in products.items():
        if sku in same_role:
            continue
        if _already_has_one(sku, cart_skus, one_per_cart, values):
            continue
        if _is_excluded(sku, excluded, values):
            continue

        reasons: list[str] = []
        score = 0.0

        lift, partner = affinity.get(sku, (0.0, None))
        if lift > 1.0 and affinity_weight:
            # O histórico DESEMPATA, não decide (dono, 23/09): a contribuição
            # é limitada abaixo do menor degrau de peso de um pareamento, então
            # nenhum lift passa por cima de uma preferência declarada. Lift 1 é
            # o acaso; 1 − 1/lift cresce com ele e nunca chega a 1.
            score += AFFINITY_TIEBREAK * (1.0 - 1.0 / lift)
            reasons.append(f"affinity:{partner}")

        paired = False
        for pairing in pairings:
            reason = _pairing_reason(pairing, sku, cart_skus, values, product)
            if reason:
                score += float(pairing.get("weight", 1))
                reasons.append(reason)
                paired = True

        if not reasons:
            # Sem um motivo, não é sugestão — é um item aleatório do catálogo.
            # Preço não é motivo: "é mais barato" sozinho fazia de qualquer
            # item da casa uma sugestão (foi uma das portas do Croque Monsieur).
            continue

        price_q = prices.get(sku)
        if prefers_cheaper and price_q is not None and cart_average and price_q < cart_average:
            score += PRICE_TIEBREAK
            reasons.append("price:below_cart_average")

        ranked.append((paired, Suggestion(
            sku=sku,
            name=getattr(product, "name", "") or "",
            unit_price_q=int(price_q or getattr(product, "base_price_q", 0) or 0),
            image_url=getattr(product, "image_url", None) or None,
            score=round(score, 4),
            reasons=tuple(reasons),
        )))

    # O pareamento é a regra da casa e vem primeiro; a afinidade ordena dentro
    # dele, e só fala sozinha quando nenhum pareamento casa. Sem esta ordem, um
    # lift alto (quem pede um croque pede o outro para a mesa) passava por cima
    # de "comida pede bebida" — e o histórico de mesa não é o que combina.
    # Empate desfeito pelo SKU, para a sugestão não dançar entre dois requests.
    ranked.sort(key=lambda r: (not r[0], -r[1].score, r[1].sku))
    return [suggestion for _, suggestion in ranked]


def _pairing_reason(pairing, sku, cart_skus, values, product) -> str | None:
    """O código do motivo, se este pareamento casa; ``None`` se não casa.

    ``when`` fala da SACOLA: cada condição tem de ser satisfeita por algum item
    dela (``[sabor=salgado, natureza=bebida]`` = "tem salgado E tem bebida",
    em itens diferentes ou no mesmo). ``when_absent`` também fala da sacola:
    nenhum item pode satisfazer nenhuma daquelas condições ("ainda não tem
    bebida"). ``suggest`` fala do CANDIDATO: ele tem de satisfazer todas.

    O motivo nomeia o valor que **de fato casou**, não o primeiro que a regra
    declarou. Com ``in: [acompanhamento, bebida]``, oferecer um café e explicar
    "→ acompanhamento" seria uma explicação errada — e explicação errada é pior
    que explicação nenhuma, porque o gestor ajusta a regra errada.
    """
    when_parts: list[str] = []
    for condition in _conditions(pairing.get("when")):
        ref = condition.get("attr")
        if not ref:
            return None
        wanted = _side_values(condition)
        by_sku = values.get(ref) or {}
        hit = None
        for cart_sku in sorted(cart_skus):
            hit = _matched(by_sku.get(cart_sku), wanted)
            if hit is not None:
                break
        if hit is None:
            return None
        when_parts.append(f"{ref}={hit}")
    if not when_parts:
        return None

    for condition in _conditions(pairing.get("when_absent")):
        by_sku = values.get(condition.get("attr")) or {}
        wanted = _side_values(condition)
        if any(_matches(by_sku.get(cart_sku), wanted) for cart_sku in cart_skus):
            return None

    suggest_parts: list[str] = []
    for condition in _conditions(pairing.get("suggest")):
        if "tag" in condition:
            tag = str(condition["tag"]).strip().lower()
            keywords = {k.lower() for k in product.keywords.names()}
            if tag not in keywords:
                return None
            suggest_parts.append(f"tag:{tag}")
            continue
        ref = condition.get("attr")
        if not ref:
            return None
        hit = _matched((values.get(ref) or {}).get(sku), _side_values(condition))
        if hit is None:
            return None
        suggest_parts.append(f"{ref}={hit}")
    if not suggest_parts:
        return None

    return f"pairing:{'+'.join(when_parts)}→{'+'.join(suggest_parts)}"


def _conditions(side) -> list[dict]:
    """Um lado do pareamento como lista de condições (objeto ou lista deles)."""
    if not side:
        return []
    if isinstance(side, dict):
        return [side]
    return [c for c in side if isinstance(c, dict)]


def _already_has_one(sku: str, cart_skus: set[str], one_per_cart: list, values: dict) -> bool:
    """O candidato cai numa classe de que a sacola já tem um (``one_per_cart``).

    "Bebida com bebida, acho que não" (dono, 23/09): com um café na sacola, o
    adicional não é outra bebida — é a comida que ainda falta.
    """
    for condition in _conditions(one_per_cart):
        by_sku = values.get(condition.get("attr")) or {}
        wanted = _side_values(condition)
        if _matches(by_sku.get(sku), wanted) and any(
            _matches(by_sku.get(c), wanted) for c in cart_skus
        ):
            return True
    return False


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


def _same_role_as_cart(
    candidate_skus: set[str], cart_skus: set[str], distinct_refs: list, values: dict,
) -> set[str]:
    """Os candidatos que fazem o MESMO papel de algo que já está na sacola.

    Adicional é complemento, não substituto: outro croque para quem leva um
    croque é a pergunta "quer trocar?", não "quer junto?". Dois critérios, e
    basta um:

    - **uma coleção em comum** — a categoria que o Offerman já guarda, primária
      ou secundária (o Pain au Chocolat é Folhados e Doces). Salgado com
      salgado, folhado com folhado, doce com doce;
    - **mesmos valores em todos os ``distinct_from_cart``** da regra (default
      ``natureza`` + ``sabor``): pão rústico e pão macio moram em coleções
      diferentes e são o mesmo papel na mesa.

    ⚠️ Dado que falta nunca exclui: só compara atributos quando os dois lados
    têm todos preenchidos. Atributo em branco é ausência de dado, não igualdade.
    """
    if not (candidate_skus and cart_skus):
        return set()

    collections = _collections(candidate_skus | cart_skus)
    cart_collections: set[str] = set()
    for cart_sku in cart_skus:
        cart_collections |= collections.get(cart_sku, set())

    def signature(sku):
        sig = tuple((values.get(ref) or {}).get(sku) for ref in distinct_refs)
        if not sig or any(v is None or v == [] for v in sig):
            return None
        return tuple(tuple(sorted(map(str, v))) if isinstance(v, list) else str(v) for v in sig)

    cart_signatures = {sig for sig in map(signature, cart_skus) if sig is not None}

    out: set[str] = set()
    for sku in candidate_skus:
        if collections.get(sku, set()) & cart_collections:
            out.add(sku)
            continue
        sig = signature(sku)
        if sig is not None and sig in cart_signatures:
            out.add(sku)
    return out


def _collections(skus: set[str]) -> dict[str, set[str]]:
    """``{sku: {refs das coleções}}`` — primária e secundárias.

    As secundárias contam: o Pain au Chocolat mora em Folhados e TAMBÉM é Doces
    (regra do dono, 02/09). Com ele na sacola, a madeleine é outro doce.
    """
    from shopman.offerman.models import CollectionItem

    out: dict[str, set[str]] = {}
    rows = CollectionItem.objects.filter(product__sku__in=skus).values_list(
        "product__sku", "collection__ref",
    )
    for sku, ref in rows:
        out.setdefault(sku, set()).add(ref)
    return out


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
