import type { ReadMetadata } from "./readMetadata";
import type { Action } from "~/generated/ordersContract";
// TS mirror of the Django catalog matrix projection
// (shopman/backstage/projections/catalog.py), serialised by backstage/api/projections.py.
// Kept in lockstep — the surface renders intent, the backend owns rules.

export type SurfaceSyncStatus = "ok" | "error" | "never" | "na";
export type SurfaceKind = "channel" | "display" | "feed";

// Estado de sync por CÉLULA (produto × plataforma) — CatalogSyncState (Arc C).
// "" = nunca sincronizado / superfície que não projeta (feed de pull).
export type CellSyncStatus =
  "synced" | "pending" | "error" | "retracted" | "skipped" | "";

// Atributos PIM sociais da linha (Arc A) — Product.metadata['social'].
export interface ProductSocial {
  brand: string;
  gtin: string;
  mpn: string;
  condition: string;
  google_product_category: string;
  tiktok_category_id: string;
  hashtags: string[];
  social_caption: string;
  has_data: boolean;
}

// Uma coluna da matriz é uma SUPERFÍCIE: um Canal de venda (transacional) OU um
// Feed, que só EMPURRA dados para fora (📺 menuboard / 🛰 Google/Meta). Feed não
// vende: a célula só pausa/reativa o item, sem preço nem publicação. A pausa global
// do produto gateia canais E feeds. No backend o model chama-se ``Feed``.
export interface SurfaceProjection {
  ref: string;
  name: string;
  short_name: string; // rótulo curto do cabeçalho; nunca vazio (cai para `name`)
  is_projection_target: boolean;
  sync_status: SurfaceSyncStatus;
  kind: SurfaceKind;
  transactional: boolean; // canal vende (preço/publicação); feed só exibe (pausa)
  icon: string; // dica de ícone p/ feeds (tv/rss); vazio p/ canal
  output_path: string; // saída pública do feed (abrir/prever); vazio p/ canal
  sync_key: string; // chave no CatalogSyncState.platform (ref p/ canais, kind p/ feeds)
}

export interface SurfaceCellProjection {
  pause_audit?: string;
  action?: Action | null;
  surface_ref: string;
  in_listing: boolean;
  is_published: boolean;
  is_sellable: boolean;
  available: boolean;
  price_q: number | null;
  price_display: string;
  sync_status: CellSyncStatus; // estado do último push p/ esta plataforma
  sync_error: string; // mensagem do erro (quando sync_status="error")
  synced_at: string; // ISO do último push OK (vazio = nunca)
}

export interface CatalogRowProjection {
  product_action?: Action | null;
  resync_action?: Action | null;
  sku: string;
  name: string;
  image_url: string;
  primary_collection: string;
  primary_collection_name: string;
  is_active: boolean;
  is_published: boolean;
  is_sellable: boolean;
  base_price_q: number;
  base_price_display: string;
  edit_url: string;
  stock_tracked: boolean;
  stock_qty: number | null;
  sold_out: boolean;
  low_stock: boolean;
  replenish_qty: number;
  keywords: string[];
  cells: SurfaceCellProjection[];
  social: ProductSocial; // atributos PIM sociais (Arc A)
  pim_complete: boolean; // tem o essencial p/ feed (brand + categoria Google)
  // Passa por todos os portões do cardápio e mesmo assim não aparece: o único
  // vínculo de coleção é com uma coleção desativada, e o balde "sem categoria"
  // só recolhe quem não tem vínculo nenhum. Efeito colateral, não escolha.
  hidden_by_inactive_collection: boolean;
  // Tem vocação (etiqueta de consumo do SKU)? Só o B.I. lê; aqui serve ao
  // filtro "Vocação" e ao aviso discreto da lista.
  has_vocation: boolean;
}

export interface CollectionProjection {
  ref: string;
  name: string;
  is_smart: boolean;
  product_count: number;
}

// Contagens por opção das facetas de lista, do recorte ATUAL (o servidor conta,
// nunca a página). A seleção da própria dimensão fica fora da conta.
export interface CatalogFacets {
  stock: Record<string, number>;
  sync_status: Record<string, number>;
}

export interface CatalogMatrixProjection {
  surfaces: SurfaceProjection[];
  rows: CatalogRowProjection[];
  collections: CollectionProjection[];
  facets: CatalogFacets;
  // Produtos à venda sem vocação, da loja inteira (não do recorte de coleção).
  vocation_pending: VocationPending[];
  // Paginação/filtro/ordenação no SERVIDOR (onda 1, fatia B): a matriz não vem
  // inteira, e `total`/`has_next` dizem o tamanho da consulta.
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  order: CatalogOrder;
  query: string;
}

export type CatalogOrder =
  "name" | "-name" | "sku" | "-sku" | "price" | "-price" | "updated";

export interface VocationPending {
  sku: string;
  name: string;
}

/** Uma escolha de vocação: um papel de consumo ativo, editável no Admin. */
export interface VocationChoice {
  ref: string;
  label: string;
  hint: string;
}

export interface CatalogMatrixResponse extends ReadMetadata {
  matrix: CatalogMatrixProjection;
  collection_ref?: string;
  actions?: Action[];
}

// Tabela nutricional (ANVISA) — espelha a dataclass `offerman.nutrition.NutritionFacts`.
// `auto_filled` é sentinel interno (derivação a partir da receita) e não é editável
// aqui: o backend o zera sozinho quando o operador digita.
export interface NutritionFacts {
  serving_size_g: number;
  servings_per_container: number;
  energy_kcal: number | null;
  carbohydrates_g: number | null;
  sugars_g: number | null;
  proteins_g: number | null;
  total_fat_g: number | null;
  saturated_fat_g: number | null;
  trans_fat_g: number | null;
  fiber_g: number | null;
  sodium_mg: number | null;
}

// Classificação fiscal do produto — espelha `fiscalman.classification`.
// O que NÃO é por produto (CFOP, CSOSN, PIS/COFINS) vem do perfil.
export interface ProductFiscal {
  profile: string;
  ncm: string;
  cest: string;
  unit: string;
  /** Origem da mercadoria (orig do ICMS): 0 nacional, 2 importado comprado no Brasil… */
  origin: string;
}

export interface FiscalOriginChoice {
  key: string;
  name: string;
}

export interface FiscalProfileChoice {
  key: string;
  name: string;
  requires_cest: boolean;
}

// Detalhe de UM produto — tudo que o painel de produto edita
// (GET/PATCH /api/v1/backstage/catalog/product/<sku>/). Espelha
// `backstage.services.catalog._detail_payload`. Fora daqui (segue no Admin):
// componentes de bundle, coleções e listings.
export interface ProductDetailProjection {
  readonly sku: string;
  name: string;
  short_description: string;
  long_description: string;
  keywords: string[];
  base_price_q: number;
  unit: string;
  unit_weight_g: number | null;
  availability_policy: string;
  shelf_life_days: number | null;
  storage_tip: string;
  production_cycle_hours: number | null;
  is_batch_produced: boolean;
  /** Cadastro operacional: muda só pelo gesto Arquivar/Desarquivar. */
  readonly is_active: boolean;
  is_published: boolean;
  is_sellable: boolean;
  ingredients_text: string;
  image_url: string;
  // rotulagem de compra remota (Product.metadata) — o cliente não pega o produto
  // na mão, então alérgenos e restrições precisam estar escritos.
  allergens: string[];
  dietary_info: string[];
  serves: string;
  approx_dimensions: string;
  allows_next_day_sale: boolean;
  nutrition_facts: NutritionFacts;
  social: ProductSocial;
  fiscal: ProductFiscal;
  readonly primary_collection: string;
  readonly primary_collection_name: string;
  // somente-leitura: dado veio da receita; editar à mão congela a derivação.
  readonly field_sources?: Record<string, string>;
  readonly dietary_from_recipe: boolean;
  readonly nutrition_auto_filled: boolean;
  readonly fiscal_profiles: FiscalProfileChoice[];
  readonly fiscal_origins?: FiscalOriginChoice[];
  /** Avisos do servidor (não bloqueiam): CEST incompatível com o NCM. */
  readonly fiscal_warnings?: string[];
  /** A SEFAZ recusou o GTIN numa NFC-e; `null` quando não. */
  readonly gtin_rejected?: GtinRejected | null;
  // Selos derivados do SKU — somente leitura. "Permitir compra" é gesto próprio
  // (POST .../purchase/), não campo do rascunho.
  readonly roles?: SkuRoles;
  /**
   * O modo de produção da ficha vigente do SKU (ADR-040): "Em lote" ou "Na hora",
   * e a estação de preparo do feito na hora. Somente leitura: o modo se muda na
   * ficha, na Produção. `null` sem ficha (revenda).
   */
  readonly production?: ProductProduction | null;
  /** Vocação do SKU (ref do papel de consumo); "" = sem vocação. Só para o B.I. */
  vocation: string;
  readonly vocation_choices: VocationChoice[];
  /** Onde dá para comprar agora (V4-G4): do registro de faltas, somente leitura. */
  readonly channel_availability?: ChannelAvailability[];
  /** "10:40" e "lote de 42 no forno": o próximo lote do SKU hoje (G23). */
  readonly back_at?: string;
  readonly back_reason?: string;
  /** O histórico de alterações do produto no Admin (⋯ do painel). */
  readonly admin_history_path?: string;
}

/** Um canal no painel do produto: vende agora, esgotado ou pausado, e desde quando. */
export interface ChannelAvailability {
  readonly ref: string;
  readonly name: string;
  readonly kind: "sale" | "display";
  readonly state: "available" | "sold_out" | "paused";
  /** "09:52" quando indisponível. */
  readonly since: string;
  /** O canal recebe a indisponibilidade sozinho (iFood, Meta, Google). */
  readonly automatic: boolean;
  /** "10:40": o esgotado volta com o próximo lote (G23); vazio sem lote ou na pausa. */
  readonly back_at?: string;
  /** "lote no forno" · "lote programado". */
  readonly back_hint?: string;
  /** A segunda linha: o que o cliente vê ali ("'Me avise' ligado, 3 esperando"). */
  readonly note?: string;
}

/**
 * GTIN recusado pela SEFAZ (`Product.metadata.gtin_nf_rejected`). A nota já saiu
 * de novo sem GTIN; o produto segue saindo sem ele até alguém conferir a
 * embalagem: corrigir `social.gtin` apaga a marca, e `confirmed` registra que
 * ele fica sem GTIN na nota.
 */
export interface GtinRejected {
  readonly gtin: string;
  readonly code: string;
  readonly reason: string;
  readonly at: string;
  readonly order_ref: string;
  readonly confirmed: boolean;
  readonly confirmed_by: string;
  readonly confirmed_at: string;
}

/** O modo de produção de um produto, com a frase pronta e o endereço da ficha. */
export interface ProductProduction {
  readonly mode: "batch" | "made_to_order";
  readonly mode_label: string;
  /** A estação de preparo do feito na hora; vazia em lote ou sem estação. */
  readonly station: string;
  /** "Feito na hora na estação Cafés: os insumos baixam a cada venda." */
  readonly summary: string;
  readonly recipe_ref: string;
  readonly recipe_name: string;
  /** Vazio quando a Produção não tem endereço configurado. */
  readonly url: string;
}

/** Comprável · Vendável · Produzido · Usado em receita — derivados no servidor. */
export interface SkuRoles {
  purchasable: boolean;
  sellable: boolean;
  produced: boolean;
  used_in_recipe: boolean;
}

// Merge parcial: só as chaves presentes são gravadas. `social` e `fiscal` também
// fazem merge por dentro (mandar só `brand` não apaga a categoria).
export type ProductDetailPatch = Partial<
  Omit<
    ProductDetailProjection,
    | "sku"
    | "primary_collection"
    | "primary_collection_name"
    | "field_sources"
    | "dietary_from_recipe"
    | "nutrition_auto_filled"
    | "is_active"
    | "fiscal_profiles"
    | "fiscal_origins"
    | "fiscal_warnings"
    | "roles"
    | "production"
    | "vocation_choices"
    | "gtin_rejected"
    | "social"
    | "fiscal"
    | "nutrition_facts"
  >
> & {
  gtin_rejected?: { confirmed: true };
  social?: Partial<Omit<ProductSocial, "has_data">>;
  fiscal?: Partial<ProductFiscal>;
  nutrition_facts?: Partial<NutritionFacts>;
};

export interface ProductDetailResponse {
  product: ProductDetailProjection;
  action?: Action;
}

export interface ProductEditConflict extends ProductDetailResponse {
  conflicting_fields: string[];
}

// Assist de IA — sugestão de conteúdo para UM campo de texto de UM produto
// (POST /api/v1/backstage/catalog/ai-assist/). É sempre por campo: o operador
// aceita ou descarta cada sugestão sozinha, e nada é gravado até ele salvar.
// Espelha `backstage.services.catalog.ASSISTABLE_FIELDS`.
export type AssistableField =
  | "short_description"
  | "long_description"
  | "ingredients_text"
  | "social_caption"
  | "hashtags";

export interface AiAssistRequest {
  sku: string;
  field: AssistableField;
  current_value: string;
  context?: Record<string, unknown>;
}

// `hashtags` volta como texto separado por espaço — o painel já normaliza texto
// livre em lista, então o contrato é uma string para todos os campos.
export interface AiAssistResponse {
  suggestion: string;
}

// ── Criar produto, duplicar e rascunho por GTIN (7.2, onda 1) ────────────────
// O rascunho do GTIN NÃO grava: as fontes (NF-e de compra -> Cosmos -> Open Food
// Facts) vivem em `shop.services.product_enrichment`; aqui só chega o campo com a
// ORIGEM. Quem aplica é o aceite campo a campo, no mesmo caminho do Admin.
export interface EnrichmentFieldEntry {
  value: unknown;
  source: string;
  source_ref?: string;
  fetched_at?: string;
  detail?: string;
  alternatives?: { value: unknown; source: string; fetched_at?: string }[];
}

export interface EnrichmentFieldDraft extends EnrichmentFieldEntry {
  label: string;
  source_label: string;
  display: string;
}

export interface CorrelationSuggestion {
  field: string;
  value: unknown;
  reason: string;
  sources: string[];
}

export interface CorrelateResult {
  correlates: { sku: string; name: string; reasons: string[] }[];
  suggestions: CorrelationSuggestion[];
  notes: string[];
}

export interface ReferencePhoto {
  url: string;
  source: string;
  license: string;
  attribution: string;
  fetched_at?: string;
}

export interface ProductDraft {
  gtin: string;
  fields: Record<string, EnrichmentFieldDraft>;
  sources: string[];
  consulted: string[];
  skipped: Record<string, string>;
  allergens_unmapped: string[];
  notes: string[];
  reference_photo: ReferencePhoto | null;
  correlate: CorrelateResult;
}

export interface DuplicateSnapshot {
  source: { sku: string; name: string };
  suggested_sku: string;
  suggested_name: string;
  action: Action;
}

export interface CreateProductPayload {
  sku: string;
  name: string;
  base_price_q?: number;
  unit?: string;
  unit_weight_g?: number | null;
  short_description?: string;
  long_description?: string;
  keywords?: string[];
  image_url?: string;
  availability_policy?: string;
  shelf_life_days?: number | null;
  storage_tip?: string;
  ingredients_text?: string;
  production_cycle_hours?: number | null;
  is_batch_produced?: boolean;
  is_published?: boolean;
  is_sellable?: boolean;
  social?: Partial<ProductSocial>;
  fiscal?: Partial<ProductFiscal>;
  nutrition_facts?: Partial<NutritionFacts>;
  enrichment?: { gtin: string; accept: string[]; replace?: string[] };
  // Intenção do cadastro (fatia E): a resposta conduz o caminho.
  intent?: "revenda" | "producao" | "insumo";
  purchase?: boolean;
}

export interface DuplicatePayload {
  sku: string;
  name?: string;
}
export interface EnrichmentAcceptResult {
  applied: string[];
  conflicts: Record<string, unknown>;
  refused: Record<string, string>;
  sources: string[];
  notes: string[];
}

export interface CreateProductResponse {
  ok: boolean;
  outcome: string;
  product: ProductDetailProjection;
  enrichment?: EnrichmentAcceptResult;
}

// Tabelão: uma célula do lote que vai para POST catalog/cells/ numa ida.
export interface BulkCell {
  sku: string;
  surface_ref: string;
  price_q?: number;
  is_published?: boolean;
  is_sellable?: boolean;
  base_revisions?: Record<string, string>;
}

export interface BulkCellsResponse {
  ok: boolean;
  outcome: string;
  applied: {
    index: number;
    sku: string;
    surface_ref: string;
    price_q: number | null;
    is_published: boolean;
    is_sellable: boolean;
  }[];
  conflicts: {
    index: number;
    sku: string;
    surface_ref: string;
    detail: string;
    conflicting_fields?: string[];
  }[];
  errors: { index: number; sku: string; surface_ref: string; detail: string }[];
}

export interface ProductArchiveLine {
  index: number;
  sku: string;
  name: string;
  before_is_active: boolean;
  is_active: boolean;
  changed: boolean;
}

export interface ProductArchiveReceipt {
  ok: boolean;
  outcome: string;
  intention: string;
  applied: ProductArchiveLine[];
  conflicts: {
    index: number;
    sku: string;
    detail: string;
    is_active: boolean;
  }[];
  errors: { index: number; sku: string; detail: string }[];
  server_now: string;
  undo_until: string;
}
// Import CSV pt-BR: a prévia não grava; o apply leva a revisão da prévia.
export interface ImportPreviewChange {
  sku: string;
  action: "new" | "update";
  name: string;
  before: {
    name: string;
    base_price_q: number;
    is_published: boolean;
    is_sellable: boolean;
  } | null;
}

export interface ImportPreview {
  dry_run: boolean;
  rows: number;
  totals: Record<string, number>;
  errors: { row: number; detail: string }[];
  changes: ImportPreviewChange[];
  base_revision: string;
}
export interface PhotoEnhanceResponse {
  provider: string;
  media_type: string;
  image: string;
  steps: string[];
}
