"""O preço que um canal de EXIBIÇÃO mostra — e de quem ele o pega emprestado.

Um canal `display` (TV na parede, feed do Google, catálogo da Meta) não vende, logo
não tem preço próprio: preço é propriedade de quem transaciona. Mas ele precisa
MOSTRAR um preço, e mostrar o errado tem consequência — no Brasil, publicidade
suficientemente precisa vincula o fornecedor.

Daí `config.display.prices_from`: o canal de exibição APONTA para um canal
transacional e mostra o preço dele. A TV do balcão aponta para o PDV, porque está
fisicamente na loja e tem de concordar com o que o caixa cobra. Os feeds de Google e
Meta apontam para a loja online, porque é lá que a pessoa que clicou vai comprar.

Antes disto os dois renderizadores liam `Product.base_price_q` direto — o preço
"de tabela", que não é o preço de nenhum canal em particular. Enquanto todos os
canais cobram igual, ninguém percebe; no dia em que o PDV tiver preço próprio, a TV
passa a anunciar um valor que o caixa não honra. Era mentira latente, e a ADR-018 §4
resolveu antes de virar mentira ativa.

Sem `ListingItem` para o produto no canal apontado, cai em `base_price_q` — e isso é
correto, não fallback preguiçoso: ausência de preço por canal significa "vale o de
tabela", que é a mesma resposta que o PDV daria.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class PriceSourceError(Exception):
    """O canal de exibição não tem fonte de preço utilizável."""


def price_source_ref(channel) -> str:
    """O ref do canal transacional de onde este canal de exibição tira preço."""
    display = (channel.config or {}).get("display") or {}
    return (display.get("prices_from") or "").strip()


def resolve_prices(channel, products) -> dict[str, int]:
    """``{sku: price_q}`` como o canal apontado por ``prices_from`` cobra.

    Uma consulta para todos os produtos, não uma por produto: o quadro da TV tem
    dezenas de itens e recarrega a cada evento de estoque.
    """
    skus = [p.sku for p in products]
    if not skus:
        return {}

    base = {p.sku: p.base_price_q for p in products}
    source = price_source_ref(channel)
    if not source:
        # O check W008 (`shop/checks.py`) avisa na subida; aqui a tela não pode
        # ficar em branco por causa de config faltando.
        logger.warning("display.no_price_source channel=%s", channel.ref)
        return base

    from shopman.offerman.models import ListingItem

    rows = (
        ListingItem.objects.filter(listing__ref=source, product__sku__in=skus)
        .values_list("product__sku", "price_q")
    )
    return {**base, **{sku: int(price_q) for sku, price_q in rows}}
