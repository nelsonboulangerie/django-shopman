"""A fundação de dados do B.I. em três camadas (BI-DATA-FOUNDATION-PLAN).

- ``ingest/``: uma fonte externa, um importador, uma tabela de aterrissagem,
  um lote por arquivo (``ImportBatch``). Validação de linha na fronteira.
- ``sources/`` + ``canonical.py`` (P1/P2): o contrato canônico e os
  adaptadores por fonte; de-paras vivem em tabela, nunca em código.
- A camada de leitura continua em ``projections/bi_*.py``: nada se move para
  cá — o pacote só recebe o que nasce novo.

Regra que separa as camadas: **fonte externa aterrissa; ledger nativo é lido
no lugar.** ``Order``, ``Move``, ``cashman.Entry`` nunca passam por aqui.
"""
