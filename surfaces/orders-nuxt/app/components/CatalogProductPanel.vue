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
  channelCells?: Record<
    string,
    { paused: boolean; enabled: boolean; busy: boolean }
  >;
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
  return path && props.adminBaseUrl
    ? `${props.adminBaseUrl.replace(/\/+$/, "").replace(/\/admin$/, "")}${path}`
    : "";
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
const belowEl = ref<HTMLElement | null>(null);
const belowVisible = ref(true);
useIntersectionObserver(belowEl, ([entry]) => {
  belowVisible.value = Boolean(entry?.isIntersecting);
});
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
const availability = computed(
  () => props.liveAvailability ?? props.detail?.channel_availability ?? [],
);
const unavailableCount = computed(
  () => availability.value.filter((row) => row.state !== "available").length,
);
const availabilityHeadline = computed(() => {
  const off = availability.value.filter((row) => row.state !== "available");
  const paused = off.some((row) => row.state === "paused");
  const since =
    off
      .map((row) => row.since)
      .filter(Boolean)
      .sort()[0] ?? "";
  const word = paused ? "Pausado" : "Esgotado";
  const where =
    off.length === availability.value.length
      ? ""
      : ` em ${off.length} de ${availability.value.length}`;
  return `${word}${where}${since ? ` desde ${since}` : ""}`;
});
function channelIcon(row: { ref: string; kind: string }): string {
  if (row.ref === "ifood") return "lucide:bike";
  if (row.ref === "pdv" || row.ref === "pos" || row.ref === "balcao")
    return "lucide:store";
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
const tabItems = TABS.map((item) => ({ value: item.id, label: item.label }));
const panelMenuItems = computed(() => [
  {
    label: draft.is_published ? "Ocultar no catálogo" : "Exibir no catálogo",
    icon: draft.is_published ? "i-lucide-eye-off" : "i-lucide-eye",
    disabled: !props.detail,
    onSelect: toggleHidden,
  },
  {
    label: props.roles?.purchasable
      ? "Tirar a permissão de compra"
      : "Permitir compra",
    icon: "i-lucide-shopping-basket",
    disabled: props.purchaseBusy || !props.roles,
    onSelect: togglePurchaseFromMenu,
  },
  ...(historyHref.value
    ? [
        {
          label: "Histórico",
          icon: "i-lucide-history",
          to: historyHref.value,
          target: "_blank",
        },
      ]
    : []),
]);
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
function setAvailabilityPolicy(value: string | number) {
  if (POLICIES.some((item) => item.value === value))
    draft.availability_policy = value as (typeof POLICIES)[number]["value"];
}
function setCondition(value: string | number) {
  if (CONDITIONS.some((item) => item.value === value))
    draft.social.condition = value as (typeof CONDITIONS)[number]["value"];
}
const availabilityPolicyValue = computed(
  () =>
    POLICIES.find((item) => item.value === draft.availability_policy)?.value,
);
const conditionValue = computed(
  () => CONDITIONS.find((item) => item.value === draft.social.condition)?.value,
);

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
const numOrBlank = (v: number | null) =>
  v === null || v === undefined ? "" : v;

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
  draft.production_cycle_hours = numOrBlank(
    detail?.production_cycle_hours ?? null,
  );
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
  (isOpen) => {
    if (isOpen)
      tab.value = isTabId(props.initialTab) ? props.initialTab : "geral";
  },
);

const fiscalProfiles = computed(() => props.detail?.fiscal_profiles ?? []);
const vocationChoices = computed(() =>
  vocationOptions(props.detail?.vocation_choices),
);
const activeFiscalProfile = computed(
  () =>
    fiscalProfiles.value.find((p) => p.key === draft.fiscal.profile) ?? null,
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
  const cleaned = text
    .replace(/[^0-9,.-]/g, "")
    .replace(/\./g, "")
    .replace(",", ".");
  const value = Number.parseFloat(cleaned);
  return Number.isFinite(value) && value >= 0 ? Math.round(value * 100) : null;
}

const priceInvalid = computed(() => parseBrl(draft.priceText) === null);

// NCM/CEST são textuais (zero à esquerda conta) e de tamanho fixo. Validamos aqui
// só para avisar cedo; quem manda é o backend (fiscalman).
const ncmInvalid = computed(
  () => draft.fiscal.ncm !== "" && !/^\d{8}$/.test(draft.fiscal.ncm),
);
const cestInvalid = computed(
  () => draft.fiscal.cest !== "" && !/^\d{7}$/.test(draft.fiscal.cest),
);
const cestRequired = computed(
  () =>
    !!activeFiscalProfile.value?.requires_cest &&
    draft.fiscal.cest.trim() === "",
);

const nullableInt = (v: number | "") => (v === "" ? null : Number(v));
const sameList = (a: string[], b: string[]) =>
  a.length === b.length && a.every((x) => b.includes(x));

// Só o que mudou entra no patch — merge parcial no backend.
function buildPatch(): ProductDetailPatch {
  const current = props.detail;
  const patch: ProductDetailPatch = {};
  if (!current) return patch;

  const put = <K extends keyof ProductDetailPatch>(
    key: K,
    next: ProductDetailPatch[K],
    prev: unknown,
  ) => {
    if (next !== prev) patch[key] = next;
  };

  put("name", draft.name.trim(), current.name);
  put(
    "short_description",
    draft.short_description.trim(),
    current.short_description,
  );
  put(
    "long_description",
    draft.long_description.trim(),
    current.long_description,
  );
  put("image_url", draft.image_url.trim(), current.image_url);
  put("unit", draft.unit.trim(), current.unit);
  put("storage_tip", draft.storage_tip.trim(), current.storage_tip);
  put(
    "ingredients_text",
    draft.ingredients_text.trim(),
    current.ingredients_text,
  );
  put(
    "availability_policy",
    draft.availability_policy,
    current.availability_policy,
  );
  put("unit_weight_g", nullableInt(draft.unit_weight_g), current.unit_weight_g);
  put(
    "shelf_life_days",
    nullableInt(draft.shelf_life_days),
    current.shelf_life_days,
  );
  put(
    "production_cycle_hours",
    nullableInt(draft.production_cycle_hours),
    current.production_cycle_hours,
  );
  put("is_batch_produced", draft.is_batch_produced, current.is_batch_produced);
  put("is_published", draft.is_published, current.is_published);
  put("is_sellable", draft.is_sellable, current.is_sellable);
  put(
    "allows_next_day_sale",
    draft.allows_next_day_sale,
    current.allows_next_day_sale,
  );
  put("serves", draft.serves.trim(), current.serves);
  put(
    "approx_dimensions",
    draft.approx_dimensions.trim(),
    current.approx_dimensions,
  );
  put("vocation", draft.vocation, current.vocation ?? "");

  const price_q = parseBrl(draft.priceText);
  if (price_q !== null && price_q !== current.base_price_q)
    patch.base_price_q = price_q;

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
  if (Object.keys(nutrition).length)
    patch.nutrition_facts = nutrition as ProductDetailPatch["nutrition_facts"];

  // social — só as chaves alteradas
  const social: Record<string, unknown> = {};
  const s = current.social;
  if (draft.social.brand.trim() !== s.brand)
    social.brand = draft.social.brand.trim();
  if (draft.social.gtin.trim() !== s.gtin)
    social.gtin = draft.social.gtin.trim();
  if (draft.social.mpn.trim() !== s.mpn) social.mpn = draft.social.mpn.trim();
  if (draft.social.condition !== s.condition)
    social.condition = draft.social.condition;
  if (draft.social.google_product_category.trim() !== s.google_product_category)
    social.google_product_category =
      draft.social.google_product_category.trim();
  if (draft.social.tiktok_category_id.trim() !== s.tiktok_category_id)
    social.tiktok_category_id = draft.social.tiktok_category_id.trim();
  if (draft.social.social_caption.trim() !== s.social_caption)
    social.social_caption = draft.social.social_caption.trim();
  const hashtags = parseHashtags(draft.social.hashtagsText);
  if (!sameList(hashtags, s.hashtags)) social.hashtags = hashtags;
  if (Object.keys(social).length)
    patch.social = social as ProductDetailPatch["social"];

  // fiscal — só as chaves alteradas
  const fiscal: Record<string, string> = {};
  const f = current.fiscal;
  if (draft.fiscal.profile !== f.profile) fiscal.profile = draft.fiscal.profile;
  if (draft.fiscal.ncm.trim() !== f.ncm) fiscal.ncm = draft.fiscal.ncm.trim();
  if (draft.fiscal.cest.trim() !== f.cest)
    fiscal.cest = draft.fiscal.cest.trim();
  if (draft.fiscal.unit.trim() !== f.unit)
    fiscal.unit = draft.fiscal.unit.trim();
  if (draft.fiscal.origin !== (f.origin || "0"))
    fiscal.origin = draft.fiscal.origin;
  if (Object.keys(fiscal).length)
    patch.fiscal = fiscal as ProductDetailPatch["fiscal"];

  return patch;
}

const patchSize = computed(() => Object.keys(buildPatch()).length);
watch(
  () => props.open && patchSize.value > 0,
  (dirty) => emit("dirty-change", dirty),
  { immediate: true, flush: "sync" },
);
const formInvalid = computed(
  () => priceInvalid.value || ncmInvalid.value || cestInvalid.value,
);
const canSave = computed(
  () =>
    !props.busy &&
    !props.loading &&
    !props.conflict &&
    !formInvalid.value &&
    patchSize.value > 0,
);

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
  return Number.isNaN(at.getTime())
    ? ""
    : at.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
});
const gtinStillRejected = computed(
  () =>
    !!gtinRejected.value &&
    draft.social.gtin.trim() === gtinRejected.value.gtin,
);
const canKeepWithoutGtin = computed(
  () =>
    !!gtinRejected.value &&
    !gtinRejected.value.confirmed &&
    gtinStillRejected.value &&
    !props.busy &&
    !props.loading &&
    !props.conflict &&
    !formInvalid.value,
);
function keepWithoutGtin() {
  if (!canKeepWithoutGtin.value) return;
  emit("save", { ...buildPatch(), gtin_rejected: { confirmed: true } });
}

const discardRequested = ref(false);
function requestClose(open: boolean) {
  if (!open && props.busy) return;
  if (!open && patchSize.value) {
    discardRequested.value = true;
    return;
  }
  emit("update:open", open);
}
watch(
  () => props.open,
  () => {
    discardRequested.value = false;
  },
);
const conflictLabels: Record<string, string> = {
  name: "Nome",
  short_description: "Descrição curta",
  long_description: "Descrição completa",
  keywords: "Palavras-chave",
  image_url: "Imagem",
  base_price_q: "Preço",
  unit: "Unidade",
  unit_weight_g: "Peso por unidade",
  availability_policy: "Disponibilidade",
  shelf_life_days: "Validade",
  storage_tip: "Conservação",
  production_cycle_hours: "Tempo de produção",
  is_batch_produced: "Produção em lote",
  is_published: "Publicado",
  is_sellable: "Disponível para venda",
  allows_next_day_sale: "Venda no dia seguinte",
  ingredients_text: "Ingredientes",
  allergens: "Alérgenos",
  dietary_info: "Informações alimentares",
  serves: "Rendimento",
  approx_dimensions: "Dimensões",
  "social.brand": "Marca",
  "social.gtin": "GTIN",
  "social.mpn": "Código do fabricante",
  "social.condition": "Condição",
  "social.google_product_category": "Categoria Google",
  "social.tiktok_category_id": "Categoria TikTok",
  "social.hashtags": "Hashtags",
  "social.social_caption": "Legenda",
  "fiscal.profile": "Perfil fiscal",
  "fiscal.ncm": "NCM",
  "fiscal.cest": "CEST",
  "fiscal.unit": "Unidade fiscal",
  vocation: "Vocação",
  ...Object.fromEntries(
    [...SERVING_FIELDS, ...MACRO_FIELDS, ...MICRO_FIELDS].map((f) => [
      `nutrition_facts.${f.key}`,
      f.label,
    ]),
  ),
};
function sourceChange(field: string): string {
  const root = field.split(".")[0]!;
  const before = props.detail?.field_sources?.[root];
  const after = props.conflict?.product.field_sources?.[root];
  if (before === after) return "";
  const label = (value?: string) =>
    value === "recipe"
      ? "ficha técnica"
      : value === "manual"
        ? "edição manual"
        : value || "não informada";
  return `Origem: ${label(before)} → ${label(after)}.`;
}

function currentValue(path: string): string {
  if (path === "vocation")
    return vocationLabel(
      props.conflict?.product.vocation ?? "",
      props.conflict?.product.vocation_choices,
    );
  let value: unknown = props.conflict?.product;
  for (const part of path.split(".")) {
    value =
      value && typeof value === "object"
        ? (value as Record<string, unknown>)[part]
        : undefined;
  }
  if (value === null || value === undefined || value === "")
    return "Não informado";
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (path === "base_price_q" && typeof value === "number")
    return `R$ ${centsToText(value)}`;
  return Array.isArray(value) ? value.join(", ") : String(value);
}

const sectionClass =
  "text-xs font-medium uppercase tracking-wide text-muted-foreground";
</script>

<template>
  <NuxtSlideover
    :open="open"
    :title="detail?.name || 'Produto'"
    :description="`${sku}${detail ? ` · R$ ${centsToText(detail.base_price_q)}${detail.unit === 'kg' ? '/kg' : ''}` : ''}${detail?.primary_collection_name ? ` · ${detail.primary_collection_name}` : ''}${roleBadges.length ? ` · ${roleBadges.join(' · ')}` : ''}`"
    side="right"
    @update:open="requestClose"
  >
    <template #actions>
      <OperatorMoreMenu
        v-model:open="headerMenuOpen"
        :items="panelMenuItems"
        label="Mais ações do produto"
        data-panel-more
      />
    </template>
    <template #body>
      <div class="flex flex-col gap-4">
        <NuxtAlert
          v-if="conflict"
          color="warning"
          variant="subtle"
          icon="i-lucide-git-compare"
          title="Seu rascunho foi preservado"
          :description="
            conflict.conflicting_fields
              .map(
                (field) =>
                  `${conflictLabels[field] || 'Campo editado'}. Valor atual: ${currentValue(field)}${sourceChange(field) ? ` (${sourceChange(field)})` : ''}`,
              )
              .join(' · ')
          "
          :actions="[
            {
              label: 'Manter meu rascunho',
              color: 'warning',
              variant: 'outline',
              onClick: () => emit('review-conflict', true),
            },
            {
              label: 'Usar valores atuais',
              color: 'warning',
              variant: 'outline',
              onClick: () => emit('review-conflict', false),
            },
          ]"
        />
        <NuxtAlert
          v-else-if="error"
          color="error"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          :description="error"
        />
        <NuxtAlert
          v-if="discardRequested"
          color="warning"
          variant="subtle"
          title="Há alterações não salvas neste produto"
          :actions="[
            {
              label: 'Continuar editando',
              color: 'warning',
              variant: 'outline',
              onClick: () => {
                discardRequested = false;
              },
            },
            {
              label: 'Descartar e fechar',
              color: 'warning',
              variant: 'outline',
              onClick: () => emit('update:open', false),
            },
          ]"
        />

        <!-- abas: o formulário é longo demais para uma coluna só. Rolam na horizontal
           porque cinco rótulos não cabem na largura do slide-over. -->
        <!-- as cinco abas cabem (v4): sublinhada a ativa, sem caixa; rola só se a largura faltar -->
        <NuxtTabs
          v-model="tab"
          :items="tabItems"
          :content="false"
          variant="link"
          aria-label="Partes do produto"
          data-panel-tabs
        />

        <div>
          <NuxtSkeleton
            v-if="loading"
            class="h-64 w-full"
            aria-label="Carregando produto"
          />

          <NuxtEmpty
            v-else-if="!detail"
            icon="i-lucide-package-x"
            title="Não foi possível carregar este produto"
          />

          <template v-else>
            <!-- Geral -->
            <div v-show="tab === 'geral'" class="space-y-4">
              <!-- A Geral começa pelo nome no cardápio (v4); a disponibilidade vem logo abaixo. -->
              <NuxtFormField label="Nome no cardápio">
                <NuxtInput
                  v-model="draft.name"
                  class="w-full"
                  type="text"
                  placeholder="Ex.: Pão francês"
                />
              </NuxtFormField>

              <!-- Disponibilidade nos canais (v4): um estado só, a hora provável de volta e o
                 porquê; por canal, o que o cliente vê ali e o Pausar (o mesmo gesto da
                 célula da tabela). O motivo da pausa não é gravado (decisão do dono). -->
              <NuxtCard
                v-if="availability.length"
                as="section"
                variant="soft"
                data-panel-availability
              >
                <template #header>
                  <div>
                    <div class="flex flex-wrap items-center gap-2">
                      <h3 class="op-label font-semibold">
                        Disponibilidade nos canais
                      </h3>
                      <NuxtBadge
                        v-if="unavailableCount"
                        color="error"
                        :label="availabilityHeadline"
                      />
                      <NuxtBadge
                        v-else
                        color="success"
                        label="À venda em todos"
                      />
                      <span class="ms-auto op-micro text-muted-foreground"
                        >vale na hora</span
                      >
                    </div>
                    <p
                      v-if="unavailableCount && detail?.back_at"
                      class="mt-1 op-micro text-muted-foreground"
                      data-panel-back
                    >
                      Volta <b class="text-foreground">~{{ detail.back_at }}</b
                      >: {{ detail.back_reason }}. Segue o estoque em todos os
                      canais.
                    </p>
                  </div>
                </template>
                <div class="divide-y divide-default">
                  <div
                    v-for="row in availability"
                    :key="row.ref"
                    class="flex min-h-12 items-center gap-3 py-2 first:pt-0 last:pb-0"
                    data-panel-channel
                  >
                    <Icon
                      :name="channelIcon(row)"
                      class="size-4 shrink-0 text-muted-foreground"
                    />
                    <span class="w-28 shrink-0 op-body">{{ row.name }}</span>
                    <span class="min-w-0 flex-1 op-micro">
                      <span class="block">
                        <b
                          v-if="row.state !== 'available'"
                          class="font-semibold text-error"
                          >{{
                            row.state === "paused"
                              ? "Pausado"
                              : row.kind === "display"
                                ? "Fora de estoque"
                                : "Esgotado"
                          }}</b
                        >
                        <span v-else class="text-muted-foreground"
                          >À venda</span
                        >
                        <span v-if="row.back_at" class="text-muted-foreground">
                          · volta ~{{ row.back_at
                          }}<template v-if="row.back_hint">
                            ({{ row.back_hint }})</template
                          ></span
                        >
                        <span
                          v-else-if="row.since"
                          class="text-muted-foreground"
                        >
                          desde {{ row.since }}</span
                        >
                      </span>
                      <span
                        v-if="
                          row.note ||
                          (row.automatic && row.state !== 'available')
                        "
                        class="mt-0.5 flex flex-wrap items-center gap-1.5 text-muted-foreground"
                        data-panel-channel-note
                      >
                        <NuxtBadge
                          v-if="row.automatic && row.state !== 'available'"
                          color="neutral"
                          icon="i-lucide-sparkles"
                          label="automático"
                        />
                        <span v-if="row.note">{{ row.note }}</span>
                      </span>
                    </span>
                    <NuxtButton
                      v-if="channelCells?.[row.ref]"
                      type="button"
                      :icon="
                        channelCells[row.ref]!.paused
                          ? 'i-lucide-play'
                          : 'i-lucide-pause'
                      "
                      :label="
                        channelCells[row.ref]!.paused ? 'Retomar' : 'Pausar'
                      "
                      color="neutral"
                      variant="outline"
                      :disabled="
                        !channelCells[row.ref]!.enabled ||
                        channelCells[row.ref]!.busy
                      "
                      :aria-label="
                        channelCells[row.ref]!.paused
                          ? `Retomar ${row.name}`
                          : `Pausar ${row.name}`
                      "
                      data-panel-pause
                      @click="
                        emit(
                          'pause-channel',
                          row.ref,
                          !channelCells[row.ref]!.paused,
                        )
                      "
                    />
                  </div>
                </div>
                <template #footer>
                  <p
                    class="flex items-start gap-1.5 op-micro text-muted-foreground"
                  >
                    <Icon
                      name="lucide:sparkles"
                      class="mt-0.5 size-3 shrink-0"
                    />
                    O sistema avisa o iFood, a Meta e o Google sozinho quando o
                    estoque zera e quando volta. Pausar é para o que não é falta
                    de estoque.
                  </p>
                </template>
              </NuxtCard>

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
                <NuxtInput
                  v-model="draft.short_description"
                  type="text"
                  maxlength="255"
                  placeholder="Uma linha para listagens e vitrine"
                />
                <span class="mt-1 block text-xs text-muted-foreground"
                  >{{ draft.short_description.length }}/255</span
                >
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
                <NuxtTextarea
                  v-model="draft.long_description"
                  :rows="5"
                  placeholder="Texto completo da página do produto."
                ></NuxtTextarea>
              </CatalogAiSuggest>

              <NuxtFormField
                label="Palavras-chave"
                description="Separe por vírgula. Usadas em busca e SEO."
              >
                <NuxtInput
                  v-model="draft.keywordsText"
                  class="w-full"
                  type="text"
                  placeholder="padaria, pão artesanal, fermentação natural"
                />
              </NuxtFormField>

              <NuxtFormField label="URL da imagem">
                <NuxtInput
                  v-model="draft.image_url"
                  class="w-full"
                  type="url"
                  placeholder="https://…"
                />
              </NuxtFormField>
              <img
                v-if="draft.image_url"
                :src="draft.image_url"
                alt="Prévia da imagem do produto"
                class="h-32 w-32 rounded-lg border border-border object-cover"
              />
            </div>

            <!-- Preço e config -->
            <div v-show="tab === 'config'" class="space-y-4">
              <!-- Vendido por peso: a unidade de venda vira kg e o MESMO campo de
                 preço passa a ser o preço do quilo. O preço final sai da balança
                 do balcão, então o item não vai para canal remoto. -->
              <NuxtCheckbox
                :model-value="soldByWeight"
                label="Vendido por peso"
                data-testid="sold-by-weight"
                @update:model-value="(value) => setSoldByWeight(value === true)"
              />
              <p
                v-if="soldByWeight"
                class="-mt-2 text-xs text-muted-foreground"
              >
                Vendido só no balcão: o preço final sai da balança.
              </p>

              <div class="grid grid-cols-2 gap-3">
                <NuxtFormField
                  :label="soldByWeight ? 'Preço por kg' : 'Preço'"
                  :error="priceInvalid ? 'Informe um valor válido.' : undefined"
                >
                  <NuxtInput
                    v-model="draft.priceText"
                    class="w-full"
                    type="text"
                    inputmode="decimal"
                    placeholder="0,00"
                    :aria-invalid="priceInvalid"
                  />
                </NuxtFormField>
                <NuxtFormField v-if="!soldByWeight" label="Unidade">
                  <NuxtInput
                    v-model="draft.unit"
                    class="w-full"
                    type="text"
                    placeholder="un, lt"
                  />
                </NuxtFormField>
              </div>

              <div class="grid grid-cols-2 gap-3">
                <NuxtFormField label="Peso por unidade (g)">
                  <NuxtInput
                    v-model.number="draft.unit_weight_g"
                    class="w-full"
                    type="number"
                    :min="0"
                    placeholder="Ex.: 150"
                  />
                </NuxtFormField>
                <NuxtFormField label="Validade (dias)">
                  <NuxtInput
                    v-model.number="draft.shelf_life_days"
                    class="w-full"
                    type="number"
                    :min="0"
                    placeholder="Vazio = não perece"
                  />
                </NuxtFormField>
              </div>

              <NuxtFormField label="Política de disponibilidade">
                <NuxtSelect
                  class="w-full"
                  :model-value="availabilityPolicyValue"
                  :items="[...POLICIES]"
                  @update:model-value="setAvailabilityPolicy"
                />
              </NuxtFormField>

              <NuxtFormField label="Dica de conservação">
                <NuxtInput
                  v-model="draft.storage_tip"
                  class="w-full"
                  type="text"
                  maxlength="300"
                  placeholder="Ex.: guarde em saco de pano por até 2 dias"
                />
              </NuxtFormField>

              <NuxtFormField label="Ciclo de produção (horas)">
                <NuxtInput
                  v-model.number="draft.production_cycle_hours"
                  class="w-full"
                  type="number"
                  :min="0"
                  placeholder="Ex.: 4"
                />
              </NuxtFormField>

              <NuxtCheckbox
                v-model="draft.is_batch_produced"
                label="Produzido em lote"
              />

              <NuxtCheckbox
                v-model="draft.allows_next_day_sale"
                label="Pode ser vendido no dia seguinte"
              />

              <!-- Permitir compra: o cadastro de compra do MESMO SKU (mesmo estoque).
                 Vale na hora, fora do "Salvar" — é interruptor, não rascunho. -->
              <NuxtCard variant="soft" data-testid="purchase-toggle">
                <div class="space-y-3">
                  <p :class="sectionClass">Compra</p>
                  <div v-if="roleBadges.length" class="flex flex-wrap gap-1">
                    <NuxtBadge
                      v-for="badge in roleBadges"
                      :key="badge"
                      color="neutral"
                      :label="badge"
                    />
                  </div>
                  <p
                    v-if="roles?.produced && !roles?.purchasable"
                    class="text-xs text-muted-foreground"
                  >
                    É produzido aqui: o estoque entra pela Produção, não pela
                    compra.
                  </p>
                  <NuxtCheckbox
                    v-else
                    :model-value="Boolean(roles?.purchasable)"
                    :disabled="purchaseBusy || !roles"
                    label="Permitir compra"
                    @update:model-value="
                      (value) => onPurchaseChange(value === true)
                    "
                  />
                  <p
                    v-if="roles?.purchasable"
                    class="text-xs text-muted-foreground"
                  >
                    Aparece no Compras: recebe nota, tem custo, mínimo e pedido.
                  </p>
                </div>
              </NuxtCard>

              <!-- Vocação: o que a presença do produto na cesta diz ao B.I. (consumo
                 aqui × levar). Não muda a venda, por isso fica discreta, aqui e não
                 na aba Geral. Entra no rascunho: grava no "Salvar". -->
              <NuxtFormField
                label="Vocação"
                hint="só para o B.I."
                data-testid="vocation"
              >
                <NuxtRadioGroup
                  v-if="vocationChoices.length"
                  v-model="draft.vocation"
                  :items="
                    vocationChoices.map((option) => ({
                      value: option.value,
                      label: option.label,
                      description: option.hint,
                    }))
                  "
                  variant="card"
                />
                <p v-else class="text-xs text-muted-foreground">
                  Nenhuma vocação cadastrada. O cadastro fica no Admin.
                </p>
                <NuxtButton
                  v-if="draft.vocation"
                  type="button"
                  label="Deixar sem vocação"
                  color="neutral"
                  variant="outline"
                  @click="draft.vocation = ''"
                />
                <p
                  v-else-if="vocationChoices.length"
                  class="text-xs text-muted-foreground"
                >
                  Sem vocação: o B.I. não classifica as vendas deste produto.
                </p>
              </NuxtFormField>

              <NuxtCard variant="soft">
                <div class="space-y-3">
                  <p :class="sectionClass">Visibilidade</p>
                  <NuxtCheckbox
                    v-model="draft.is_published"
                    label="Exibido no catálogo"
                  />
                  <NuxtCheckbox
                    v-model="draft.is_sellable"
                    label="Disponível para venda"
                  />
                </div>
              </NuxtCard>
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
                <NuxtTextarea
                  v-model="draft.ingredients_text"
                  :rows="6"
                  placeholder="Farinha de trigo, água, fermento natural, sal marinho."
                ></NuxtTextarea>
              </CatalogAiSuggest>

              <NuxtCard variant="soft">
                <div class="space-y-3">
                  <p :class="sectionClass">Rotulagem para compra remota</p>
                  <NuxtAlert
                    v-if="
                      detail?.dietary_from_recipe &&
                      (detail.allergens.length || detail.dietary_info.length)
                    "
                    color="info"
                    variant="subtle"
                    description="Alérgenos e restrições vieram da receita. Ao editar aqui, o produto passa a ignorar a receita e você fica responsável por manter estes campos."
                  />

                  <NuxtFormField
                    label="Alérgenos"
                    description="Separe por vírgula."
                  >
                    <NuxtInput
                      v-model="draft.allergensText"
                      class="w-full"
                      type="text"
                      placeholder="glúten, leite, gergelim"
                    />
                  </NuxtFormField>

                  <NuxtFormField
                    label="Restrições atendidas"
                    description="Separe por vírgula."
                  >
                    <NuxtInput
                      v-model="draft.dietaryText"
                      class="w-full"
                      type="text"
                      placeholder="100% vegetal, sem lactose"
                    />
                  </NuxtFormField>

                  <div class="grid grid-cols-2 gap-3">
                    <NuxtFormField label="Serve">
                      <NuxtInput
                        v-model="draft.serves"
                        class="w-full"
                        type="text"
                        placeholder="Ex.: 2 a 4 pessoas"
                      />
                    </NuxtFormField>
                    <NuxtFormField label="Medidas aproximadas">
                      <NuxtInput
                        v-model="draft.approx_dimensions"
                        class="w-full"
                        type="text"
                        placeholder="Ex.: aprox. 24 x 12 cm"
                      />
                    </NuxtFormField>
                  </div>
                </div>
              </NuxtCard>

              <NuxtCard variant="soft">
                <div class="space-y-3">
                  <p :class="sectionClass">Tabela nutricional</p>
                  <NuxtAlert
                    v-if="detail?.nutrition_auto_filled"
                    color="info"
                    variant="subtle"
                    description="Estes valores foram calculados a partir da receita. Ao editar, o cálculo automático para de valer para este produto."
                  />

                  <div class="grid grid-cols-2 gap-3">
                    <NuxtFormField
                      v-for="f in SERVING_FIELDS"
                      :key="f.key"
                      :label="f.label"
                    >
                      <NuxtInput
                        v-model.number="draft.nutrition[f.key]"
                        class="w-full"
                        type="number"
                        :min="0"
                        :step="f.step"
                      />
                    </NuxtFormField>
                  </div>

                  <p class="pt-1 text-xs font-medium text-muted-foreground">
                    Macronutrientes
                  </p>
                  <div class="grid grid-cols-2 gap-3">
                    <NuxtFormField
                      v-for="f in MACRO_FIELDS"
                      :key="f.key"
                      :label="f.label"
                    >
                      <NuxtInput
                        v-model.number="draft.nutrition[f.key]"
                        class="w-full"
                        type="number"
                        :min="0"
                        :step="f.step"
                      />
                    </NuxtFormField>
                  </div>

                  <p class="pt-1 text-xs font-medium text-muted-foreground">
                    Micronutrientes
                  </p>
                  <div class="grid grid-cols-2 gap-3">
                    <NuxtFormField
                      v-for="f in MICRO_FIELDS"
                      :key="f.key"
                      :label="f.label"
                    >
                      <NuxtInput
                        v-model.number="draft.nutrition[f.key]"
                        class="w-full"
                        type="number"
                        :min="0"
                        :step="f.step"
                      />
                    </NuxtFormField>
                  </div>

                  <p class="text-xs text-muted-foreground">
                    Preencher qualquer nutriente exige informar a porção.
                    Gorduras trans e saturadas não podem passar das totais, nem
                    açúcares dos carboidratos.
                  </p>
                </div>
              </NuxtCard>
            </div>

            <!-- Redes sociais (PIM) -->
            <div v-show="tab === 'social'" class="space-y-4">
              <NuxtAlert
                color="info"
                variant="subtle"
                description="Atributos comerciais compartilhados pelos canais. As exigências variam por destino."
              />

              <NuxtFormField label="Marca">
                <NuxtInput
                  v-model="draft.social.brand"
                  class="w-full"
                  type="text"
                  placeholder="Ex.: Nelson Boulangerie"
                />
              </NuxtFormField>

              <div class="grid grid-cols-2 gap-3">
                <NuxtFormField label="GTIN / código de barras">
                  <NuxtInput
                    v-model="draft.social.gtin"
                    class="w-full"
                    type="text"
                    inputmode="numeric"
                    placeholder="8, 12, 13 ou 14 dígitos"
                  />
                </NuxtFormField>
                <NuxtFormField label="Condição">
                  <NuxtSelect
                    class="w-full"
                    :model-value="conditionValue"
                    :items="[...CONDITIONS]"
                    @update:model-value="setCondition"
                  />
                </NuxtFormField>
              </div>

              <NuxtAlert
                v-if="gtinRejected"
                :color="gtinRejected.confirmed ? 'info' : 'warning'"
                variant="subtle"
                icon="i-lucide-scan-barcode"
                :title="
                  gtinRejected.confirmed
                    ? 'Produto mantido sem GTIN na nota'
                    : 'GTIN recusado pela SEFAZ'
                "
                data-gtin-rejected
              >
                <template #description
                  ><div class="space-y-2">
                    <template v-if="gtinRejected.confirmed">
                      <p data-gtin-rejected-confirmed>
                        Sai sem GTIN na NFC-e. A SEFAZ recusou o código
                        {{ gtinRejected.gtin }}, e
                        {{ gtinRejected.confirmed_by || "o gestor" }} conferiu a
                        embalagem. Para voltar a mandar o GTIN, corrija o campo
                        e salve.
                      </p>
                    </template>
                    <template v-else>
                      <p class="font-medium">
                        A SEFAZ recusou o GTIN {{ gtinRejected.gtin }} na NFC-e
                        do pedido {{ gtinRejected.order_ref
                        }}<template v-if="gtinRejectedWhen"
                          >, em {{ gtinRejectedWhen }}</template
                        >.
                      </p>
                      <p class="text-muted-foreground">
                        A nota saiu de novo sem GTIN, e o produto segue saindo
                        assim até alguém conferir. Compare com o código da
                        embalagem: se for outro, corrija o campo e salve; se for
                        o mesmo, ou se o produto não tiver código de barras,
                        toque em Manter sem GTIN na nota.
                      </p>
                      <p
                        v-if="gtinRejected.reason"
                        class="text-xs text-muted-foreground"
                        data-gtin-rejected-reason
                      >
                        Motivo da SEFAZ (rejeição {{ gtinRejected.code }}):
                        {{ gtinRejected.reason }}
                      </p>
                      <p
                        v-if="!gtinStillRejected"
                        class="text-xs"
                        data-gtin-rejected-corrected
                      >
                        Ao salvar, o código novo volta a ir na nota.
                      </p>
                      <NuxtButton
                        v-else
                        type="button"
                        label="Manter sem GTIN na nota"
                        color="warning"
                        variant="outline"
                        :disabled="!canKeepWithoutGtin"
                        data-gtin-keep-without
                        @click="keepWithoutGtin"
                      />
                    </template></div
                ></template>
              </NuxtAlert>

              <NuxtFormField label="MPN (código do fabricante)">
                <NuxtInput
                  v-model="draft.social.mpn"
                  class="w-full"
                  type="text"
                  placeholder="Opcional"
                />
              </NuxtFormField>

              <NuxtFormField label="Categoria Google">
                <NuxtInput
                  v-model="draft.social.google_product_category"
                  class="w-full"
                  type="text"
                  placeholder="Ex.: Food, Beverages & Tobacco > Food Items > Bakery"
                />
              </NuxtFormField>

              <NuxtFormField label="Categoria TikTok">
                <NuxtInput
                  v-model="draft.social.tiktok_category_id"
                  class="w-full"
                  type="text"
                  placeholder="ID da categoria (opcional)"
                />
              </NuxtFormField>

              <CatalogAiSuggest
                :sku="sku"
                field="hashtags"
                label="Hashtags"
                :current="draft.social.hashtagsText"
                :busy="assistBusy('hashtags')"
                :assist="assist"
                hint='Separe por espaço ou vírgula. O "#" é opcional.'
                @accept="(text) => (draft.social.hashtagsText = text)"
              >
                <NuxtInput
                  v-model="draft.social.hashtagsText"
                  type="text"
                  placeholder="pão artesanal caseiro"
                />
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
                <NuxtTextarea
                  v-model="draft.social.social_caption"
                  :rows="3"
                  placeholder="Texto sugerido para posts e feeds."
                ></NuxtTextarea>
              </CatalogAiSuggest>
            </div>

            <!-- Fiscal (NFC-e) -->
            <div v-show="tab === 'fiscal'" class="space-y-4">
              <NuxtAlert
                color="info"
                variant="subtle"
                description="Usado na emissão da NFC-e. CFOP, CSOSN e PIS/COFINS vêm do perfil; aqui fica só o que muda de produto para produto."
              />

              <NuxtFormField label="Perfil fiscal">
                <NuxtSelect
                  v-model="draft.fiscal.profile"
                  class="w-full"
                  :items="
                    fiscalProfiles.map((profile) => ({
                      value: profile.key,
                      label: profile.name,
                    }))
                  "
                />
              </NuxtFormField>

              <div class="grid grid-cols-2 gap-3">
                <NuxtFormField
                  label="NCM"
                  :error="ncmInvalid ? 'NCM deve ter 8 dígitos.' : undefined"
                >
                  <NuxtInput
                    v-model="draft.fiscal.ncm"
                    class="w-full"
                    type="text"
                    inputmode="numeric"
                    maxlength="8"
                    placeholder="8 dígitos"
                    :aria-invalid="ncmInvalid"
                  />
                </NuxtFormField>
                <NuxtFormField label="Unidade comercial">
                  <NuxtInput
                    v-model="draft.fiscal.unit"
                    class="w-full"
                    type="text"
                    maxlength="6"
                    placeholder="UN"
                  />
                </NuxtFormField>
              </div>

              <NuxtFormField label="Origem da mercadoria">
                <NuxtSelect
                  v-model="draft.fiscal.origin"
                  class="w-full"
                  :items="
                    (props.detail?.fiscal_origins ?? []).map((origin) => ({
                      value: origin.key,
                      label: origin.name,
                    }))
                  "
                />
              </NuxtFormField>

              <NuxtFormField
                label="CEST"
                :error="cestInvalid ? 'CEST deve ter 7 dígitos.' : undefined"
                :description="
                  cestRequired
                    ? 'Obrigatório com substituição tributária.'
                    : 'Identificação da mercadoria; a tributação vem do perfil fiscal.'
                "
              >
                <NuxtInput
                  v-model="draft.fiscal.cest"
                  class="w-full"
                  type="text"
                  inputmode="numeric"
                  maxlength="7"
                  placeholder="7 dígitos"
                  :aria-invalid="cestInvalid"
                />
                <NuxtAlert
                  v-for="warning in props.detail?.fiscal_warnings ?? []"
                  :key="warning"
                  color="warning"
                  variant="subtle"
                  :description="warning"
                />
              </NuxtFormField>
            </div>
          </template>
        </div>

        <!-- Rodapé (v4): o que ainda está abaixo na Geral, Descartar e "N campo alterado · Salvar". -->
      </div>
    </template>
    <template #footer>
      <NuxtButton
        v-if="tab === 'geral' && detail && !belowVisible"
        type="button"
        label="Descrição e foto seguem abaixo"
        trailing-icon="i-lucide-chevron-down"
        color="neutral"
        variant="ghost"
        data-panel-below
        @click="showBelow"
      />
      <span v-else class="me-auto" />
      <NuxtButton
        type="button"
        label="Descartar"
        color="neutral"
        variant="ghost"
        data-panel-discard
        @click="requestClose(false)"
      />
      <NuxtButton
        type="button"
        :label="
          patchSize
            ? `${patchSize} ${patchSize === 1 ? 'campo alterado' : 'campos alterados'} · Salvar`
            : 'Salvar'
        "
        :disabled="!canSave"
        color="primary"
        :loading="busy"
        data-panel-save
        data-panel-changes
        @click="onSave"
      />
    </template>
  </NuxtSlideover>
</template>
