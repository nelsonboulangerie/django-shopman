"""A base de clientes viva e o limiar de cerimônia que sai dela.

O limiar de cerimônia do Marketing não é mais um número no código: é uma proporção da
base de clientes, ou o teto de gasto do disparo — o que chegar primeiro (política em
``shopman/shop/marketing_policy.py``, decisão em ADR-032). Este módulo é o único lugar
que sabe **o que é a base**:

> **Base de clientes = o cadastro ativo da casa** — ``Customer`` com ``is_active=True``,
> um por pessoa conhecida, já sem quem pediu para ser esquecido (a anonimização do
> guestman é exatamente o que desliga esse campo).

Duas coisas que essa frase NÃO diz, e que importam:

- **não é o público alcançável.** Quem pode receber uma mensagem é sempre menos: precisa
  de telefone, consentimento verificado e maioridade declarada. O alcançável é o
  numerador (quantas pessoas o disparo atinge); a base é o denominador (o tamanho da
  casa). Misturar os dois faria "2% da base" significar "2% de quem eu já consigo
  alcançar", que encolhe junto com o disparo e nunca morde.
- **não inclui o histórico do Yooga.** ``shopman/backstage/bi/ingest/yooga.py`` escreve
  ``HistoricalSale``/``HistoricalSaleItem``, guarda ``customer_external_id`` e o hash do
  telefone, e **não cria ``Customer``**. O join por ``phone_hash`` está previsto no
  docstring daquele módulo e não existe em código. Enquanto não existir, quem só comprou
  no sistema antigo não conta aqui — e o Admin diz isso na tela, para o número não
  parecer um erro.

**Sem cache longo, de propósito.** Cache de regra de uma hora já mordeu esta casa. Aqui
o cache dura 60 segundos (o mesmo do ``Shop.load()``, que carrega a política ao lado) e
tem invalidação explícita: o Admin chama ``invalidate_customer_base_size()`` antes de
mostrar o número vivo, para o gestor nunca conferir um limiar contra uma base velha.
"""

from __future__ import annotations

import logging

from django.core.cache import cache
from django.db import DatabaseError

from shopman.shop.marketing_policy import CeremonyThreshold, MarketingPolicy

logger = logging.getLogger(__name__)

CUSTOMER_BASE_CACHE_KEY = "shopman:marketing:ceremony:customer_base"
#: 60 s. Curto porque o limiar decide se a tela pede senha, e uma base velha empurraria
#: essa decisão para o lado errado sem ninguém ver. Longo o bastante para que a projeção
#: do cockpit — que resolve seis ações por anúncio — não faça um COUNT por ação.
CUSTOMER_BASE_CACHE_TTL = 60


def customer_base_size(*, refresh: bool = False) -> int:
    """Quantas pessoas a casa tem no cadastro ativo.

    Falha FECHADO: se o banco não responde, devolve ``0``, e zero leva o limiar ao piso
    — mais cerimônia, nunca menos. Nenhuma conta aqui divide pela base.
    """
    if not refresh:
        cached = cache.get(CUSTOMER_BASE_CACHE_KEY)
        if cached is not None:
            return int(cached)
    from shopman.guestman.models import Customer

    try:
        total = int(Customer.objects.filter(is_active=True).count())
    except DatabaseError:
        logger.warning("marketing_ceremony.customer_base_unavailable", exc_info=True)
        return 0
    cache.set(CUSTOMER_BASE_CACHE_KEY, total, CUSTOMER_BASE_CACHE_TTL)
    return total


def invalidate_customer_base_size() -> None:
    """Esquece a contagem cacheada. O Admin chama antes de mostrar o número vivo."""
    cache.delete(CUSTOMER_BASE_CACHE_KEY)


def ceremony_threshold(
    *,
    base_size: int | None = None,
    policy: MarketingPolicy | None = None,
) -> CeremonyThreshold:
    """Limiar de cerimônia efetivo, em pessoas: política da loja × base viva."""
    from shopman.shop.marketing_policy import resolve_marketing_policy

    resolved = policy if policy is not None else resolve_marketing_policy()
    size = customer_base_size() if base_size is None else int(base_size)
    return resolved.ceremony_threshold(size)
