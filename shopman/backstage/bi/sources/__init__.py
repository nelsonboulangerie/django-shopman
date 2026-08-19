"""Adaptadores por fonte: cada um traduz UMA tabela para o contrato canônico.

- ``orderman``: o pedido nativo (``Order``/``OrderItem``) — ledger da operação,
  lido no lugar, nunca copiado.
- ``historical``: o histórico externo aterrissado (``HistoricalSale``/``Item``),
  seja qual for a origem carimbada na linha (yooga, seed…), com os de-paras
  confirmados aplicados nas linhas.

Regra que os separa: fonte externa aterrissa (P0) e é traduzida aqui; ledger
nativo é lido no lugar. Fonte nova = tabela + importador + um módulo aqui.
"""
