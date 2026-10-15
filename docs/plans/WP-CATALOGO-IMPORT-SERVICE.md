# WP-CATALOGO-IMPORT-SERVICE (pós-go-live)

Status: planejado. Não bloqueia o go-live.
Origem: decisão do dono em 14/10/2026, ao aceitar a mudança de Core da onda 1 do catálogo (#1786).

## Contexto

A onda 1 do cadastro turbo (#1786) entregou `POST catalog/product/import/` reusando o
`ProductResource` que o Admin já usava
(`packages/offerman/shopman/offerman/contrib/import_export/resources.py`), para não
haver duas verdades de import/upsert por SKU.

O framework (backstage) não pode importar `shopman.offerman.contrib.*`
(`shopman/shop/tests/test_import_boundaries.py`, `test_architecture.py`). O conserto
aceito foi expor o `ProductResource` na API pública do pacote (`shopman.offerman`),
com precedente em `get_social_attributes`/`set_social_attributes` (contrib.social) e
`find_substitutes`/`score_substitutes` (contrib.substitutes).

O dono aceitou o estado atual (necessidade medida mais o precedente) e pediu que o
refactor fique planejado, sem revisar os outros contribs pela metade.

## Objetivo

Import e upsert por SKU viram serviço público do Offerman, por exemplo
`CatalogService.import_products(...)`. O `ProductResource` vira adaptador fino sobre
esse serviço. O endpoint do backstage e o Admin consomem o MESMO serviço.

Entram na mesma revisão, pela régua da fronteira (API pública, não `contrib`):
`gtin_is_valid`, `get_social_attributes`/`set_social_attributes` e
`find_substitutes`/`score_substitutes`.

## Fora de escopo

- Mudar o comportamento do import de produto no Admin do catálogo ou no Compras.
- Migração de dados.
