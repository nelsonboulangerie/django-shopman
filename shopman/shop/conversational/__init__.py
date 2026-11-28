"""O adaptador do Shopman para o framework de comércio conversacional (ADR-049).

As portas de negócio genéricas do Shopman, que qualquer superfície conversacional usa:
comércio (leitura no N4, execução no N6), armazenamento, relógio e resultados (N8). O que
é da Nice e do canal dela (canal, modelo, perfil, sombra) mora em
``shopman/storefront/concierge/``. ``storefront`` importa ``shop``, nunca o contrário: por
isso quem diz de quem é o carrinho, o cliente e o pedido entra aqui pelo construtor
(``Ownership``), e não por import.

Plano: ``docs/plans/COMERCIO-CONVERSACIONAL-ADAPTADOR-NICE-PLANO.md`` (seções 1 e 7).
"""

from .commerce_read import DenyAll, Ownership, ShopmanCommerceRead

__all__ = ["DenyAll", "Ownership", "ShopmanCommerceRead"]
