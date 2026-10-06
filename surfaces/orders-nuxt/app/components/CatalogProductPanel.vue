<script setup lang="ts">
// Painel de produto — edição COMPLETA de um produto sem sair do Gestor. Presentacional:
// o pai é dono do fetch/save (useCatalogMatrix.fetchProductDetail / saveProductDetail)
// e do estado de ocupado; aqui mora só o rascunho, dividido em cinco abas:
// Geral · Preço e config · Ingredientes e nutrição · Redes sociais · Fiscal.
//
// Emitimos APENAS o que mudou — o backend faz merge parcial, então não tocar num campo
// é diferente de gravá-lo igual. Os blocos aninhados (social, fiscal, nutricional)
// também vão parciais: mandar só `brand` não apaga a categoria.
//
// Fora do escopo (segue no Admin): componentes de bundle, coleções e listings.
import type {
  AssistableField,
  NutritionFacts,
  ProductDetailPatch,
  ProductEditConflict,
  ProductDetailProjection,
  SkuRoles,
} from "~/types/catalog";
import { vocationLabel, vocationOptions } from "~/presentation/vocation";
import { useIntersectionObserver } from "@vueuse/core";

const props = defineProps<{
  open: boolean;
  sku: string | null;
  detail: ProductDetailProjection | null;
  loading: boolean;
  busy: boolean;
  // assist de IA por campo — o pai injeta (useCatalogMatrix); o painel segue
  // presentacional e testável sem rede.
  assist: (field: AssistableField, currentValue: string) => Promise<string>;
  assistBusy: (field: AssistableField) => boolean;
  // aba em que o painel abre — o menu da linha tem um atalho direto para "Redes
  // sociais", que antes era um slide-over separado.
  initialTab?: string;
  conflict?: ProductEditConflict | null;
  error?: string;
  // Selos do SKU e o gesto "Permitir compra" — fora do rascunho: valem na hora.
  roles?: SkuRoles | null;
  purchaseBusy?: boolean;
  // O interruptor de cada canal na tabela (G22): pausado à mão, gesto liberado e
  // ocupado. O "Pausar" da linha é o MESMO gesto da célula da matriz.
  channelCells?: Record<string, { paused: boolean; enabled: boolean; busy: boolean }>;
  // A disponibilidade relida depois de um Pausar (sem recarregar o rascunho).
  liveAvailability?: ProductDetailProjection["channel_availability"] | null;
  // Endereço do Admin: o "Histórico" do ⋯ abre o histórico de alterações de lá.
  adminBaseUrl?: string;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [patch: ProductDetailPatch];
  "review-conflict": [keepDraft: boolean];
  "dirty-change": [dirty: boolean];
  "set-purchasable": [enabled: boolean];
  "pause-channel": [ref: string, pause: boolean];
}>();

// ⋯ do cabeçalho (v4): Ocultar/Exibir (entra no rascunho), Permitir compra (vale na
// hora) e o Histórico de alterações.
const headerMenuOpen = ref(false);
const historyHref = computed(() => {
  const path = props.detail?.admin_history_path || "";
  return path && props.adminBaseUrl ? `${props.adminBaseUrl.replace(/\/+$/, "").replace(/\/admin$/, "")}${path}` : "";
});
function toggleHidden() {
  headerMenuOpen.value = false;
  draft.is_published = !draft.is_published;
}
function togglePurchaseFromMenu() {
  headerMenuOpen.value = false;
  emit("set-purchasable", !props.roles?.purchasable);
}
// "Descrição e foto seguem abaixo ⌄": o rodapé aponta o que a Geral ainda guarda
// abaixo da dobra e leva até lá; some quando o bloco aparece.
const bodyEl = ref<HTMLElement | null>(null);
const belowEl = ref<HTMLElement | null>(null);
const belowVisible = ref(true);
useIntersectionObserver(belowEl, ([entry]) => { belowVisible.value = Boolean(entry?.isIntersecting); }, { root: bodyEl });
function showBelow() {
  belowEl.value?.scrollIntoView({ behavior: "smooth", block: "start" });
}

// Vendido por peso = unidade de venda kg (contrato do PDV). Desligar volta a
// vender por unidade; outra unidade (lt, dz) se escreve no campo Unidade.
const soldByWeight = computed(() => draft.unit.trim().toLowerCase() === "kg");
function setSoldByWeight(on: boolean) {
  draft.unit = on ? "kg" : "un";
}

// O interruptor mostra o que o SERVIDOR diz: devolve a marca ao estado atual e
// deixa o selo novo (ou a recusa) redesenhar. Sem isso a recusa "é produzido
// aqui" deixaria o quadrado marcado, mentindo.
function onPurchaseChange(wanted: boolean) {
  emit("set-purchasable", wanted);
}

// Disponibilidade nos canais (V4-G4): o que o servidor leu do registro de faltas.
const availability = computed(() => props.liveAvailability ?? props.detail?.channel_availability ?? []);
const unavailableCount = computed(() => availability.value.filter((row) => row.state !== "available").length);
const availabilityHeadline = computed(() => {
  const off = availability.value.filter((row) => row.state !== "available");
  const paused = off.some((row) => row.state === "paused");
  const since = off.map((row) => row.since).filter(Boolean).sort()[0] ?? "";
  const word = paused ? "Pausado" : "Esgotado";
  const where = off.length === availability.value.length ? "" : ` em ${off.length} de ${availability.value.length}`;
  return `${word}${where}${since ? ` desde ${since}` : ""}`;
});
function channelIcon(row: { ref: string; kind: string }): string {
  if (row.ref === "ifood") return "lucide:bike";
  if (row.ref === "pdv" || row.ref === "pos" || row.ref === "balcao") return "lucide:store";
  if (row.ref === "whatsapp") return "lucide:message-circle";
  if (row.kind === "display") return "lucide:rss";
  return "lucide:globe";
}

// Comprável · Vendável · Produzido · Usado em receita — só o que é verdade.
const roleBadges = computed(() => {
  const roles = props.roles;
  if (!roles) return [];
  return [
    roles.purchasable && "Comprável",
    roles.sellable && "Vendável",
    roles.produced && "Produzido",
    roles.used_in_recipe && "Usado em receita",
  ].filter((badge): badge is string => Boolean(badge));
});

const TABS = [
  { id: "geral", label: "Geral" },
  { id: "config", label: "Preço e config" },
  { id: "rotulagem", label: "Ingredientes e nutrição" },
  { id: "social", label: "Redes sociais" },
  { id: "fiscal", label: "Fiscal" },
] as const;
type TabId = (typeof TABS)[number]["id"];
const tab = ref<TabId>("geral");

const POLICIES = [
  { value: "stock_only", label: "Somente estoque" },
  { value: "planned_ok", label: "Aceita planejado" },
  { value: "demand_ok", label: "Aceita demanda" },
] as const;

const CONDITIONS = [
  { value: "new", label: "Novo" },
  { value: "refurbished", label: "Recondicionado" },
  { value: "used", label: "Usado" },
] as const;

// Tabela nutricional: os mesmos três grupos do rótulo ANVISA, na mesma ordem do
// formulário do Admin. Rótulos em pt-BR, chaves em inglês (contrato do backend).
const SERVING_FIELDS = [
  { key: "serving_size_g", label: "Porção (g)", step: "1" },
  { key: "servings_per_container", label: "Porções por embalagem", step: "1" },
] as const;
const MACRO_FIELDS = [
  { key: "energy_kcal", label: "Valor energético (kcal)", step: "0.01" },
  { key: "carbohydrates_g", label: "Carboidratos (g)", step: "0.01" },
  { key: "sugars_g", label: "Açúcares (g)", step: "0.01" },
  { key: "proteins_g", label: "Proteínas (g)", step: "0.01" },
  { key: "total_fat_g", label: "Gorduras totais (g)", step: "0.01" },
  { key: "saturated_fat_g", label: "Gorduras saturadas (g)", step: "0.01" },
  { key: "trans_fat_g", label: "Gorduras trans (g)", step: "0.01" },
] as const;
const MICRO_FIELDS = [
  { key: "fiber_g", label: "Fibras (g)", step: "0.01" },
  { key: "sodium_mg", label: "Sódio (mg)", step: "0.01" },
] as const;
type NutritionKey = keyof NutritionFacts;
const NUTRITION_KEYS: NutritionKey[] = [
  ...SERVING_FIELDS.map((f) => f.key),
  ...MACRO_FIELDS.map((f) => f.key),
  ...MICRO_FIELDS.map((f) => f.key),
];

// rascunho editável — reidratado toda vez que o painel abre (não vazar o produto
// anterior). Listas (keywords, alérgenos, hashtags) vivem como texto livre e viram
// lista ao salvar. O preço é editado em reais (vírgula) e volta a centavos no patch.
const draft = reactive({
  name: "",
  short_description: "",
  long_description: "",
  keywordsText: "",
  image_url: "",
  priceText: "",
  unit: "",
  unit_weight_g: "" as number | "",
  availability_policy: "planned_ok",
  shelf_life_days: "" as number | "",
  storage_tip: "",
  production_cycle_hours: "" as number | "",
  is_batch_produced: false,
  is_published: true,
  is_sellable: true,
  allows_next_day_sale: false,
  ingredients_text: "",
  allergensText: "",
  dietaryText: "",
  serves: "",
  approx_dimensions: "",
  nutrition: {} as Record<string, number | "">,
  social: {
    brand: "",
    gtin: "",
    mpn: "",
    condition: "new",
    google_product_category: "",
    tiktok_category_id: "",
    hashtagsText: "",
    social_caption: "",
  },
  fiscal: { profile: "standard", ncm: "", cest: "", unit: "UN", origin: "0" },
  // Vocação (etiqueta de consumo do SKU): ref do papel, "" = sem vocação.
  vocation: "",
});

const centsToText = (q: number) => (q / 100).toFixed(2).replace(".", ",");
const numOrBlank = (v: number | null) => (v === null || v === undefined ? "" : v);

function hydrate(detail: ProductDetailProjection | null) {
  draft.name = detail?.name ?? "";
  draft.short_description = detail?.short_description ?? "";
  draft.long_description = detail?.long_description ?? "";
  draft.keywordsText = (detail?.keywords ?? []).join(", ");
  draft.image_url = detail?.image_url ?? "";
  draft.priceText = centsToText(detail?.base_price_q ?? 0);
  draft.unit = detail?.unit ?? "un";
  draft.unit_weight_g = numOrBlank(detail?.unit_weight_g ?? null);
  draft.availability_policy = detail?.availability_policy || "planned_ok";
  draft.shelf_life_days = numOrBlank(detail?.shelf_life_days ?? null);
  draft.storage_tip = detail?.storage_tip ?? "";
  draft.production_cycle_hours = numOrBlank(detail?.production_cycle_hours ?? null);
  draft.is_batch_produced = detail?.is_batch_produced ?? false;
  draft.is_published = detail?.is_published ?? true;
  draft.is_sellable = detail?.is_sellable ?? true;
  draft.allows_next_day_sale = detail?.allows_next_day_sale ?? false;
  draft.ingredients_text = detail?.ingredients_text ?? "";
  draft.allergensText = (detail?.allergens ?? []).join(", ");
  draft.dietaryText = (detail?.dietary_info ?? []).join(", ");
  draft.serves = detail?.serves ?? "";
  draft.approx_dimensions = detail?.approx_dimensions ?? "";

  const facts = detail?.nutrition_facts;
  const nutrition: Record<string, number | ""> = {};
  for (const key of NUTRITION_KEYS) {
    const value = facts?.[key];
    // 0 é valor legítimo (gordura trans zero é uma afirmação do rótulo), então só
    // null/undefined viram campo vazio.
    nutrition[key] = value === null || value === undefined ? "" : value;
  }
  draft.nutrition = nutrition;

  const s = detail?.social;
  draft.social.brand = s?.brand ?? "";
  draft.social.gtin = s?.gtin ?? "";
  draft.social.mpn = s?.mpn ?? "";
  draft.social.condition = s?.condition || "new";
  draft.social.google_product_category = s?.google_product_category ?? "";
  draft.social.tiktok_category_id = s?.tiktok_category_id ?? "";
  draft.social.hashtagsText = (s?.hashtags ?? []).join(" ");
  draft.social.social_caption = s?.social_caption ?? "";

  const f = detail?.fiscal;
  draft.fiscal.profile = f?.profile || "standard";
  draft.fiscal.ncm = f?.ncm ?? "";
  draft.fiscal.cest = f?.cest ?? "";
  draft.fiscal.unit = f?.unit || "UN";
  draft.fiscal.origin = f?.origin || "0";

  draft.vocation = detail?.vocation ?? "";
}

watch(
  () => [props.open, props.sku, props.detail],
  () => {
    if (props.open) hydrate(props.detail);
  },
  { immediate: true },
);
const isTabId = (value: string | undefined): value is TabId =>
  TABS.some((t) => t.id === value);

watch(
  () => props.open,
  (isOpen) => { if (isOpen) tab.value = isTabId(props.initialTab) ? props.initialTab : "geral"; },
);

const fiscalProfiles = computed(() => props.detail?.fiscal_profiles ?? []);
const vocationChoices = computed(() => vocationOptions(props.detail?.vocation_choices));
const activeFiscalProfile = computed(
  () => fiscalProfiles.value.find((p) => p.key === draft.fiscal.profile) ?? null,
);

// "pão, artesanal caseiro" → ["pão", "artesanal caseiro"] (vírgula separa; espaço não).
function parseCommaList(text: string): string[] {
  const out: string[] = [];
  for (const raw of text.split(",")) {
    const item = raw.trim();
    if (item && !out.includes(item)) out.push(item);
  }
  return out;
}

// hashtags: "pão, #artesanal caseiro" → ["pão","artesanal","caseiro"].
function parseHashtags(text: string): string[] {
  const out: string[] = [];
  for (const raw of text.replace(/,/g, " ").split(/\s+/)) {
    const tag = raw.replace(/^#+/, "").trim();
    if (tag && !out.includes(tag)) out.push(tag);
  }
  return out;
}

function parseBrl(text: string): number | null {
  const cleaned = text.replace(/[^0-9,.-]/g, "").replace(/\./g, "").replace(",", ".");
  const value = Number.parseFloat(cleaned);
  return Number.isFinite(value) && value >= 0 ? Math.round(value * 100) : null;
}

const priceInvalid = computed(() => parseBrl(draft.priceText) === null);

// NCM/CEST são textuais (zero à esquerda conta) e de tamanho fixo. Validamos aqui
// só para avisar cedo; quem manda é o backend (fiscalman).
const ncmInvalid = computed(() => draft.fiscal.ncm !== "" && !/^\d{8}$/.test(draft.fiscal.ncm));
const cestInvalid = computed(() => draft.fiscal.cest !== "" && !/^\d{7}$/.test(draft.fiscal.cest));
const cestRequired = computed(
  () => !!activeFiscalProfile.value?.requires_cest && draft.fiscal.cest.trim() === "",
);

const nullableInt = (v: number | "") => (v === "" ? null : Number(v));
const sameList = (a: string[], b: string[]) => a.length === b.length && a.every((x) => b.includes(x));

// Só o que mudou entra no patch — merge parcial no backend.
function buildPatch(): ProductDetailPatch {
  const current = props.detail;
  const patch: ProductDetailPatch = {};
  if (!current) return patch;

  const put = <K extends keyof ProductDetailPatch>(key: K, next: ProductDetailPatch[K], prev: unknown) => {
    if (next !== prev) patch[key] = next;
  };

  put("name", draft.name.trim(), current.name);
  put("short_description", draft.short_description.trim(), current.short_description);
  put("long_description", draft.long_description.trim(), current.long_description);
  put("image_url", draft.image_url.trim(), current.image_url);
  put("unit", draft.unit.trim(), current.unit);
  put("storage_tip", draft.storage_tip.trim(), current.storage_tip);
  put("ingredients_text", draft.ingredients_text.trim(), current.ingredients_text);
  put("availability_policy", draft.availability_policy, current.availability_policy);
  put("unit_weight_g", nullableInt(draft.unit_weight_g), current.unit_weight_g);
  put("shelf_life_days", nullableInt(draft.shelf_life_days), current.shelf_life_days);
  put("production_cycle_hours", nullableInt(draft.production_cycle_hours), current.production_cycle_hours);
  put("is_batch_produced", draft.is_batch_produced, current.is_batch_produced);
  put("is_published", draft.is_published, current.is_published);
  put("is_sellable", draft.is_sellable, current.is_sellable);
  put("allows_next_day_sale", draft.allows_next_day_sale, current.allows_next_day_sale);
  put("serves", draft.serves.trim(), current.serves);
  put("approx_dimensions", draft.approx_dimensions.trim(), current.approx_dimensions);
  put("vocation", draft.vocation, current.vocation ?? "");

  const price_q = parseBrl(draft.priceText);
  if (price_q !== null && price_q !== current.base_price_q) patch.base_price_q = price_q;

  const keywords = parseCommaList(draft.keywordsText);
  if (!sameList(keywords, current.keywords)) patch.keywords = keywords;

  const allergens = parseCommaList(draft.allergensText);
  if (!sameList(allergens, current.allergens)) patch.allergens = allergens;

  const dietary = parseCommaList(draft.dietaryText);
  if (!sameList(dietary, current.dietary_info)) patch.dietary_info = dietary;

  // nutricional — só as chaves alteradas
  const nutrition: Record<string, number> = {};
  for (const key of NUTRITION_KEYS) {
    const raw = draft.nutrition[key];
    const next = raw === "" ? null : Number(raw);
    const prev = current.nutrition_facts?.[key] ?? null;
    if (next !== prev && next !== null) nutrition[key] = next;
  }
  if (Object.keys(nutrition).length) patch.nutrition_facts = nutrition as ProductDetailPatch["nutrition_facts"];

  // social — só as chaves alteradas
  const social: Record<string, unknown> = {};
  const s = current.social;
  if (draft.social.brand.trim() !== s.brand) social.brand = draft.social.brand.trim();
  if (draft.social.gtin.trim() !== s.gtin) social.gtin = draft.social.gtin.trim();
  if (draft.social.mpn.trim() !== s.mpn) social.mpn = draft.social.mpn.trim();
  if (draft.social.condition !== s.condition) social.condition = draft.social.condition;
  if (draft.social.google_product_category.trim() !== s.google_product_category)
    social.google_product_category = draft.social.google_product_category.trim();
  if (draft.social.tiktok_category_id.trim() !== s.tiktok_category_id)
    social.tiktok_category_id = draft.social.tiktok_category_id.trim();
  if (draft.social.social_caption.trim() !== s.social_caption)
    social.social_caption = draft.social.social_caption.trim();
  const hashtags = parseHashtags(draft.social.hashtagsText);
  if (!sameList(hashtags, s.hashtags)) social.hashtags = hashtags;
  if (Object.keys(social).length) patch.social = social as ProductDetailPatch["social"];

  // fiscal — só as chaves alteradas
  const fiscal: Record<string, string> = {};
  const f = current.fiscal;
  if (draft.fiscal.profile !== f.profile) fiscal.profile = draft.fiscal.profile;
  if (draft.fiscal.ncm.trim() !== f.ncm) fiscal.ncm = draft.fiscal.ncm.trim();
  if (draft.fiscal.cest.trim() !== f.cest) fiscal.cest = draft.fiscal.cest.trim();
  if (draft.fiscal.unit.trim() !== f.unit) fiscal.unit = draft.fiscal.unit.trim();
  if (draft.fiscal.origin !== (f.origin || "0")) fiscal.origin = draft.fiscal.origin;
  if (Object.keys(fiscal).length) patch.fiscal = fiscal as ProductDetailPatch["fiscal"];

  return patch;
}

const patchSize = computed(() => Object.keys(buildPatch()).length);
watch(() => props.open && patchSize.value > 0, dirty => emit("dirty-change", dirty), { immediate: true, flush: "sync" });
const formInvalid = computed(() => priceInvalid.value || ncmInvalid.value || cestInvalid.value);
const canSave = computed(() => !props.busy && !props.loading && !props.conflict && !formInvalid.value && patchSize.value > 0);

function onSave() {
  if (!canSave.value) return;
  emit("save", buildPatch());
}

// GTIN recusado pela SEFAZ. A nota já saiu de novo sem GTIN; o que falta é
// alguém com a embalagem na mão. Código diferente: corrige o campo e salva.
// Mesmo código, ou produto sem código de barras: "Manter sem GTIN na nota",
// que salva junto o que mais estiver no rascunho.
const gtinRejected = computed(() => props.detail?.gtin_rejected ?? null);
const gtinRejectedWhen = computed(() => {
  const at = new Date(gtinRejected.value?.at ?? "");
  return Number.isNaN(at.getTime()) ? "" : at.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
});
const gtinStillRejected = computed(() =>
  !!gtinRejected.value && draft.social.gtin.trim() === gtinRejected.value.gtin);
const canKeepWithoutGtin = computed(() =>
  !!gtinRejected.value && !gtinRejected.value.confirmed && gtinStillRejected.value
  && !props.busy && !props.loading && !props.conflict && !formInvalid.value);
function keepWithoutGtin() {
  if (!canKeepWithoutGtin.value) return;
  emit("save", { ...buildPatch(), gtin_rejected: { confirmed: true } });
}

const discardRequested = ref(false);
function requestClose(open: boolean) {
  if (!open && props.busy) return;
  if (!open && patchSize.value) { discardRequested.value = true; return; }
  emit("update:open", open);
}
watch(() => props.open, () => { discardRequested.value = false; });
const conflictLabels: Record<string, string> = {
  name: "Nome", short_description: "Descrição curta", long_description: "Descrição completa",
  keywords: "Palavras-chave", image_url: "Imagem", base_price_q: "Preço",
  unit: "Unidade", unit_weight_g: "Peso por unidade", availability_policy: "Disponibilidade",
  shelf_life_days: "Validade", storage_tip: "Conservação", production_cycle_hours: "Tempo de produção",
  is_batch_produced: "Produção em lote", is_published: "Publicado", is_sellable: "Disponível para venda",
  allows_next_day_sale: "Venda no dia seguinte", ingredients_text: "Ingredientes", allergens: "Alérgenos",
  dietary_info: "Informações alimentares", serves: "Rendimento", approx_dimensions: "Dimensões",
  "social.brand": "Marca", "social.gtin": "GTIN", "social.mpn": "Código do fabricante",
  "social.condition": "Condição", "social.google_product_category": "Categoria Google",
  "social.tiktok_category_id": "Categoria TikTok", "social.hashtags": "Hashtags",
  "social.social_caption": "Legenda", "fiscal.profile": "Perfil fiscal", "fiscal.ncm": "NCM",
  "fiscal.cest": "CEST", "fiscal.unit": "Unidade fiscal", vocation: "Vocação",
  ...Object.fromEntries([...SERVING_FIELDS, ...MACRO_FIELDS, ...MICRO_FIELDS].map(f => [`nutrition_facts.${f.key}`, f.label])),
};
function sourceChange(field: string): string {
  const root = field.split(".")[0]!;
  const before = props.detail?.field_sources?.[root];
  const after = props.conflict?.product.field_sources?.[root];
  if (before === after) return "";
  const label = (value?: string) => value === "recipe" ? "ficha técnica" : value === "manual" ? "edição manual" : value || "não informada";
  return `Origem: ${label(before)} → ${label(after)}.`;
}

function currentValue(path: string): string {
  if (path === "vocation") return vocationLabel(props.conflict?.product.vocation ?? "", props.conflict?.product.vocation_choices);
  let value: unknown = props.conflict?.product;
  for (const part of path.split(".")) {
    value = value && typeof value === "object" ? (value as Record<string, unknown>)[part] : undefined;
  }
  if (value === null || value === undefined || value === "") return "Não informado";
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (path === "base_price_q" && typeof value === "number") return `R$ ${centsToText(value)}`;
  return Array.isArray(value) ? value.join(", ") : String(value);
}

const fieldClass =
  "min-h-control w-full rounded-md border border-border bg-background px-2.5 text-sm outline-none focus:ring-1 focus:ring-ring";
const areaClass =
  "w-full rounded-md border border-border bg-background px-2.5 py-2 text-sm outline-none focus:ring-1 focus:ring-ring";
const labelClass = "mb-1 block text-xs font-medium text-muted-foreground";
const sectionClass = "text-xs font-medium uppercase tracking-wide text-muted-foreground";
</script>

<template>
  <UiSheet :open="open" @update:open="requestClose">
    <UiSheetContent side="right" class="w-full gap-0 p-0 sm:max-w-[520px]" :title="undefined" @open-auto-focus.prevent>
      <!-- o ✕ é do cabeçalho do painel, ao lado do ⋯ (v4), não o canto padrão da folha -->
      <template #close><span class="hidden" /></template>
      <!-- Cabeçalho do painel (prévia v4 `catalogo-produto4.html`): a inicial do
           produto num quadrado, o nome e a linha do que ele é; ⋯ e ✕ à direita. -->
      <div class="flex items-center gap-3 border-b border-border px-5 py-4">
        <span class="grid size-12 shrink-0 place-items-center rounded-lg bg-primary text-lg font-semibold text-primary-foreground" aria-hidden="true">
          {{ (detail?.name || sku || "?").charAt(0).toUpperCase() }}
        </span>
        <div class="min-w-0">
          <p class="sr-only">Editar produto</p>
          <h2 class="truncate text-xl leading-tight font-semibold text-foreground">{{ detail?.name || "Produto" }}</h2>
          <p class="flex min-w-0 flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground" data-panel-subtitle>
            <span class="font-mono">{{ sku }}</span>
            <template v-if="detail">
              <span aria-hidden="true">·</span>
              <span class="tnum">R$ {{ centsToText(detail.base_price_q) }}{{ detail.unit === "kg" ? "/kg" : "" }}</span>
            </template>
            <template v-if="detail?.primary_collection_name">
              <span aria-hidden="true">·</span>
              <span>{{ detail.primary_collection_name }}</span>
            </template>
            <template v-for="badge in roleBadges" :key="badge">
              <span aria-hidden="true">·</span>
              <span>{{ badge }}</span>
            </template>
          </p>
        </div>
        <UiPopover v-model:open="headerMenuOpen">
          <UiPopoverTrigger as-child>
            <button
              type="button"
              class="grid size-control place-items-center rounded-md border border-border bg-card text-foreground transition hover:bg-accent"
              aria-label="Mais ações do produto"
              data-panel-more
            >
              <Icon name="lucide:ellipsis" class="size-5" />
            </button>
          </UiPopoverTrigger>
          <UiPopoverContent v-if="headerMenuOpen" align="end" :side-offset="6" class="w-60 rounded-lg p-1.5 shadow-lg" role="menu" data-panel-menu>
            <button type="button" role="menuitem" class="flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left text-sm transition hover:bg-accent" :disabled="!detail" @click="toggleHidden">
              <Icon :name="draft.is_published ? 'lucide:eye-off' : 'lucide:eye'" class="size-4 text-muted-foreground" />{{ draft.is_published ? "Ocultar no catálogo" : "Exibir no catálogo" }}
            </button>
            <button type="button" role="menuitem" class="flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left text-sm transition hover:bg-accent disabled:opacity-50" :disabled="purchaseBusy || !roles" @click="togglePurchaseFromMenu">
              <Icon name="lucide:shopping-basket" class="size-4 text-muted-foreground" />{{ roles?.purchasable ? "Tirar a permissão de compra" : "Permitir compra" }}
            </button>
            <a v-if="historyHref" :href="historyHref" target="_blank" rel="noopener" role="menuitem" class="flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-sm transition hover:bg-accent" data-panel-history>
              <Icon name="lucide:history" class="size-4 text-muted-foreground" />Histórico
            </a>
          </UiPopoverContent>
        </UiPopover>
        <button
          type="button"
          class="grid size-control shrink-0 place-items-center rounded-md text-muted-foreground transition hover:bg-accent hover:text-foreground"
          aria-label="Fechar o painel"
          data-panel-close
          @click="requestClose(false)"
        >
          <Icon name="lucide:x" class="size-5" />
        </button>
      </div>

      <div v-if="conflict" role="alert" class="space-y-2 border-b border-border bg-muted p-4 text-sm">
        <p>Seu rascunho foi preservado. Confira os campos que mudaram desde sua leitura:</p>
        <ul><li v-for="field in conflict.conflicting_fields" :key="field">
          {{ conflictLabels[field] || "Campo editado" }}. Valor atual: {{ currentValue(field) }}
          <span v-if="sourceChange(field)" class="block text-xs">{{ sourceChange(field) }}</span>
        </li></ul>
        <button type="button" class="min-h-12 rounded border px-3" @click="emit('review-conflict', true)">Manter meu rascunho</button>
        <button type="button" class="min-h-12 rounded border px-3" @click="emit('review-conflict', false)">Descartar minhas alterações e usar valores atuais</button>
      </div>
      <p v-else-if="error" role="alert" class="p-4 text-sm text-destructive">{{ error }}</p>
      <div v-if="discardRequested" role="alert" class="space-y-2 border-b p-4 text-sm">
        <p>Há alterações não salvas neste produto.</p>
        <button type="button" class="min-h-12 rounded border px-3" @click="discardRequested = false">Continuar editando</button>
        <button type="button" class="min-h-12 rounded border px-3" @click="emit('update:open', false)">Descartar e fechar</button>
      </div>

      <!-- abas: o formulário é longo demais para uma coluna só. Rolam na horizontal
           porque cinco rótulos não cabem na largura do slide-over. -->
      <!-- as cinco abas cabem (v4): sublinhada a ativa, sem caixa; rola só se a largura faltar -->
      <UiTabs v-model="tab">
        <UiTabsList class="flex w-full justify-between gap-0 overflow-x-auto rounded-none border-x-0 border-t-0 bg-transparent px-3 py-0 no-scrollbar" aria-label="Partes do produto" data-panel-tabs>
          <UiTabsTrigger
            v-for="t in TABS"
            :key="t.id"
            :value="t.id"
            class="min-h-12 shrink-0 rounded-none px-2 whitespace-nowrap data-[state=active]:shadow-[inset_0_-2px_0_var(--primary)]"
          >{{ t.label }}</UiTabsTrigger>
        </UiTabsList>
      </UiTabs>

      <div ref="bodyEl" class="flex-1 overflow-y-auto px-5 py-4">
        <div v-if="loading" class="flex items-center gap-2 py-8 text-sm text-muted-foreground">
          <Icon name="line-md:loading-loop" class="size-4" /> Carregando produto…
        </div>

        <div v-else-if="!detail" class="py-8 text-sm text-muted-foreground">
          Não foi possível carregar este produto.
        </div>

        <template v-else>
          <!-- Geral -->
          <div v-show="tab === 'geral'" class="space-y-4">
            <!-- A Geral começa pelo nome no cardápio (v4); a disponibilidade vem logo abaixo. -->
            <label class="block">
              <span :class="labelClass">Nome no cardápio</span>
              <input v-model="draft.name" :class="fieldClass" type="text" placeholder="Ex.: Pão francês" />
            </label>

            <!-- Disponibilidade nos canais (v4): um estado só, a hora provável de volta e o
                 porquê; por canal, o que o cliente vê ali e o Pausar (o mesmo gesto da
                 célula da tabela). O motivo da pausa não é gravado (decisão do dono). -->
            <section
              v-if="availability.length"
              class="overflow-hidden rounded-lg border"
              :class="unavailableCount ? 'border-destructive/30' : 'border-border'"
              data-panel-availability
            >
              <div class="px-3.5 py-3" :class="unavailableCount ? 'bg-destructive/6' : 'bg-muted/40'">
                <div class="flex flex-wrap items-center gap-2">
                  <h3 class="text-sm font-semibold">Disponibilidade nos canais</h3>
                  <span v-if="unavailableCount" class="pill-destructive inline-flex h-6 items-center gap-1.5 rounded-full px-2 text-xs font-semibold">
                    <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />{{ availabilityHeadline }}
                  </span>
                  <span v-else class="pill-success inline-flex h-6 items-center rounded-full px-2 text-xs font-semibold">À venda em todos</span>
                  <span class="ml-auto text-xs text-muted-foreground">vale na hora</span>
                </div>
                <p v-if="unavailableCount && detail?.back_at" class="mt-1 text-xs text-muted-foreground" data-panel-back>
                  Volta <b class="text-foreground">~{{ detail.back_at }}</b>: {{ detail.back_reason }}. Segue o estoque em todos os canais.
                </p>
              </div>
              <div v-for="row in availability" :key="row.ref" class="flex min-h-12 items-center gap-3 border-t border-border px-3.5 py-2" data-panel-channel>
                <Icon :name="channelIcon(row)" class="size-4 shrink-0 text-muted-foreground" />
                <span class="w-28 shrink-0 text-sm">{{ row.name }}</span>
                <span class="min-w-0 flex-1 text-xs">
                  <span class="block">
                    <b v-if="row.state !== 'available'" class="font-semibold text-destructive">{{ row.state === "paused" ? "Pausado" : row.kind === "display" ? "Fora de estoque" : "Esgotado" }}</b>
                    <span v-else class="text-muted-foreground">À venda</span>
                    <span v-if="row.back_at" class="text-muted-foreground"> · volta ~{{ row.back_at }}<template v-if="row.back_hint"> ({{ row.back_hint }})</template></span>
                    <span v-else-if="row.since" class="text-muted-foreground"> desde {{ row.since }}</span>
                  </span>
                  <span v-if="row.note || (row.automatic && row.state !== 'available')" class="mt-0.5 flex flex-wrap items-center gap-1.5 text-muted-foreground" data-panel-channel-note>
                    <span v-if="row.automatic && row.state !== 'available'" class="inline-flex h-5 items-center gap-1 rounded-full bg-muted px-1.5 font-semibold"><Icon name="lucide:sparkles" class="size-3" />automático</span>
                    <span v-if="row.note">{{ row.note }}</span>
                  </span>
                </span>
                <button
                  v-if="channelCells?.[row.ref]"
                  type="button"
                  class="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-md border border-border bg-card px-3 text-sm font-semibold transition hover:bg-accent disabled:opacity-50"
                  :disabled="!channelCells[row.ref]!.enabled || channelCells[row.ref]!.busy"
                  :aria-label="channelCells[row.ref]!.paused ? `Retomar ${row.name}` : `Pausar ${row.name}`"
                  data-panel-pause
                  @click="emit('pause-channel', row.ref, !channelCells[row.ref]!.paused)"
                >
                  <Icon :name="channelCells[row.ref]!.paused ? 'lucide:play' : 'lucide:pause'" class="size-4" />{{ channelCells[row.ref]!.paused ? "Retomar" : "Pausar" }}
                </button>
              </div>
              <p class="flex items-start gap-1.5 border-t border-border px-3.5 py-2 text-xs text-muted-foreground">
                <Icon name="lucide:sparkles" class="mt-0.5 size-3 shrink-0" />
                O sistema avisa o iFood, a Meta e o Google sozinho quando o estoque zera e quando volta. Pausar é para o que não é falta de estoque.
              </p>
            </section>

            <div ref="belowEl" class="scroll-mt-4" />
            <CatalogAiSuggest
              :sku="sku"
              field="short_description"
              label="Descrição curta"
              :current="draft.short_description"
              :busy="assistBusy('short_description')"
              :assist="assist"
              @accept="(text) => (draft.short_description = text)"
            >
              <input
                v-model="draft.short_description" :class="fieldClass" type="text" maxlength="255"
                placeholder="Uma linha para listagens e vitrine"
              />
              <span class="mt-1 block text-xs text-muted-foreground">{{ draft.short_description.length }}/255</span>
            </CatalogAiSuggest>

            <CatalogAiSuggest
              :sku="sku"
              field="long_description"
              label="Descrição longa"
              :current="draft.long_description"
              :busy="assistBusy('long_description')"
              :assist="assist"
              @accept="(text) => (draft.long_description = text)"
            >
              <textarea v-model="draft.long_description" rows="5" :class="areaClass" placeholder="Texto completo da página do produto."></textarea>
            </CatalogAiSuggest>

            <label class="block">
              <span :class="labelClass">Palavras-chave</span>
              <input v-model="draft.keywordsText" :class="fieldClass" type="text" placeholder="padaria, pão artesanal, fermentação natural" />
              <span class="mt-1 block text-xs text-muted-foreground">Separe por vírgula. Usadas em busca e SEO.</span>
            </label>

            <label class="block">
              <span :class="labelClass">URL da imagem</span>
              <input v-model="draft.image_url" :class="fieldClass" type="url" placeholder="https://…" />
            </label>
            <img
              v-if="draft.image_url"
              :src="draft.image_url" alt="Prévia da imagem do produto"
              class="h-32 w-32 rounded-lg border border-border object-cover"
            />
          </div>

          <!-- Preço e config -->
          <div v-show="tab === 'config'" class="space-y-4">
            <!-- Vendido por peso: a unidade de venda vira kg e o MESMO campo de
                 preço passa a ser o preço do quilo. O preço final sai da balança
                 do balcão, então o item não vai para canal remoto. -->
            <UiCheckbox
              :model-value="soldByWeight"
              label="Vendido por peso"
              data-testid="sold-by-weight"
              @update:model-value="setSoldByWeight"
            />
            <p v-if="soldByWeight" class="-mt-2 text-xs text-muted-foreground">Vendido só no balcão: o preço final sai da balança.</p>

            <div class="grid grid-cols-2 gap-3">
              <label class="block">
                <span :class="labelClass">{{ soldByWeight ? "Preço por kg" : "Preço" }}</span>
                <input
                  v-model="draft.priceText" :class="fieldClass" type="text" inputmode="decimal" placeholder="0,00"
                  :aria-invalid="priceInvalid"
                />
                <span v-if="priceInvalid" class="mt-1 block text-xs text-destructive">Informe um valor válido.</span>
              </label>
              <label v-if="!soldByWeight" class="block">
                <span :class="labelClass">Unidade</span>
                <input v-model="draft.unit" :class="fieldClass" type="text" placeholder="un, lt" />
              </label>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <label class="block">
                <span :class="labelClass">Peso por unidade (g)</span>
                <input v-model="draft.unit_weight_g" :class="fieldClass" type="number" min="0" placeholder="Ex.: 150" />
              </label>
              <label class="block">
                <span :class="labelClass">Validade (dias)</span>
                <input v-model="draft.shelf_life_days" :class="fieldClass" type="number" min="0" placeholder="Vazio = não perece" />
              </label>
            </div>

            <label class="block">
              <span :class="labelClass">Política de disponibilidade</span>
              <UiNativeSelect v-model="draft.availability_policy" class="w-full">
                <option v-for="p in POLICIES" :key="p.value" :value="p.value">{{ p.label }}</option>
              </UiNativeSelect>
            </label>

            <label class="block">
              <span :class="labelClass">Dica de conservação</span>
              <input v-model="draft.storage_tip" :class="fieldClass" type="text" maxlength="300" placeholder="Ex.: guarde em saco de pano por até 2 dias" />
            </label>

            <label class="block">
              <span :class="labelClass">Ciclo de produção (horas)</span>
              <input v-model="draft.production_cycle_hours" :class="fieldClass" type="number" min="0" placeholder="Ex.: 4" />
            </label>

            <UiCheckbox v-model="draft.is_batch_produced" label="Produzido em lote" />

            <UiCheckbox v-model="draft.allows_next_day_sale" label="Pode ser vendido no dia seguinte" />

            <!-- Permitir compra: o cadastro de compra do MESMO SKU (mesmo estoque).
                 Vale na hora, fora do "Salvar" — é interruptor, não rascunho. -->
            <div class="space-y-2 rounded-lg border border-border p-3" data-testid="purchase-toggle">
              <p :class="sectionClass">Compra</p>
              <div v-if="roleBadges.length" class="flex flex-wrap gap-1">
                <span v-for="badge in roleBadges" :key="badge" class="rounded border border-border px-1.5 py-0.5 text-xs text-muted-foreground">{{ badge }}</span>
              </div>
              <p v-if="roles?.produced && !roles?.purchasable" class="text-xs text-muted-foreground">
                É produzido aqui: o estoque entra pela Produção, não pela compra.
              </p>
              <UiCheckbox
                v-else
                :model-value="Boolean(roles?.purchasable)"
                :disabled="purchaseBusy || !roles"
                label="Permitir compra"
                @update:model-value="onPurchaseChange"
              />
              <p v-if="roles?.purchasable" class="text-xs text-muted-foreground">
                Aparece no Compras: recebe nota, tem custo, mínimo e pedido.
              </p>
            </div>

            <!-- Vocação: o que a presença do produto na cesta diz ao B.I. (consumo
                 aqui × levar). Não muda a venda, por isso fica discreta, aqui e não
                 na aba Geral. Entra no rascunho: grava no "Salvar". -->
            <fieldset class="space-y-1.5" data-testid="vocation">
              <legend class="flex w-full items-baseline justify-between gap-2">
                <span :class="labelClass">Vocação</span>
                <span class="text-xs text-muted-foreground">só para o B.I.</span>
              </legend>
              <UiRadioGroup v-if="vocationChoices.length" v-model="draft.vocation" label="Vocação" class="grid-cols-2 gap-x-3 gap-y-0 sm:grid-cols-3">
                <UiRadio
                  v-for="option in vocationChoices" :key="option.value"
                  :value="option.value" :label="option.label" :title="option.hint || undefined" variant="inline"
                />
              </UiRadioGroup>
              <p v-else class="text-xs text-muted-foreground">Nenhuma vocação cadastrada. O cadastro fica no Admin.</p>
              <button
                v-if="draft.vocation" type="button"
                class="min-h-control text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
                @click="draft.vocation = ''"
              >
                Deixar sem vocação
              </button>
              <p v-else-if="vocationChoices.length" class="text-xs text-muted-foreground">Sem vocação: o B.I. não classifica as vendas deste produto.</p>
            </fieldset>

            <div class="space-y-2 rounded-lg border border-border p-3">
              <p :class="sectionClass">Visibilidade</p>
              <UiCheckbox v-model="draft.is_published" label="Exibido no catálogo" />
              <UiCheckbox v-model="draft.is_sellable" label="Disponível para venda" />
            </div>
          </div>

          <!-- Ingredientes e nutrição -->
          <div v-show="tab === 'rotulagem'" class="space-y-5">
            <CatalogAiSuggest
              :sku="sku"
              field="ingredients_text"
              label="Ingredientes"
              :current="draft.ingredients_text"
              :busy="assistBusy('ingredients_text')"
              :assist="assist"
              hint="Em ordem decrescente de peso, como manda a ANVISA."
              @accept="(text) => (draft.ingredients_text = text)"
            >
              <textarea
                v-model="draft.ingredients_text" rows="6" :class="areaClass"
                placeholder="Farinha de trigo, água, fermento natural, sal marinho."
              ></textarea>
            </CatalogAiSuggest>

            <div class="space-y-3 rounded-lg border border-border p-3">
              <p :class="sectionClass">Rotulagem para compra remota</p>
              <p
                v-if="detail.dietary_from_recipe && (detail.allergens.length || detail.dietary_info.length)"
                class="rounded-md bg-muted/60 px-2.5 py-2 text-xs text-muted-foreground"
              >
                Alérgenos e restrições vieram da receita. Ao editar aqui, o produto passa a
                ignorar a receita e você fica responsável por manter estes campos.
              </p>

              <label class="block">
                <span :class="labelClass">Alérgenos</span>
                <input v-model="draft.allergensText" :class="fieldClass" type="text" placeholder="glúten, leite, gergelim" />
                <span class="mt-1 block text-xs text-muted-foreground">Separe por vírgula.</span>
              </label>

              <label class="block">
                <span :class="labelClass">Restrições atendidas</span>
                <input v-model="draft.dietaryText" :class="fieldClass" type="text" placeholder="100% vegetal, sem lactose" />
                <span class="mt-1 block text-xs text-muted-foreground">Separe por vírgula.</span>
              </label>

              <div class="grid grid-cols-2 gap-3">
                <label class="block">
                  <span :class="labelClass">Serve</span>
                  <input v-model="draft.serves" :class="fieldClass" type="text" placeholder="Ex.: 2 a 4 pessoas" />
                </label>
                <label class="block">
                  <span :class="labelClass">Medidas aproximadas</span>
                  <input v-model="draft.approx_dimensions" :class="fieldClass" type="text" placeholder="Ex.: aprox. 24 x 12 cm" />
                </label>
              </div>
            </div>

            <div class="space-y-3 rounded-lg border border-border p-3">
              <p :class="sectionClass">Tabela nutricional</p>
              <p v-if="detail.nutrition_auto_filled" class="rounded-md bg-muted/60 px-2.5 py-2 text-xs text-muted-foreground">
                Estes valores foram calculados a partir da receita. Ao editar, o cálculo
                automático para de valer para este produto.
              </p>

              <div class="grid grid-cols-2 gap-3">
                <label v-for="f in SERVING_FIELDS" :key="f.key" class="block">
                  <span :class="labelClass">{{ f.label }}</span>
                  <input v-model="draft.nutrition[f.key]" :class="fieldClass" type="number" min="0" :step="f.step" />
                </label>
              </div>

              <p class="pt-1 text-xs font-medium text-muted-foreground">Macronutrientes</p>
              <div class="grid grid-cols-2 gap-3">
                <label v-for="f in MACRO_FIELDS" :key="f.key" class="block">
                  <span :class="labelClass">{{ f.label }}</span>
                  <input v-model="draft.nutrition[f.key]" :class="fieldClass" type="number" min="0" :step="f.step" />
                </label>
              </div>

              <p class="pt-1 text-xs font-medium text-muted-foreground">Micronutrientes</p>
              <div class="grid grid-cols-2 gap-3">
                <label v-for="f in MICRO_FIELDS" :key="f.key" class="block">
                  <span :class="labelClass">{{ f.label }}</span>
                  <input v-model="draft.nutrition[f.key]" :class="fieldClass" type="number" min="0" :step="f.step" />
                </label>
              </div>

              <p class="text-xs text-muted-foreground">
                Preencher qualquer nutriente exige informar a porção. Gorduras trans e saturadas
                não podem passar das totais, nem açúcares dos carboidratos.
              </p>
            </div>
          </div>

          <!-- Redes sociais (PIM) -->
          <div v-show="tab === 'social'" class="space-y-4">
            <p class="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
              Atributos comerciais compartilhados pelos canais. As exigências variam por destino.
            </p>

            <label class="block">
              <span :class="labelClass">Marca</span>
              <input v-model="draft.social.brand" :class="fieldClass" type="text" placeholder="Ex.: Nelson Boulangerie" />
            </label>

            <div class="grid grid-cols-2 gap-3">
              <label class="block">
                <span :class="labelClass">GTIN / código de barras</span>
                <input v-model="draft.social.gtin" :class="fieldClass" type="text" inputmode="numeric" placeholder="8, 12, 13 ou 14 dígitos" />
              </label>
              <label class="block">
                <span :class="labelClass">Condição</span>
                <UiNativeSelect v-model="draft.social.condition" class="w-full">
                  <option v-for="c in CONDITIONS" :key="c.value" :value="c.value">{{ c.label }}</option>
                </UiNativeSelect>
              </label>
            </div>

            <div
              v-if="gtinRejected"
              class="space-y-2 rounded-lg border px-3 py-2 text-sm"
              :class="gtinRejected.confirmed ? 'border-border bg-muted/40' : 'border-amber-500/40 bg-amber-500/10'"
              data-gtin-rejected
            >
              <template v-if="gtinRejected.confirmed">
                <p data-gtin-rejected-confirmed>
                  Sai sem GTIN na NFC-e. A SEFAZ recusou o código {{ gtinRejected.gtin }}, e {{ gtinRejected.confirmed_by || "o gestor" }} conferiu a embalagem.
                  Para voltar a mandar o GTIN, corrija o campo e salve.
                </p>
              </template>
              <template v-else>
                <p class="font-medium">
                  A SEFAZ recusou o GTIN {{ gtinRejected.gtin }} na NFC-e do pedido {{ gtinRejected.order_ref }}<template v-if="gtinRejectedWhen">, em {{ gtinRejectedWhen }}</template>.
                </p>
                <p class="text-muted-foreground">
                  A nota saiu de novo sem GTIN, e o produto segue saindo assim até alguém conferir. Compare com o código da embalagem:
                  se for outro, corrija o campo e salve; se for o mesmo, ou se o produto não tiver código de barras, toque em Manter sem GTIN na nota.
                </p>
                <p v-if="gtinRejected.reason" class="text-xs text-muted-foreground" data-gtin-rejected-reason>
                  Motivo da SEFAZ (rejeição {{ gtinRejected.code }}): {{ gtinRejected.reason }}
                </p>
                <p v-if="!gtinStillRejected" class="text-xs" data-gtin-rejected-corrected>
                  Ao salvar, o código novo volta a ir na nota.
                </p>
                <button
                  v-else
                  type="button"
                  class="inline-flex min-h-control items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition-colors hover:bg-accent disabled:opacity-50"
                  :disabled="!canKeepWithoutGtin"
                  data-gtin-keep-without
                  @click="keepWithoutGtin"
                >
                  Manter sem GTIN na nota
                </button>
              </template>
            </div>

            <label class="block">
              <span :class="labelClass">MPN (código do fabricante)</span>
              <input v-model="draft.social.mpn" :class="fieldClass" type="text" placeholder="Opcional" />
            </label>

            <label class="block">
              <span :class="labelClass">Categoria Google</span>
              <input
                v-model="draft.social.google_product_category" :class="fieldClass" type="text"
                placeholder="Ex.: Food, Beverages & Tobacco > Food Items > Bakery"
              />
            </label>

            <label class="block">
              <span :class="labelClass">Categoria TikTok</span>
              <input v-model="draft.social.tiktok_category_id" :class="fieldClass" type="text" placeholder="ID da categoria (opcional)" />
            </label>

            <CatalogAiSuggest
              :sku="sku"
              field="hashtags"
              label="Hashtags"
              :current="draft.social.hashtagsText"
              :busy="assistBusy('hashtags')"
              :assist="assist"
              hint="Separe por espaço ou vírgula. O &quot;#&quot; é opcional."
              @accept="(text) => (draft.social.hashtagsText = text)"
            >
              <input v-model="draft.social.hashtagsText" :class="fieldClass" type="text" placeholder="pão artesanal caseiro" />
            </CatalogAiSuggest>

            <CatalogAiSuggest
              :sku="sku"
              field="social_caption"
              label="Legenda social"
              :current="draft.social.social_caption"
              :busy="assistBusy('social_caption')"
              :assist="assist"
              @accept="(text) => (draft.social.social_caption = text)"
            >
              <textarea
                v-model="draft.social.social_caption" rows="3" :class="areaClass"
                placeholder="Texto sugerido para posts e feeds."
              ></textarea>
            </CatalogAiSuggest>
          </div>

          <!-- Fiscal (NFC-e) -->
          <div v-show="tab === 'fiscal'" class="space-y-4">
            <p class="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
              Usado na emissão da NFC-e. CFOP, CSOSN e PIS/COFINS vêm do perfil; aqui fica
              só o que muda de produto para produto.
            </p>

            <label class="block">
              <span :class="labelClass">Perfil fiscal</span>
              <UiNativeSelect v-model="draft.fiscal.profile" class="w-full">
                <option v-for="p in fiscalProfiles" :key="p.key" :value="p.key">{{ p.name }}</option>
              </UiNativeSelect>
            </label>

            <div class="grid grid-cols-2 gap-3">
              <label class="block">
                <span :class="labelClass">NCM</span>
                <input
                  v-model="draft.fiscal.ncm" :class="fieldClass" type="text" inputmode="numeric"
                  maxlength="8" placeholder="8 dígitos" :aria-invalid="ncmInvalid"
                />
                <span v-if="ncmInvalid" class="mt-1 block text-xs text-destructive">NCM deve ter 8 dígitos.</span>
              </label>
              <label class="block">
                <span :class="labelClass">Unidade comercial</span>
                <input v-model="draft.fiscal.unit" :class="fieldClass" type="text" maxlength="6" placeholder="UN" />
              </label>
            </div>

            <label class="block">
              <span :class="labelClass">Origem da mercadoria</span>
              <UiNativeSelect v-model="draft.fiscal.origin" class="w-full">
                <option v-for="o in props.detail?.fiscal_origins ?? []" :key="o.key" :value="o.key">{{ o.name }}</option>
              </UiNativeSelect>
            </label>

            <label class="block">
              <span :class="labelClass">CEST</span>
              <input
                v-model="draft.fiscal.cest" :class="fieldClass" type="text" inputmode="numeric"
                maxlength="7" placeholder="7 dígitos" :aria-invalid="cestInvalid"
              />
              <span v-if="cestInvalid" class="mt-1 block text-xs text-destructive">CEST deve ter 7 dígitos.</span>
              <span v-else-if="cestRequired" class="mt-1 block text-xs text-amber-600 dark:text-amber-400">
                Obrigatório com substituição tributária.
              </span>
              <span v-else class="mt-1 block text-xs text-muted-foreground">
                Identificação da mercadoria; a tributação vem do perfil fiscal.
              </span>
              <span
                v-for="warning in props.detail?.fiscal_warnings ?? []" :key="warning"
                class="mt-1 block text-xs text-amber-600 dark:text-amber-400"
              >{{ warning }}</span>
            </label>
          </div>
        </template>
      </div>

      <!-- Rodapé (v4): o que ainda está abaixo na Geral, Descartar e "N campo alterado · Salvar". -->
      <div class="flex items-center justify-end gap-2 border-t border-border px-5 py-4">
        <button
          v-if="tab === 'geral' && detail && !belowVisible"
          type="button"
          class="mr-auto inline-flex min-h-control items-center gap-1 text-left text-xs text-muted-foreground transition hover:text-foreground"
          data-panel-below
          @click="showBelow"
        >Descrição e foto seguem abaixo <Icon name="lucide:chevron-down" class="size-4 shrink-0" /></button>
        <span v-else class="mr-auto" />
        <button
          type="button"
          class="min-h-control rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground"
          data-panel-discard
          @click="requestClose(false)"
        >Descartar</button>
        <button
          type="button"
          :disabled="!canSave"
          class="inline-flex min-h-action items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
          data-panel-save
          @click="onSave"
        >
          <Icon v-if="busy" name="line-md:loading-loop" class="size-4" />
          <span data-panel-changes>{{ patchSize ? `${patchSize} ${patchSize === 1 ? "campo alterado" : "campos alterados"} · Salvar` : "Salvar" }}</span>
        </button>
      </div>
    </UiSheetContent>
  </UiSheet>
</template>
