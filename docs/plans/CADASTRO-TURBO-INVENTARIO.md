# Cadastro turbo nos apps Nuxt — inventário e proposta (§7.2)

> Frente §7.2 do COORDENACAO-GO-LIVE.md. **Só inventário e proposta**: nenhum código de app, nenhum modelo alterado.
> Base: origin/main 0e9acc7e3. Fontes: admin registrations e models de packages/, páginas/projections de surfaces/ e o operator-kit.

Legenda: **NU+ADM** edita nos dois · **ADM** só no Django Admin · **—** não existe em lugar nenhum.

## 1. Campo a campo — o que o Admin edita e o Nuxt não

### 1.1 Produto

Admin: packages/offerman/shopman/offerman/contrib/admin_unfold/admin.py (ProductAdmin, fieldsets :375-454; inlines :373; actions :563-571; import/export :297 e :332) e models/product.py:36-201, listing.py, collection.py, product_component.py.
Nuxt: surfaces/orders-nuxt/app/pages/catalog.vue; contrato surfaces/orders-nuxt/app/types/catalog.ts:172-296; API shopman/backstage/api/catalog.py (detalhe :124-196, produto :199-217, lote :337-346).

| Classe | Campos | Admin (onde) | Nuxt (onde) |
|---|---|---|---|
| NU+ADM | name, short_description, long_description, keywords, base_price_q, unit, unit_weight_g, availability_policy, shelf_life_days, storage_tip, production_cycle_hours, is_batch_produced, is_published, is_sellable, ingredients_text, image_url, nutrition_facts, metadata.social, metadata fiscal, rotulagem de compra remota (allergens, dietary_info, serves, approx_dimensions), allows_next_day_sale, vocation | fieldsets :375-454 | ProductDetailProjection / ProductDetailPatch types/catalog.ts:172-296; painel do produto em catalog.vue |
| ADM | sku (criação e renome); choice_group; made_to_order; ready_from; metadata cru; nutritional por formulário dedicado; e os vínculos: Listing/ListingItem (product, price_q, min_qty, is_published, is_sellable), Collection/CollectionItem (collection, is_primary, sort_order), ProductComponent (component, qty) | fieldsets :375-454; inlines :269-290, :373; contrib/import_export/resources.py | — (o contrato declara: "Fora daqui (segue no Admin): componentes de bundle, coleções e listings" — types/catalog.ts:169-171) |
| — | criar produto do zero; duplicar produto; tabelão célula a célula com colar/desfazer/salvar em lote | — | — (CatalogProductView.post só aceita is_published/is_sellable: catalog.py:210-217) |

Já existe em Nuxt (não é gap): publicação/pausa em lote (catalog.vue:1096, 1111, 1318, 1412; catalog.py:337-346) e exportar CSV da matriz (presentation/catalog.ts:342-366).

### 1.2 Receita

São dois cadastros distintos. A **ficha de execução** é craftsman.Recipe + RecipeItem (models/recipe.py:32-113 e :214-300; Admin contrib/admin_unfold/admin.py:380-438 e inline :142). O **inventário/fórmula** é RecipeBook/RecipeEntry/RecipeVersion (models/recipe_book.py), que o Nuxt já edita (production-nuxt/pages/recipes/*; API shopman/backstage/api/recipe_book.py).

| Modelo / campo | Classe | Onde |
|---|---|---|
| craftsman.Recipe: ref, name, is_active, output_sku, batch_size, steps, meta; operação: max_started_minutes, capacity_per_day, requires_batch_tracking, shelf_life_days, shelf_life_reviewed; RecipeItem: input_sku, quantity, usable_factor, unit, sort_order, is_optional, meta | ADM | fieldsets admin_unfold/admin.py:401-425; inline :142; models/recipe.py:43-92 e :241-291 |
| craftsman.Recipe cria/edita no Nuxt | — | — (o Nuxt só lê \(has_ficha\) e \(ficha_ref\): generated/recipeBookContract.ts:13 e :236) |
| RecipeBook/RecipeEntry: name, kind, output_sku, notes | NU | EntryCreatePayload/EntryPatch types/recipeBook.ts:179-204; recipe_book.py: RecipeBookListView GET :165 POST :181; RecipeEntryView PATCH :216; cofre shop/backup/resources.py:319-329 |
| RecipeVersion: formula (anchor.kind; items[name, sku, quantity, unit, role, grams_per_unit]; parts[kind, sku, cap_pct, flour_pct, quantity, unit]), yield_quantity, yield_unit, steps, notes, label | NU | types/recipeBook.ts:102-176; production-nuxt/pages/recipes/[ref]/edit.vue:397-592 |
| duplicar receita; CSV importar no Nuxt; ações em lote | — | — |

### 1.3 Insumo

Admin: packages/buyman/shopman/buyman/contrib/admin_unfold/admin.py (MaterialAdmin :67-79, SupplierMaterialCostAdmin :125-151, MaterialConversionAdmin :154-181) e models/material.py:28-48, conversion.py, cost.py.
Nuxt: surfaces/purchase-nuxt/app/pages/base/materials.vue, base/materials/[sku].vue e components/PurchaseMaterialDetail.vue; tipos surfaces/purchase-nuxt/app/types/purchase.ts:20-67; API shopman/backstage/api/purchase.py.

| Classe | Campos | Admin | Nuxt |
|---|---|---|---|
| ADM | Material: sku, name, unit, shelf_life_days, is_active, metadata. MaterialConversion: label, to_base_factor, kind, supplier, is_active, created_by. SupplierMaterialCost: material, supplier, conversion, cost_q, is_preferred | MaterialAdmin :67-79 (inlines ConversionOnMaterialInline, CostOnMaterialInline :58-64); :125-181 | — |
| NU+ADM | custo por fornecedor; mínimo declarado; conversão; "Permitir revenda" (preço → mesmo SKU); "Quando aberto, vira" | inlines e telas Admin | costs.vue, count.vue, PurchaseMaterialDetail.vue; purchase.py: upsert_cost :580, upsert_costs :626, set_min_stock :755, declare_conversion :849, set_opening :980, set_sale :1013 |
| — | criar insumo do zero no Nuxt; duplicar insumo; CSV importar no Nuxt; ações em lote sobre insumos (só custo/mínimo) | — | — |

### 1.4 Cliente

Admin: packages/guestman/shopman/guestman/contrib/admin_unfold/admin.py (CustomerAdmin fieldsets :392-422, inlines :368-390, actions :424) e models/customer.py:53-121, contact_point.py, address.py.
Nuxt: surfaces/orders-nuxt/app/pages/customers/index.vue e [ref].vue; API shopman/backstage/api/customers.py.

| Classe | Campos | Admin | Nuxt |
|---|---|---|---|
| ADM | first_name, last_name, customer_type, document, birthday, email, phone, price_tier, tags, is_active, notes, metadata; conta da casa (metadata.house_account / house_account_limit_q, form :249-320); preferências fiscais (:279-323); endereços; contatos; consentimento LGPD | fieldsets :392-422; inlines :368-390 | — (customers/index.vue:55 "Criar e editar cadastro continua no Admin"; :100-104 e :156-165 abrem o Admin) |
| NU | leitura 360 (ficha), busca, filtro, paginação, unificação e desfazer | — | customers/index.vue e [ref].vue; customers.py GET :50 e :69; merge :107; undo :149 |
| — | criar/editar cliente no Nuxt; duplicar; CSV importar no Nuxt; ações em lote no Nuxt | Admin tem export_selected_csv :424 | — |

### 1.5 Fornecedor

Admin: packages/buyman/shopman/buyman/contrib/admin_unfold/admin.py (SupplierAdmin :82-121; ContactOnSupplierInline :26-37) e models/supplier.py:17-52, contact.py.
Nuxt: surfaces/purchase-nuxt/app/pages/base/suppliers.vue e base/suppliers/[ref].vue; components/PurchaseSupplierDetail.vue; tipos purchase.ts:114-143.

| Classe | Campos | Admin | Nuxt |
|---|---|---|---|
| ADM | Supplier: ref, name, trade_name, document, email, phone, is_active, metadata. SupplierContact: name, role, email, phone, is_primary, is_active, notes | fieldsets :89-102; inline :37 | — (PurchaseSupplierDetail.vue:12 e :71/:75: "Contatos se cadastram no Admin") |
| NU | lista (insumos cobertos, no prazo, prazo de entrega) e ficha (carteira de custos) — leitura | — | suppliers.vue; PurchaseSupplierDetail.vue |
| — | criar fornecedor do zero no Nuxt; duplicar; CSV importar no Nuxt; ações em lote | Admin tem criação automática pelo emitente da nota: purchase.py _adopt_supplier_by_name :2154, _register_supplier_from_issuer :2194 | — |

### 1.6 Grupo de cliente

Admin: packages/guestman/shopman/guestman/models/price_tier.py:24-58; PriceTierAdmin em packages/guestman/.../contrib/admin_unfold/admin.py:31-53, estendido por shopman/shop/admin/price_tier.py (fieldsets :168-180; gravação da Promotion :132-156). Nuxt: nenhuma tela.

| Classe | Campo | Admin | Nuxt |
|---|---|---|---|
| ADM | ref, name, description, listing_ref, is_default, priority, metadata; desconto do grupo (type, value, channels) → Promotion ref \(grupo-<ref>\) | shop/admin/price_tier.py:66-205 | — (§7.2: "grupos de clientes (só Admin)") |
| — | tela Nuxt do grupo; **vários clientes no mesmo grupo** (hoje Customer.price_tier é FK única: models/customer.py:84); vantagens tipadas além de desconto (frete grátis, coleção exclusiva, promoção, notificação) | — | — |

### 1.7 Resposta curta do §1

Só no Admin, por entidade: produto (criar, duplicar, sku, vínculos de listing/coleção/componente, metadata cru); receita (ficha de execução inteira + itens + operação); insumo (todos os campos do Material, conversões e custos completos); cliente (criar/editar, tags, grupo, conta da casa, endereços, contatos, consentimento); fornecedor (criar/editar + contatos); grupo (tudo).
Em lugar nenhum: criar/duplicar em massa nos apps, tabelão com colar/desfazer, importar CSV com prévia/erro por linha, tela de grupo com múltiplos clientes e vantagens tipadas.

## 2. Requisito do dono → peça do kit

Peças do kit: surfaces/operator-kit/app/components/OperatorTable.vue, OperatorBulkBar.vue, OperatorActionBar.vue, OperatorRecordNav.vue, OperatorFilterPanel.vue, OperatorQuickFilters.vue, OperatorTableView.vue; composable useOperatorTableView.ts.

| Requisito (14/10) | O kit já oferece | Falta nascer no kit | Evidência |
|---|---|---|---|
| Ações em lote sobre a seleção | OperatorTable com seleção múltipla e rowSelection (:50-53, :103); OperatorBulkBar com escopo, ações, Esc e placement toolbar/base (:37-55, :83-95); OperatorCountChip | Gestos destrutivos confirmar+Desfazer como padrão (as peças existem: OperatorConfirmDialog, OperatorTimedButton); seleção que sobrevive à paginação no servidor; endpoint de lote por entidade (só o catálogo tem) | Contagem/UI: OperatorBulkBar.vue; lote servidor só em catalog.py:337-346 |
| Tabelão editável célula a célula, colar planilha, desfazer, salvar em lote | OperatorTable + useOperatorTableView (densidade/colunas, :22-64); salvar lote com OperatorActionBar já usado em purchase-nuxt/app/pages/base/materials.vue:317-322 (embrião) | Primitiva de célula editável; colar de planilha (não há clipboard/onPaste no kit); pilha de desfazer (só OperatorTimedButton.vue:2-6, desfazer de UMA ação com prazo); contrato de lote para o catálogo (hoje célula a célula: catalog/cell/) | OperatorTable.vue:40-105; OperatorActionBar.vue:46-60 |
| Filtros, busca e ordenação em toda lista | OperatorFilterPanel (dimensões, favoritos/salvas, data, agrupar: :51-88); OperatorQuickFilters (:43-61); OperatorSuiteSearch; ordenação por cabeçalho (OperatorTable :8) e "Exibir" (OperatorTableView :13-18) | Contrato de filtro/ordenação no SERVIDOR; padronizar as listas que ainda usam checkbox/select (receitas) | Filtro/ordenação do catálogo é do cliente: catalogFilters.ts:3-5 |
| Listas sensíveis a data com atalhos de período | OperatorFilterPanel periodPresets/customPeriod/defaultPeriod (:55-60, :87) sobre presentation/dates | Nada estrutural: cada lista declara os presets. O eixo de data existe no modelo (Listing.valid_from/valid_until, Collection.valid_from/valid_until) e ainda não é filtro | OperatorFilterPanel.vue:55-88 |
| Duplicar registro | Nada | Primitiva de ação "Duplicar" + endpoint no backstage. Não há \(duplicar\) em packages/ (só dedup/merge) | grep duplic em packages/ |
| Exportar/importar CSV pt-BR com prévia e erro por linha | Export existe como função (readingCsvText/readingCsvMoney) e no ⋯ do OperatorReadingCard | Helper/componente genérico "exportar esta lista"; e TODO o import: nenhum endpoint, nenhuma prévia, nenhum relatório por linha | kit app/presentation/readingChart.ts:291-346; uso no catálogo presentation/catalog.ts:342-366. Backend: ImportExportModelAdmin + ProductResource (admin_unfold/admin.py:297, :332; contrib/import_export/resources.py) e cofre shop/backup/resources.py (ProductBackupResource :218, SupplierResource :376, MaterialResource :382, PriceTierResource :416) |
| Checklist D1–D12 à altura da suíte | app.config.ts + README + guardrails codificam D1–D5, D7, D11; D6 (OperatorFitLabel/actionLabel.ts), D8 (OperatorSonner/alertActions), D9 (OperatorActionBar, OperatorConfirmDialog, OperatorTimedButton) | Nada novo no kit: D10 (copy) e D12 (captura) são gate por tela; D9 no tabelão precisa do par inline+Aplicar/Cancelar e destrutivo+Desfazer | OperatorActionBar.vue:8-36; OperatorBulkBar.vue:14-18 |

## 3. Ondas propostas

Estimativas de tamanho: P/M/G. "Core?" = exige mudança em packages/.

| Onda | Escopo | Tamanho | Risco | Depende de | Core? |
|---|---|---|---|---|---|
| 1. Catálogo de produtos (B5) | criar do zero (endpoint+form), duplicar, tabelão (preço/publicado/vendável por superfície) com colar/desfazer/salvar em lote, lista com paginação/filtro/ordenação no servidor, CSV export (existe) e import com prévia e erro por linha, BulkBar ligada às ações que já existem | G (a maior) | Alto: corrige o catálogo do Dia 1 e mexe na projeção iFood/Meta | — | Não |
| 2. Insumos e fornecedores | criar/editar Material, Supplier, SupplierContact, MaterialConversion e custos no Nuxt; duplicar; lote de custo/mínimo já existe | M | Médio: Compras já opera; hoje contatos e cadastro mandam ao Admin | Onda 1 (kit de tabelão/CSV) | Não |
| 3. Receitas (ficha de execução) | fechar o gap de craftsman.Recipe + RecipeItem no Nuxt; duplicar; RecipeBook já tem CRUD | M | Médio: BOM errado desconta estoque errado (mass balance models/recipe.py:125-182) | Onda 1 (kit) | Não |
| 4. Clientes | criar/editar no Nuxt sobre o service existente, duplicar, ações em lote, ordenação no servidor | M | Alto: PII/LGPD (consentimento, endereços, contatos) e merge | Onda 1 (kit) | Não |
| 5. Grupos de clientes (§7.1) | tela Nuxt do grupo, associação de vários clientes, vantagens tipadas; consome a decisão da §7.1 | M/G | Alto | Onda 4 e a decisão de Core da §7.1 | **Sim** |

**Core (packages/) — a única mudança medida:** grupo de cliente. Hoje Customer.price_tier é FK única (guestman models/customer.py:84) e PriceTier não tem coleção de clientes (models/price_tier.py:24-58); o desconto grava Promotion com customer_segments=[tier.ref] (shop/admin/price_tier.py:132-156) e o motor assume uma faixa por cliente. "Cliente em mais de um grupo, melhor vantagem por tipo, sem acumular" exige relação N:N e vantagens tipadas no guestman, com migração, e ajuste em shop/services/promotions.py.

**Não exigem Core:** catálogo (as escritas moram em shopman/backstage/services/catalog.py; offerman não tem diretório services/), custos/mínimo (shopman/backstage/services/purchase.py:626 e :755), cliente (packages/guestman/.../services/customer.py:194 create, :246 update), receita (craftsman.Recipe já modelado; ficha e itens completos). Não falta campo: Product/Listing/Collection/ProductComponent, Recipe/RecipeItem, Material/Supplier, Customer/PriceTier já têm os campos usados. Chave nova de JSONField entra antes em docs/reference/data-schemas.md, sem migração (regra do CLAUDE.md). "Duplicar produto" que copie listing/coleção/componente é serviço de backstage — não criar campo no Core.

## 4. Desempenho como requisito

| Onda | Paginação/virtualização no servidor | Filtro/ordenação no banco | Salvar em lote numa ida |
|---|---|---|---|
| 1. Catálogo | Precisa: a matriz vem inteira (catalogFilters.ts:3-5); build_catalog_matrix ordena mas não pagina (projections/catalog.py:506-541). Paginar e virtualizar linhas | Precisa: hoje filtra/ordena no cliente (catalogFilters.ts); levar name, sku, is_published, is_sellable e coleção para o banco | Publicação e preço já são uma ida com prévia + idempotência (catalog.py:270-346). O tabelão NÃO pode virar N PATCHes em catalog/cell/: precisa endpoint de lote |
| 2. Insumos/fornecedores | Precisa: a Base manda materials+suppliers+conversions+costs inteiros (types/purchase.ts:179-201); paginar/filtrar/ordenar no servidor | Precisa para visão de compra (nome, situação, cobertura, custo-base) | Custo e mínimo já são lote numa ida (PurchaseCostBatchPayload / PurchaseMinStockPayload; purchase.py:626 e :755) |
| 3. Receitas | Precisa: GET recipes/ devolve a lista inteira (useRecipeBook.ts:24); q/kind/archived já vão, falta paginar | Precisa: ordenação por atualização/tipo e busca no banco | Sem lote natural: a versão se edita uma por vez |
| 4. Clientes | Já paginado no servidor (customers.py:50-58; CustomerListProjection page/page_size/total/has_next) | Falta ordenação no servidor (hoje só q e filtro) | Ações em lote (tag, export) e edição precisam endpoint em uma ida |
| 5. Grupos | Não precisa: cardinalidade pequena | Não | Associação cliente↔grupos numa transação |

## 5. Os 3 maiores riscos e a ordem exata

1. **Lote que pula o save()**: o Admin itera save() por produto para disparar product_updated → re-projeção iFood/Meta (contrib/admin_unfold/admin.py:573-583). Um update em massa fora do service deixa canal externo desatualizado em silêncio.
2. **Concorrência no catálogo**: a gravação exige intenção + base_revision + Idempotency-Key (catalog.py:156-196). Tabelão com colar de planilha multiplica conflito; precisa prévia, conflito por linha e revisão.
3. **Escopo do Core (§7.1) contaminando o B5**: multi-grupo exige migração e mexe no motor de promoções; se entrar na onda 1, atrasa a correção do catálogo do Dia 1. Clientes trazem LGPD.

**Ordem exata:** 1) catálogo de produtos (B5) → 2) insumos e fornecedores → 3) receitas (ficha de execução) → 4) clientes → 5) grupos de cliente (depende da decisão de Core da §7.1).
