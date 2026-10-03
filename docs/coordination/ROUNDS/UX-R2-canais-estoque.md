# UX-R2 — iFood, Meta e Google respeitam o estoque

- **id:** UX-R2
- **sessão:** reforma SUITE-UX, onda 1 (Claude; executor em worktree próprio)
- **branch:** claude/ux-r2-canais-estoque
- **PR:** #1404
- **estado final:** na fila #1404 (auto-merge pedido)
- **início / fim:** 2026-10-03

## Objetivo
Plano `docs/plans/SUITE-UX-FUNCTION-PLAN.md` §5.1, linha "canais externos respeitam o estoque"
(decisão do dono em 03/10): a projeção de catálogo do iFood e o feed Meta/Google passam a mandar
indisponível quando o vendável zera e disponível quando volta, com a mesma regra de estoque do site.
A pausa manual continua e vence.

## O que mudou
- `shopman/shop/services/external_availability.py` (novo): a resposta única dos canais de fora.
  A regra é a do **portão de pedido** (`availability.decide` com uma unidade), a mesma que recusa
  o pedido quando ele chega: produto sem rastreio de estoque e `demand_ok` seguem disponíveis,
  fornada planejada aceita por `planned_ok` conta, kit limitado pelo componente. Só a falta
  (`insufficient_supply`) derruba; pausa e ausência na listagem seguem com as flags de antes.
  Leitura que falha responde "tem estoque". Canal de exibição lê o estoque do `display.prices_from`.
- iFood (`adapters/catalog_projection_ifood.py`): o upsert sai `UNAVAILABLE` sem estoque e
  `AVAILABLE` quando volta. Vale para a diretiva e para `sync_catalog_ifood` (que também mostra
  isso no `--dry-run`).
- Catálogo da Meta empurrado (`adapters/catalog_projection_meta.py`): `out of stock` / `in stock`
  pela mesma regra (`sync_catalog_meta --dry-run` também).
- Feed público Google/Meta (`views/product_feed.py`): `out_of_stock` / `out of stock` calculado na
  hora da leitura.
- Gatilho: `backstage/services/shelf_outages._apply` (passagem por zero e volta, por evento de
  Move/Hold depois do commit e pela reconciliação do `maintenance_worker`) chama
  `external_availability.on_offer_changed`, que enfileira `catalog.project_sku`
  (`trigger="stock_changed"`, ADR-003) para os canais empurrados cujo estoque vem daquele canal, na
  mesma transação do período. A diretiva na fila absorve a seguinte, e o handler lê o estado na hora.
  A reconciliação isola falha por SKU.
- Doc: seção "Estoque" em `docs/reference/ifood-catalog-write-policy.md`. Nenhuma chave nova em
  JSONField, nenhuma migração.

## Prova
- `shopman/shop/tests/test_external_availability.py`: 21 testes (zera → indisponível no iFood, na
  Meta e no feed; volta → disponível; sem rastreio → disponível; pausado com estoque → indisponível;
  pausa local do feed vence; idempotência e junção do disparo; receiver depois do commit;
  reconciliação; sem backend, nenhuma diretiva). Contra o main sem a mudança: `7 failed, 13 passed`.
- Suítes relacionadas + trava de vocabulário: `2446 passed, 4 skipped`.
- Recorte amplo (`shop`, `storefront`, `backstage` com `-k "ifood or feed or catalog or outage or
  projection or stock or availability or display"`): `3547 passed, 20 skipped`.
- `ruff check` nos arquivos tocados: `All checks passed!`

## O que ficou de fora
- No deploy de hoje, `IFOOD_CATALOG_PROJECTION`/`META_CATALOG_PROJECTION` não estão ligados nos
  specs `.do/`, e a escrita do catálogo iFood segue bloqueada pela política de teste. O efeito vivo
  imediato é o **feed** Google/Meta; o iFood e o catálogo Meta passam a respeitar o estoque quando
  esses envios forem ligados.
- Regra `require_stock` (opt-in por plataforma em `social_publish`, desligada por padrão): com ela
  ligada, o handler segura o upsert sem estoque como "pendente" e não manda o `UNAVAILABLE`. Não
  mexi: é uma regra de publicação à parte, e nenhum canal a usa hoje.
- Kit (bundle): o evento de estoque observa o SKU do componente, então a virada do kit chega pela
  reconciliação periódica, não na hora.

## Perguntas ao dono
nada
