"""
Substitute product scoring — find replacement SKUs for an unavailable one.

The name is deliberate: this is a substitution system (produto X faltou,
aqui está o mais próximo), not a recommendation or cross-sell system.

## O que este módulo responde, e o que ele NÃO responde

Aqui mora a **similaridade de catálogo**: palavras-chave, coleção, preço de
tabela e gramatura. Disponibilidade, preço do canal e sabor **não** moram aqui —
são política do tenant e vivem em ``shopman.shop.services.substitutes.find``.
A divisão é de propósito: o Offerman sabe o que se parece com o quê; o
orquestrador sabe o que a casa pode oferecer agora.

Sem similaridade de nome: em catálogos com nomes muito prefixados ("Pão X",
"Pão Y"), ``SequenceMatcher`` infla score de produtos não relacionados e
penaliza substitutos legítimos com nomes distintos.

## Refino de 04/09/2026 (aprovado pelo dono)

Três defeitos medidos, três correções:

- **Palavra-chave era pré-requisito.** ``if not product_keywords: return []``
  fazia todo produto sem tag não ter substituto nenhum — e tag é dado que
  alguém precisa cadastrar. Agora a **coleção sozinha gera candidatos**.
- **Coleção era filtro duro.** ``same_collection=True`` tornava impossível
  sugerir de fora, mesmo quando dentro não havia nada. Agora ela é
  **preferência**: pontua alto (o de dentro ganha no empate e quase sempre no
  geral), e o de fora entra como reserva em vez de não existir.
- **Gramatura era ignorada.** Trocar um pão de 150 g por um de 800 g é
  tecnicamente um substituto e praticamente um problema. A **distância relativa
  de peso** entra na pontuação: o mais próximo ganha.

E uma adição: ``score_substitutes`` devolve pontuação e motivos, para quem
precisa explicar a escolha. ``find_substitutes`` mantém a assinatura e o tipo de
retorno que os consumidores já esperam.
"""

from dataclasses import dataclass
from decimal import Decimal

from shopman.offerman.models import Product
from shopman.offerman.service import CatalogService

#: Pesos da pontuação. Explícitos porque são regra de negócio, não constante
#: mágica: quem discordar tem de conseguir apontar a linha.
KEYWORD_POINTS = 3      # por palavra-chave em comum
COLLECTION_POINTS = 2   # mesma coleção primária
PRICE_POINTS = 1        # dentro da faixa de preço
WEIGHT_POINTS = 2       # gramatura idêntica; decai com a distância relativa

PRICE_BAND = Decimal("0.3")  # ±30% do preço de referência


@dataclass(frozen=True)
class ScoredSubstitute:
    """Um candidato, sua pontuação e **por que** ele pontuou."""

    product: Product
    score: float
    #: Códigos legíveis: ``("keyword:centeio", "same_collection", "weight:~150g")``.
    reasons: tuple[str, ...]


def _get_primary_collection(product: Product):
    """Get the primary collection for a product."""
    primary_item = product.collection_items.filter(is_primary=True).first()
    return primary_item.collection if primary_item else None


def _weight_closeness(reference: int | None, candidate: int | None) -> float:
    """1.0 para peso idêntico, 0.0 para o dobro (ou mais) de diferença.

    Relativo, não absoluto: 50 g de diferença é muito entre dois pãezinhos de
    80 g e é irrelevante entre dois pães de 1 kg.
    """
    if not reference or not candidate:
        return 0.0
    return max(0.0, 1.0 - abs(reference - candidate) / max(reference, candidate))


def _score_candidates(
    candidates: list[Product],
    product: Product,
    product_keywords: list[str],
    primary_collection,
) -> list[ScoredSubstitute]:
    """
    Pontua e ordena os candidatos.

    Pontuação (palavra-chave domina; coleção reforça; peso aproxima; preço
    finaliza):

        - Palavras-chave em comum:      3 pontos cada
        - Mesma coleção da referência:  2 pontos
        - Gramatura próxima:            até 2 pontos, por distância relativa
        - Preço ±30% da referência:     1 ponto
    """
    price_low = int(product.base_price_q * (1 - PRICE_BAND))
    price_high = int(product.base_price_q * (1 + PRICE_BAND))

    collection_product_ids = set()
    if primary_collection:
        collection_product_ids = set(
            primary_collection.items.values_list("product_id", flat=True)
        )

    reference_keywords = set(product_keywords)
    scored: list[ScoredSubstitute] = []

    for candidate in candidates:
        score = 0.0
        reasons: list[str] = []

        common = sorted(reference_keywords & set(candidate.keywords.names()))
        if common:
            score += len(common) * KEYWORD_POINTS
            reasons.extend(f"keyword:{k}" for k in common)

        if primary_collection and candidate.pk in collection_product_ids:
            score += COLLECTION_POINTS
            reasons.append("same_collection")

        closeness = _weight_closeness(product.unit_weight_g, candidate.unit_weight_g)
        if closeness:
            score += WEIGHT_POINTS * closeness
            reasons.append(f"weight:~{candidate.unit_weight_g}g")

        if price_low <= candidate.base_price_q <= price_high:
            score += PRICE_POINTS
            reasons.append("price_band")

        scored.append(ScoredSubstitute(
            product=candidate, score=round(score, 4), reasons=tuple(reasons),
        ))

    # Empate desfeito pelo SKU: sem isso a ordem depende do plano de query e a
    # mesma pergunta devolve respostas diferentes entre dois requests.
    scored.sort(key=lambda s: (-s.score, s.product.sku))
    return scored


def score_substitutes(
    sku: str,
    limit: int = 5,
    *,
    same_collection: bool = True,
) -> list[ScoredSubstitute]:
    """Substitutos com pontuação e motivos — a irmã explicativa de ``find_substitutes``.

    ``same_collection`` é **preferência, não filtro**: quando ``True``, estar na
    mesma coleção vale pontos e o de dentro tende a ganhar; o de fora continua
    elegível, como reserva. Quando ``False``, a coleção não pontua.
    """
    product = CatalogService.get(sku)
    if not product:
        return []

    product_keywords = list(product.keywords.names())
    primary_collection = _get_primary_collection(product)

    # Duas portas de entrada, unidas: palavra-chave em comum OU mesma coleção.
    # Antes só a primeira existia, e produto sem tag não tinha substituto.
    candidate_ids: set[int] = set()
    if product_keywords:
        candidate_ids |= set(
            Product.objects.filter(
                is_published=True, is_sellable=True, keywords__name__in=product_keywords,
            )
            .exclude(sku=sku)
            .values_list("pk", flat=True)[: limit * 6]
        )
    if primary_collection:
        candidate_ids |= set(
            Product.objects.filter(
                is_published=True, is_sellable=True,
                collection_items__collection=primary_collection,
            )
            .exclude(sku=sku)
            .values_list("pk", flat=True)[: limit * 6]
        )

    if not candidate_ids:
        return []

    candidates = list(
        Product.objects.filter(pk__in=candidate_ids).prefetch_related("keywords")
    )
    scored = _score_candidates(
        candidates,
        product,
        product_keywords,
        primary_collection if same_collection else None,
    )
    return scored[:limit]


def find_substitutes(
    sku: str,
    limit: int = 5,
    same_collection: bool = True,
) -> list[Product]:
    """Find substitute products for a given SKU.

    Assinatura e tipo de retorno preservados — quem só quer a lista de produtos
    (o estoque, a modal de erro) não muda uma linha. Para saber **por que** cada
    um está ali, use :func:`score_substitutes`.
    """
    return [
        s.product
        for s in score_substitutes(sku, limit, same_collection=same_collection)
    ]
