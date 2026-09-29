# CATALOG-SYNC-EXTERNO-PLAN — Sincronização com catálogos externos

> Sincronizar o catálogo da Nelson para **Google Merchant Center**, **Meta
> (Instagram/Facebook) Shopping** e **WhatsApp Catalog**. Frente **v1** (🆕,
> Onda 1 · canais externos) do [PRODUCT-V1-SCOPE-BACKLOG](PRODUCT-V1-SCOPE-BACKLOG.md).

**Status**: 🟡 Revalidado em 2026-09-29. Feed pull Google/Meta e push Meta estão
implementados; ativação externa continua bloqueada por contas/credenciais. Push
Google não é lacuna de go-live enquanto o feed agendado atender a operação.

---

## Achado-chave: a fundação já existe

A pesquisa reversa mostrou que o projeto **já tem o padrão de projeção de
catálogo** e que parte relevante dos canais novos foi entregue. Reusar, não
reinventar:

- **Protocolo** `CatalogProjectionBackend` (`project()` + `retract()`):
  [`packages/offerman/shopman/offerman/protocols/projection.py`](../../packages/offerman/shopman/offerman/protocols/projection.py).
- **Padrão-ouro** já implementado: o adapter iFood
  [`shopman/shop/adapters/catalog_projection_ifood.py`](../../shopman/shop/adapters/catalog_projection_ifood.py)
  (project/retract + rate-limit) + management command `sync_catalog_ifood`.
- **Payload neutro** pronto: `catalog_exports.build_catalog_export()`
  ([`shopman/shop/services/catalog_exports.py`](../../shopman/shop/services/catalog_exports.py))
  e `ProjectedItem` (sku, name, description, price_q, image_url, category,
  keywords, metadata).
- **Categorias** hierárquicas (`Collection`/`CollectionItem`, `is_primary`) →
  mapeáveis para `google_product_category`.
- **API REST** de catálogo (produtos/coleções/preços) já existe.

## Estado real revalidado

1. ✅ **Atributos comerciais**: brand, GTIN, MPN, condition e
   google_product_category vivem no schema tipado de `metadata.social`, com
   formulário Admin e validação. Não é necessária migração do Core.
2. ✅ **Feed pull Google e Meta**: `GET /feed/<ref>.xml` publica RSS compatível,
   com enum de disponibilidade específico por plataforma, preço do canal,
   landing page da loja e falha fechada quando a base pública não existe.
3. ✅ **Push Meta**: `MetaCatalogProjection`, `sync_catalog_meta`, batching,
   retract reversível, rate limit, dry-run e testes existem. O registro é off por
   padrão e só entra com `META_CATALOG_PROJECTION=1`.
4. ✅ **Disponibilidade**: feed e projeção derivam publicação/venda/pausa; o
   registry canônico permite o auto-trigger já usado pelos canais externos.
5. ⏳ **Ativação Meta/WhatsApp**: depende de token, Catalog ID e vínculo real do
   catálogo ao número/contas Meta. Não criar adapter WhatsApp paralelo antes de
   confirmar esse vínculo, pois o catálogo Meta é a fonte compartilhada prevista.
6. ⏳ **Google**: o feed pull está pronto. Push pela Merchant API permanece uma
   melhoria de latência pós-gate, não um requisito técnico de go-live.
7. ⏳ **Imagens públicas**: itens sem imagem são omitidos e URLs precisam seguir
   estáveis/publicamente acessíveis. Validar isso na conta externa; migrar mídia
   para storage próprio somente se a QA comprovar instabilidade.

---

## Arquitetura vigente

- **Google v1**: feed pull público, configurado no Merchant Center por busca
  agendada. Não exige token de escrita.
- **Meta v1**: o mesmo feed pull, com opção de push near-real-time por
  `MetaCatalogProjection` quando o ambiente habilitar o registry.
- **WhatsApp Catalog**: deve vincular o catálogo Meta existente. Um adapter
  separado só é justificável se a homologação mostrar uma API ou identidade de
  catálogo distinta.
- **Google push futuro**: usar Merchant API, sucessora da Content API citada na
  versão antiga deste plano, e somente depois de medir que a cadência do pull é
  insuficiente.

## Arcos

- ✅ **Arc 1 · Atributos de feed**: entregue em `metadata.social` e Admin.
- ✅ **Arc 2 · Feed pull Google/Meta**: entregue e coberto por testes.
- ✅ **Arc 3 · Push Meta**: adapter, comando e testes entregues; ativação externa
  permanece desligada por padrão.
- ⏳ **Arc 4 · Homologação Meta + vínculo WhatsApp**: gate externo.
- 📋 **Arc 5 · Push Google Merchant**: backlog condicionado a necessidade de
  latência; não executar como dívida automática.

## Invariantes

- **Core sagrado**: preferir dataclass em `metadata` a migração no `Product`.
  Se campo estrutural/queryable for inevitável (GTIN para busca), discutir antes.
- Reusar `CatalogProjectionBackend` + `catalog_exports` — não criar fluxo paralelo.
- Adapters swappable por config (padrão do projeto).

## Gates externos / do dono

- Cadastrar as URLs pull no Google Merchant Center e Meta Commerce Manager.
- Para push Meta: fornecer Catalog ID, System User token, URL pública da loja e
  habilitar `META_CATALOG_PROJECTION` somente após dry-run/canário.
- Vincular e verificar o número WhatsApp Business no catálogo Meta escolhido.
- Confirmar na QA externa que as imagens usadas pelos SKUs publicados têm URL
  estável. Se não tiverem, decidir storage próprio.
- GTIN ausente não deve ser inventado: o feed já omite identificador quando não
  há evidência. A política por SKU continua sendo decisão de cadastro, não do
  adapter.

## Referências

- [PRODUCT-V1-SCOPE-BACKLOG](PRODUCT-V1-SCOPE-BACKLOG.md)
- [CATALOG-FEEDS-GOOGLE-META](CATALOG-FEEDS-GOOGLE-META.md)
- `catalog_projection_ifood.py` (padrão) · `catalog_exports.py` · `protocols/projection.py`
- `catalog_projection_meta.py` · `sync_catalog_meta` · `views/product_feed.py`
- `packages/offerman/shopman/offerman/models/{product,collection}.py`
