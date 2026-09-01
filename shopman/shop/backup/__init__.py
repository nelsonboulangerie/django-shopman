"""Cofre de dados curados — export/import round-trip das entidades que não se reconstroem.

O banco transacional (pedidos, ledger de estoque, livro-caixa, pagamentos) tem o
backup do Postgres gerenciado como rede. O que NÃO tem rede é a curadoria feita à
mão: catálogo, receitas, fornecedores, regras, canais, copy, promoções, de-paras.
Este módulo dá a essa curadoria um caminho de ida e volta em planilha (XLSX/CSV),
legível e editável por gente — inclusive no Google Sheets.

Três peças:

- ``registry`` — cada app registra suas entidades exportáveis (nome, resource,
  tier de dependência). O shop registra as suas e as dos packages do Core; o
  backstage registra as dele no ``AppConfig.ready()`` (a direção de import é
  backstage → shop, nunca o contrário).
- ``resources`` — um ``ModelResource`` do django-import-export por entidade, com
  chave natural (``ref``/``sku``/``code``) como identidade de upsert. FKs e M2M
  atravessam a planilha pela chave natural, nunca por id de banco.
- ``workbook`` — leitura e escrita do arquivo: um XLSX com uma aba por entidade,
  ou um diretório de CSVs (melhor para diff em git).

Comandos: ``manage.py export_backup`` e ``manage.py import_backup`` (dry-run por
padrão; ``--apply`` escreve, tudo numa transação só). Guia:
``docs/guides/backup-and-restore.md``.
"""
