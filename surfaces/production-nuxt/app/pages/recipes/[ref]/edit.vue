<script setup lang="ts">
import { alertActions } from "../../../../../operator-kit/app/utils/alertActions";
import type { OperatorActionBarAction } from "../../../../../operator-kit/app/presentation/actionBar";
// O editor do rascunho (/recipes/[ref]/edit?v=n). Rendimento, âncora, a tabela
// editável (ingrediente com busca, quantidade, composição, papel), etapas e
// notas; à direita a PRÉVIA DA LENTE, recalculada pelo servidor com debounce. O
// botão "Padronizar para 1000 g" mostra o antes/depois e deixa desfazer; a receita
// como foi informada (`origin`) fica visível como referência histórica. "Salvar
// rascunho" grava; "Salvar e publicar" grava e publica, voltando à receita.
import type { AnchorKind, Formula, FormulaQuantity, FormulaUnit, IngredientDefaults, IngredientOptionProjection, IngredientRole, RecipeKind, RecipeStepInput, RecipeVersionProjection } from "~/types/recipeBook";
import {
  ANCHOR_OPTIONS,
  HOUSE_BASIS_G,
  KIND_OPTIONS,
  ROLE_OPTIONS,
  UNIT_OPTIONS,
  YIELD_UNIT_OPTIONS,
  addItem,
  anchorTotalOf,
  emptyFormula,
  emptyItem,
  exactQuantity,
  formulaFromServed,
  gramsLabel,
  moveItem,
  originLines,
  pctOf,
  quantityPreset,
  removeItem,
  setAnchor,
  stepsForPayload,
  totalMassOf,
  unmatchedItems,
  updateItem,
  withQuantityPreset,
} from "~/presentation/recipeBook";
import { convertQuantity, normalizeQuantity, quantityRule } from "~/utils/quantity";

const route = useRoute();
const entryRef = String(route.params.ref ?? "");

const { entry, canEdit, latestDraft, versionByNumber, notFound, forbidden, pending, error, refresh, busy, patchEntry, saveExecution, createVersion, updateDraft, publish } =
  useRecipeEntry(entryRef);

useHead({ title: computed(() => `Editar · ${entry.value?.name || "Receita"}`) });

// ── O rascunho em edição ────────────────────────────────────────────────────
const requestedNumber = computed(() => Number(route.query.v) || null);
const draft = computed<RecipeVersionProjection | null>(() => {
  const requested = versionByNumber(requestedNumber.value);
  if (requested?.status === "draft") return requested;
  return latestDraft.value;
});
// Estado local, semeado UMA vez quando o rascunho chega (o refresh depois de salvar
// não pode sobrescrever o que o padeiro está digitando).
const formula = ref<Formula>(emptyFormula());
const yieldQuantity = ref("");
const yieldUnit = ref("g");
const steps = ref<RecipeStepInput[]>([]);
const notes = ref("");
const label = ref("");
const seededNumber = ref<number | null>(null);
const entryName = ref("");
const entryKind = ref<RecipeKind>("other");
const entryOutputSku = ref("");
const entryNotes = ref("");
const ingredientDefaults = ref<IngredientDefaults | null>(null);
const entrySeeded = ref(false);
// O "antes" da padronização (desfazer). Declarado ANTES do watch abaixo: com o
// rascunho já carregado no servidor, o watch imediato roda durante o setup e
// tocava em `before` antes da inicialização (500 na página inteira).
const before = ref<{ formula: Formula; anchorTotal: number; total: number; yieldQuantity: string } | null>(null);

watch(
  draft,
  (version) => {
    if (!version || seededNumber.value === version.number) return;
    formula.value = formulaFromServed(version.formula);
    yieldQuantity.value = version.yield_quantity;
    yieldUnit.value = version.yield_unit || "g";
    steps.value = stepsForPayload(version.steps);
    notes.value = version.notes;
    label.value = version.label;
    seededNumber.value = version.number;
    before.value = null;
  },
  { immediate: true },
);

watch(
  entry,
  (current) => {
    if (!current || entrySeeded.value) return;
    entryName.value = current.name;
    entryKind.value = current.kind as RecipeKind;
    entryOutputSku.value = current.output_sku;
    entryNotes.value = current.notes;
    ingredientDefaults.value = ((current as typeof current & { ingredient_defaults?: IngredientDefaults | null }).ingredient_defaults) ?? null;
    entrySeeded.value = true;
  },
  { immediate: true },
);

const kind = computed(() => entry.value?.kind ?? "other");
const { lens, pending: lensPending, error: lensError, standardizing, standardize } = useFormulaLens(formula, kind);

// ── Feedback imediato (a conta oficial é a lente) ───────────────────────────
const localAnchorTotal = computed(() => anchorTotalOf(formula.value));
const localTotal = computed(() => totalMassOf(formula.value));
// O padrão da casa vale para qualquer âncora: 1000 g de farinha no pão, 1000 g
// de massa total num creme, 1000 g do ingrediente-âncora numa ganache.
const anchorNoun = computed(() => {
  if (formula.value.anchor.kind === "flour") return "de farinha";
  if (formula.value.anchor.kind === "ingredient") return "do ingrediente-base";
  return "de massa total";
});
const unmatchedCount = computed(() => (lens.value ? unmatchedItems(lens.value.ingredients).length : 0));

// ── Itens ───────────────────────────────────────────────────────────────────
// Percentuais informados pelo operador usam uma única régua. Aceitar milésimos
// com botões de décimo preservava um resíduo invisível (0,201 → 0,301).
const percentageRule = { step: 0.1, min: 0.1, maximumFractionDigits: 1 } as const;
const newIngredientIndex = ref<number | null>(null);
const ingredientFocusKey = ref<string | null>(null);
useNextFocus(ingredientFocusKey);
const yieldQuantityNumber = computed<number | null>({
  get: () => {
    const value = Number(String(yieldQuantity.value).replace(",", "."));
    return Number.isFinite(value) && value > 0 ? value : null;
  },
  set: (value) => {
    yieldQuantity.value = value == null ? "" : String(normalizeQuantity(value, yieldUnit.value as FormulaUnit));
  },
});
function normalizedPercentage(value: number): number {
  const factor = 10 ** percentageRule.maximumFractionDigits;
  return Math.round((value + Number.EPSILON) * factor) / factor;
}
function formulaDefaultUnit(unit: string): FormulaUnit {
  if (unit === "kg" || unit === "g") return "g";
  if (unit === "L" || unit === "ml") return "ml";
  return "un";
}
function onItemQuantity(index: number, value: number | null | undefined) {
  const item = formula.value.ingredients[index];
  if (!item) return;
  const unit = item.quantity.unit ?? "g";
  const target = value == null
    ? 0
    : item.quantity.kind === "ratio"
      ? normalizedPercentage(value)
      : normalizeQuantity(value, unit);
  const preset = quantityPreset(item.quantity);
  formula.value = updateItem(formula.value, index, {
    quantity: withQuantityPreset({ ...item.quantity, target }, preset),
  });
}
function onItemUnit(index: number, unit: string) {
  const item = formula.value.ingredients[index];
  if (!item) return;
  const next = unit as FormulaUnit;
  const currentUnit = item.quantity.unit ?? "g";
  const converted = convertQuantity(item.quantity.target, currentUnit, next);
  const factor = converted == null || !item.quantity.target ? 1 : converted / item.quantity.target;
  const scale = (value: number | null) => value == null ? null : normalizeQuantity(value * factor, next);
  formula.value = updateItem(formula.value, index, {
    quantity: {
      ...item.quantity,
      unit: next,
      target: converted ?? item.quantity.target,
      minimum: scale(item.quantity.minimum),
      maximum: scale(item.quantity.maximum),
    },
  });
  if (converted === null && item.quantity.target > 0) {
    useSonner.info("Quantidade mantida. Massa, volume e unidade não têm conversão automática entre si.");
  }
}
function onYieldUnit(unit: string) {
  const from = yieldUnit.value as FormulaUnit;
  const next = unit as FormulaUnit;
  const current = yieldQuantityNumber.value;
  if (current != null) {
    const converted = convertQuantity(current, from, next);
    yieldQuantity.value = String(converted ?? current);
    if (converted === null) {
      useSonner.info("Rendimento mantido. Massa, volume e unidade não têm conversão automática entre si.");
    }
  }
  yieldUnit.value = next;
}
function onItemRole(index: number, role: string) {
  formula.value = updateItem(formula.value, index, { role: role as IngredientRole });
}
function onItemGramsPerUnit(index: number, event: Event) {
  const raw = (event.target as HTMLInputElement).value.replace(",", ".");
  formula.value = updateItem(formula.value, index, { grams_per_unit: raw ? Number(raw) || null : null });
}
function onItemSku(index: number, sku: string) {
  formula.value = updateItem(formula.value, index, sku ? { sku } : { sku: "", name: "" });
}
function onItemSelect(index: number, option: IngredientOptionProjection) {
  const item = formula.value.ingredients[index];
  if (!item) return;
  // A BOM tem um único tipo de linha: ingrediente. A origem do item escolhido
  // decide apenas qual estrutura o motor recebe. Não obriga o operador a saber,
  // antes de buscar, se o ingrediente é comprado ou preparado pela casa.
  const patch: Partial<typeof item> = { sku: option.sku, name: option.name };
  if (ROLE_OPTIONS.some((role) => role.value === option.role)) patch.role = option.role as IngredientRole;
  const nextUnit = formulaDefaultUnit(option.unit);
  const converted = convertQuantity(item.quantity.target, item.quantity.unit ?? "g", nextUnit);
  patch.quantity = exactQuantity(converted ?? item.quantity.target, nextUnit);
  if (option.has_recipe) {
    patch.recipe_version_ref = option.recipe_version_ref || undefined;
    patch.composition = option.default_composition === "included" ? "included" : "additional";
    if (option.default_quantity) {
      patch.quantity = JSON.parse(JSON.stringify(option.default_quantity)) as FormulaQuantity;
    }
  } else {
    patch.recipe_version_ref = undefined;
    patch.composition = "additional";
  }
  formula.value = updateItem(formula.value, index, patch);
  newIngredientIndex.value = null;
  ingredientFocusKey.value = `ingredient-${index}-quantity`;
}
function itemMatchedName(index: number): string {
  const item = formula.value.ingredients[index];
  if (!item?.sku) return "";
  return lens.value?.ingredients.find((row) => row.ref === item.ref || row.sku === item.sku)?.name || item.name || item.sku;
}
function addIngredient() {
  const index = formula.value.ingredients.length;
  newIngredientIndex.value = index;
  formula.value = addItem(formula.value, emptyItem());
  ingredientFocusKey.value = `ingredient-${index}-picker`;
}
function remove(index: number) {
  formula.value = removeItem(formula.value, index);
  newIngredientIndex.value = null;
  ingredientFocusKey.value = null;
}
function move(index: number, delta: number) {
  formula.value = moveItem(formula.value, index, index + delta);
  newIngredientIndex.value = null;
  ingredientFocusKey.value = null;
}
function recipeVersionNumber(reference: string): string {
  return reference.split("@").at(-1) || reference;
}

// ── Âncora ──────────────────────────────────────────────────────────────────
function onAnchorKind(kind: string) {
  const next = kind as AnchorKind;
  const firstSku = formula.value.ingredients.find((item) => item.sku)?.sku ?? "";
  formula.value = setAnchor(formula.value, next, next === "ingredient" ? firstSku : "");
}
function onAnchorSku(sku: string) {
  formula.value = setAnchor(formula.value, "ingredient", sku);
}
const anchorCandidates = computed(() =>
  formula.value.ingredients
    .filter((item) => item.sku)
    .map((item) => ({ value: item.sku, label: item.name || item.sku })),
);
// Listas curtas e fixas da ficha: `NuxtSelect` (o `[...]` tira o readonly do tipo).
const yieldUnits = [...YIELD_UNIT_OPTIONS];
const quantityExpressionOptions = [
  ...UNIT_OPTIONS.map((unit) => ({ value: unit, label: unit })),
  { value: "ratio", label: "% da base" },
];
const roles = [...ROLE_OPTIONS];
const anchors = [...ANCHOR_OPTIONS];
const kinds = [...KIND_OPTIONS];
const editorTab = ref("technical");
const editorTabs = [
  { label: "Ficha técnica", value: "technical" },
  { label: "Modo de preparo", value: "preparation" },
  { label: "Produção", value: "production" },
];

// ── Quantidade e composição ─────────────────────────────────────────────────
const quantityPresets = [
  { value: "exact", label: "Exato" },
  { value: "minimum", label: "Mínimo" },
  { value: "maximum", label: "Máximo" },
  { value: "range", label: "Faixa" },
];
const compositionOptions = [
  { value: "additional", label: "Adicional" },
  { value: "included", label: "Inclusa" },
];

function onQuantityPreset(index: number, preset: string) {
  const item = formula.value.ingredients[index];
  if (!item) return;
  formula.value = updateItem(formula.value, index, {
    quantity: withQuantityPreset(item.quantity, preset as "exact" | "minimum" | "maximum" | "range"),
  });
}
function onQuantityExpression(index: number, expression: string) {
  const item = formula.value.ingredients[index];
  if (!item) return;
  if (expression !== "ratio" && item.quantity.kind === "fixed") {
    onItemUnit(index, expression);
    return;
  }
  const nextUnit = expression as FormulaUnit;
  const quantity: FormulaQuantity = expression === "ratio"
    ? { ...item.quantity, kind: "ratio", unit: undefined, basis: { kind: formula.value.anchor.kind, sku: formula.value.anchor.sku } }
    : {
        ...item.quantity,
        kind: "fixed",
        unit: nextUnit,
        basis: undefined,
        target: normalizeQuantity(item.quantity.target, nextUnit),
        minimum: item.quantity.minimum == null ? null : normalizeQuantity(item.quantity.minimum, nextUnit),
        maximum: item.quantity.maximum == null ? null : normalizeQuantity(item.quantity.maximum, nextUnit),
      };
  formula.value = updateItem(formula.value, index, { quantity });
}
function onQuantityBasis(index: number, kind: string) {
  const item = formula.value.ingredients[index];
  if (!item) return;
  formula.value = updateItem(formula.value, index, {
    quantity: { ...item.quantity, basis: { kind: kind as AnchorKind } },
  });
}
function onQuantityBasisSku(index: number, sku: string) {
  const item = formula.value.ingredients[index];
  if (!item) return;
  formula.value = updateItem(formula.value, index, {
    quantity: { ...item.quantity, basis: { kind: "ingredient", sku } },
  });
}
function onQuantityBound(index: number, field: "minimum" | "target" | "maximum", value: number | null | undefined) {
  const item = formula.value.ingredients[index];
  if (!item) return;
  formula.value = updateItem(formula.value, index, {
    quantity: { ...item.quantity, [field]: value == null ? (field === "target" ? 0 : null) : value },
  });
}
function onComposition(index: number, composition: string) {
  formula.value = updateItem(formula.value, index, { composition: composition === "included" ? "included" : "additional" });
}

function startIngredientDefaults() {
  ingredientDefaults.value = {
    quantity: exactQuantity(100, "g"),
    composition: "additional",
  };
}
function onDefaultPreset(preset: string) {
  if (!ingredientDefaults.value) return;
  ingredientDefaults.value = {
    ...ingredientDefaults.value,
    quantity: withQuantityPreset(ingredientDefaults.value.quantity, preset as "exact" | "minimum" | "maximum" | "range"),
  };
}
function onDefaultExpression(expression: string) {
  if (!ingredientDefaults.value) return;
  ingredientDefaults.value = {
    ...ingredientDefaults.value,
    quantity: expression === "ratio"
      ? { ...ingredientDefaults.value.quantity, kind: "ratio", unit: undefined, basis: { kind: "total" } }
      : { ...ingredientDefaults.value.quantity, kind: "fixed", unit: expression as FormulaUnit, basis: undefined },
  };
}
function onDefaultBound(field: "minimum" | "target" | "maximum", value: number | null | undefined) {
  if (!ingredientDefaults.value) return;
  ingredientDefaults.value = {
    ...ingredientDefaults.value,
    quantity: { ...ingredientDefaults.value.quantity, [field]: value == null ? (field === "target" ? 0 : null) : value },
  };
}
function onDefaultTarget(value: number | null | undefined) {
  if (!ingredientDefaults.value) return;
  const quantity = ingredientDefaults.value.quantity;
  ingredientDefaults.value = {
    ...ingredientDefaults.value,
    quantity: withQuantityPreset({ ...quantity, target: value ?? 0 }, quantityPreset(quantity)),
  };
}
function onDefaultBasis(kind: string) {
  if (!ingredientDefaults.value) return;
  ingredientDefaults.value = {
    ...ingredientDefaults.value,
    quantity: { ...ingredientDefaults.value.quantity, basis: { kind: kind as AnchorKind } },
  };
}
function onDefaultBasisSku(sku: string) {
  if (!ingredientDefaults.value) return;
  ingredientDefaults.value = {
    ...ingredientDefaults.value,
    quantity: { ...ingredientDefaults.value.quantity, basis: { kind: "ingredient", sku } },
  };
}

// ── Modo de preparo estruturado ────────────────────────────────────────────
function addStep() {
  steps.value = [...steps.value, { name: "" }];
}
function updateStep(index: number, patch: Partial<RecipeStepInput>) {
  steps.value = steps.value.map((step, current) => current === index ? { ...step, ...patch } : step);
}
function removeStep(index: number) {
  steps.value = steps.value.filter((_, current) => current !== index);
}
function moveStep(index: number, delta: number) {
  const target = index + delta;
  if (target < 0 || target >= steps.value.length) return;
  const next = [...steps.value];
  const [moved] = next.splice(index, 1);
  if (!moved) return;
  next.splice(target, 0, moved);
  steps.value = next;
}
function stepMinutes(step: RecipeStepInput): string {
  return step.target_seconds ? String(step.target_seconds / 60) : "";
}
function onStepMinutes(index: number, event: Event) {
  const raw = (event.target as HTMLInputElement).value.replace(",", ".");
  const minutes = Number(raw);
  updateStep(index, { target_seconds: raw && Number.isFinite(minutes) && minutes > 0 ? Math.round(minutes * 60) : null });
}
function onStepTemperature(index: number, event: Event) {
  const raw = (event.target as HTMLInputElement).value.replace(",", ".");
  const celsius = Number(raw);
  updateStep(index, { temperature_celsius: raw && Number.isFinite(celsius) ? celsius : null });
}

// ── Padronizar para 1000 g (antes/depois + desfazer) ────────────────────────
async function standardizeToHouse() {
  const snapshot = {
    formula: formula.value,
    anchorTotal: localAnchorTotal.value,
    total: localTotal.value,
    yieldQuantity: yieldQuantity.value,
  };
  const next = await standardize(HOUSE_BASIS_G);
  if (!next) return;
  before.value = snapshot;
  formula.value = next;
  // O rendimento acompanha a fórmula: 5 kg de creme sobre 5,2 kg de insumos
  // viram ~0,96 kg sobre 1 kg. Sem isto a ficha renderia mais do que pesa e a
  // publicação recusaria pelo invariante de massa.
  const factor = snapshot.anchorTotal > 0 ? HOUSE_BASIS_G / snapshot.anchorTotal : 0;
  const current = Number(String(yieldQuantity.value).replace(",", "."));
  if (factor > 0 && Number.isFinite(current) && current > 0) {
    yieldQuantity.value = String(Math.round(current * factor * 1000) / 1000);
  }
}
function undoStandardize() {
  if (!before.value) return;
  formula.value = before.value.formula;
  yieldQuantity.value = before.value.yieldQuantity;
  before.value = null;
}
const origin = computed(() => (draft.value ? originLines(draft.value.origin) : []));
const originOpen = ref(false);

// ── Salvar / publicar ───────────────────────────────────────────────────────
const saveError = ref("");
function editorSnapshot(): string {
  return JSON.stringify({
    name: entryName.value,
    kind: entryKind.value,
    outputSku: entryOutputSku.value,
    entryNotes: entryNotes.value,
    ingredientDefaults: ingredientDefaults.value,
    formula: formula.value,
    yieldQuantity: yieldQuantity.value,
    yieldUnit: yieldUnit.value,
    steps: steps.value,
    notes: notes.value,
    label: label.value,
  });
}

const editorBaseline = ref("");
function captureEditor() {
  editorBaseline.value = editorSnapshot();
}

watch(
  [entry, draft],
  async ([currentEntry, currentDraft]) => {
    if (!currentEntry || !currentDraft || editorBaseline.value) return;
    await nextTick();
    captureEditor();
  },
  { immediate: true },
);

const executionDirty = ref(false);
const recipeHasUnsavedChanges = computed(() => !!editorBaseline.value && editorSnapshot() !== editorBaseline.value);
const hasUnsavedChanges = computed(() => recipeHasUnsavedChanges.value || executionDirty.value);
const confirmDiscard = useConfirm();

async function confirmLeave(): Promise<boolean> {
  if (!hasUnsavedChanges.value) return true;
  return confirmDiscard({
    title: "Sair sem salvar a receita?",
    description: "As alterações feitas nesta ficha técnica serão perdidas.",
    confirmLabel: "Sair sem salvar",
  });
}

onBeforeRouteLeave(async () => confirmLeave());

function warnBeforeUnload(event: BeforeUnloadEvent) {
  if (!hasUnsavedChanges.value) return;
  event.preventDefault();
  event.returnValue = "";
}

onMounted(() => window.addEventListener("beforeunload", warnBeforeUnload));
onBeforeUnmount(() => window.removeEventListener("beforeunload", warnBeforeUnload));

function draftPatch() {
  return {
    formula: formula.value,
    yield_quantity: yieldQuantity.value.trim(),
    yield_unit: yieldUnit.value,
    steps: steps.value,
    notes: notes.value,
    label: label.value.trim(),
  };
}
async function save(): Promise<boolean> {
  if (!draft.value) return false;
  saveError.value = "";
  const cleanName = entryName.value.trim();
  if (!cleanName) {
    saveError.value = "Informe o nome da receita.";
    return false;
  }
  entryName.value = cleanName;
  if (steps.value.some((step) => !step.name.trim())) {
    editorTab.value = "preparation";
    saveError.value = "Dê um nome a cada etapa do modo de preparo.";
    return false;
  }
  const cleanOutputSku = entryOutputSku.value.trim().toUpperCase();
  entryOutputSku.value = cleanOutputSku;
  const entryChanged =
    cleanName !== entry.value?.name ||
    entryKind.value !== entry.value?.kind ||
    cleanOutputSku !== entry.value?.output_sku ||
    entryNotes.value !== entry.value?.notes;
  const servedDefaults = ((entry.value as typeof entry.value & { ingredient_defaults?: IngredientDefaults | null })?.ingredient_defaults) ?? null;
  const defaultsChanged = JSON.stringify(ingredientDefaults.value) !== JSON.stringify(servedDefaults);
  if (entryChanged || defaultsChanged) {
    const entryResult = await patchEntry({
      name: cleanName,
      kind: entryKind.value,
      output_sku: cleanOutputSku,
      notes: entryNotes.value,
      ingredient_defaults: ingredientDefaults.value,
      ...(entry.value?.revision ? { expectedRevision: entry.value.revision } : {}),
    });
    if (!entryResult.ok) {
      saveError.value = entryResult.message ?? "Não foi possível salvar as informações da receita.";
      return false;
    }
  }
  const result = await updateDraft(draft.value.number, draftPatch());
  if (result.ok) {
    useSonner.success("Rascunho salvo.");
    await nextTick();
    captureEditor();
    return true;
  }
  saveError.value = result.message ?? "";
  return false;
}

async function saveExecutionForm(payload: Parameters<typeof saveExecution>[0]) {
  const result = await saveExecution(payload);
  if (!result.ok) return;
  useSonner.success("Configuração da produção salva.");
}
async function saveAndPublish() {
  if (!draft.value) return;
  const number = draft.value.number;
  if (!(await save())) return;
  const result = await publish(number);
  if (result.ok) {
    useSonner.success(`Versão ${number} publicada.`);
    await navigateTo(`/recipes/${entryRef}?v=${number}`);
  } else {
    saveError.value = result.message ?? "";
  }
}

// Entrar no editor já é a intenção explícita de editar. Se ainda não existe um
// rascunho, cria a cópia de trabalho automaticamente e mantém a publicada intacta.
const draftStartAttempted = ref(false);
const draftStartError = ref("");
async function startDraft() {
  draftStartError.value = "";
  const base = entry.value?.versions[0];
  const result = await createVersion(
    base
      ? {
          ...(entry.value?.revision ? { expectedRevision: entry.value.revision } : {}),
          from_version: base.number,
          formula: formulaFromServed(base.formula),
          yield_quantity: base.yield_quantity,
          yield_unit: base.yield_unit,
          steps: stepsForPayload(base.steps),
          notes: base.notes,
          label: "",
        }
      : {
          ...(entry.value?.revision ? { expectedRevision: entry.value.revision } : {}),
          formula: emptyFormula(),
          yield_quantity: "1",
          yield_unit: "kg",
          steps: [],
          notes: "",
          label: "",
        },
  );
  if (result.ok && result.version) {
    await navigateTo(`/recipes/${entryRef}/edit?v=${result.version.number}`, { replace: true });
    return;
  }
  draftStartError.value = result.message || "Não foi possível preparar a edição.";
}

async function ensureDraft() {
  if (draftStartAttempted.value || pending.value || !entry.value?.is_active || !canEdit.value) return;
  if (draft.value) {
    if (requestedNumber.value !== draft.value.number) {
      await navigateTo(`/recipes/${entryRef}/edit?v=${draft.value.number}`, { replace: true });
    }
    return;
  }
  draftStartAttempted.value = true;
  await startDraft();
}

function retryStartDraft() {
  draftStartAttempted.value = false;
  void ensureDraft();
}

watch(
  [entry, canEdit, draft, pending],
  () => {
    if (!import.meta.server) void ensureDraft();
  },
  { immediate: true },
);

const touch = useTouchPointer();

const publishDisabledReason = computed(() => {
  if (!entryOutputSku.value.trim()) return "Associe um produto à receita antes de publicar.";
  if (unmatchedCount.value) return "Associe todos os ingredientes aos respectivos insumos antes de publicar.";
  return "";
});
const mobilePublishAction = computed<OperatorActionBarAction>(() => ({
  label: "Salvar e publicar",
  shortLabel: "Publicar",
  icon: "i-lucide-check",
  loading: busy.value,
  disabled: busy.value || !!publishDisabledReason.value,
  reason: publishDisabledReason.value,
  onSelect: () => void saveAndPublish(),
}));
const mobileSaveAction = computed<OperatorActionBarAction>(() => ({
  label: "Salvar rascunho",
  shortLabel: "Salvar",
  icon: "i-lucide-save",
  loading: busy.value,
  disabled: busy.value,
  onSelect: () => void save(),
}));
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <RecipeHeader
      :title="entry ? `Editar · ${entry.name}` : 'Editar receita'"
      :subtitle="draft ? `Rascunho · Versão ${draft.number}` : ''"
      :back="`/recipes/${entryRef}`"
      hide-refresh
    >
      <template #actions>
        <div v-if="draft && canEdit" class="hidden items-center gap-2 lg:flex">
          <NuxtButton
            color="neutral"
            variant="outline"
            icon="i-lucide-save"
            aria-label="Salvar rascunho"
            :disabled="busy"
            @click="save"
          >
            <span class="hidden sm:inline">Salvar rascunho</span>
          </NuxtButton>
          <NuxtButton
            icon="i-lucide-check"
            aria-label="Salvar e publicar"
            :disabled="busy || unmatchedCount > 0 || !entryOutputSku.trim()"
            :title="!entryOutputSku.trim() ? 'Associe um produto à receita antes de publicar' : unmatchedCount ? 'Associe todos os ingredientes aos respectivos insumos antes de publicar' : ''"
            @click="saveAndPublish"
          >
            <span class="hidden sm:inline">Salvar e publicar</span>
          </NuxtButton>
        </div>
      </template>
    </RecipeHeader>

    <section v-if="forbidden || (!pending && entry && !canEdit)" class="grid flex-1 place-items-center p-6 text-center">
      <div class="grid max-w-md gap-2 rounded-md border border-dashed p-10">
        <Icon name="lucide:lock" class="mx-auto size-8 text-muted-foreground" />
        <p class="text-base font-semibold">Só leitura</p>
        <p class="text-sm text-muted-foreground">Editar receitas pede a permissão de gestão da produção.</p>
        <NuxtLink :to="`/recipes/${entryRef}`" class="mt-1 text-sm text-primary underline-offset-2 hover:underline">Ver a receita</NuxtLink>
      </div>
    </section>

    <section v-else-if="notFound" class="grid flex-1 place-items-center p-6 text-center">
      <div class="grid max-w-md gap-2 rounded-md border border-dashed p-10">
        <Icon name="lucide:book-x" class="mx-auto size-8 text-muted-foreground" />
        <p class="text-base font-semibold">Receita não encontrada</p>
        <NuxtLink to="/recipes" class="mt-1 text-sm text-primary underline-offset-2 hover:underline">Voltar às receitas</NuxtLink>
      </div>
    </section>

    <section v-else class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <p v-if="pending && !entry" class="text-sm text-muted-foreground">Carregando…</p>

      <div
        v-else-if="error && !entry"
        class="grid place-items-center gap-2 rounded-md border border-dashed border-destructive/30 py-16 text-center text-muted-foreground"
      >
        <Icon name="lucide:cloud-off" class="size-8 text-destructive/70" />
        <p class="text-base font-medium text-foreground">Não foi possível carregar a receita.</p>
        <NuxtButton
          class="mt-1"
          color="neutral"
          variant="outline"
          icon="i-lucide-refresh-cw"
          label="Tentar de novo"
          @click="refresh()"
        />
      </div>

      <div
        v-else-if="entry && !draft"
        class="grid place-items-center gap-2 rounded-md border border-dashed py-16 text-center text-muted-foreground"
      >
        <Icon :name="draftStartError ? 'lucide:circle-alert' : 'lucide:loader-circle'" :class="['size-8', { 'animate-spin': !draftStartError }]" />
        <p class="text-base font-medium text-foreground">{{ draftStartError ? "Não foi possível abrir a edição." : "Preparando edição…" }}</p>
        <p class="text-sm">A versão publicada permanece intacta enquanto você edita.</p>
        <NuxtButton
          v-if="draftStartError && entry.is_active"
          class="mt-1"
          color="neutral"
          variant="outline"
          icon="i-lucide-refresh-cw"
          label="Tentar novamente"
          :disabled="busy"
          @click="retryStartDraft"
        />
      </div>

      <div
        v-else-if="entry && draft"
        class="mx-auto grid w-full max-w-6xl gap-4"
        :class="editorTab === 'technical' ? 'xl:grid-cols-[minmax(0,3fr)_minmax(20rem,2fr)]' : ''"
      >
        <NuxtTabs
          v-model="editorTab"
          :items="editorTabs"
          :content="false"
          variant="pill"
          class="w-full xl:col-span-full"
          aria-label="Seções da receita"
        />
        <NuxtAlert
          v-if="saveError"
          class="xl:col-span-full"
          color="error"
          variant="subtle"
          icon="i-lucide-circle-alert"
          :title="saveError"
          :actions="alertActions('error', [{ label: 'Salvar de novo', disabled: busy, onClick: () => save() }])"
        />
        <!-- ── Editor ──────────────────────────────────────────────────── -->
        <div class="grid min-w-0 content-start gap-4">
          <section v-if="editorTab === 'technical'" class="grid gap-3 rounded-md border bg-card p-3">
            <h2 class="text-sm font-semibold">Informações da receita</h2>
            <div class="grid gap-3 sm:grid-cols-2">
              <NuxtFormField label="Nome da receita" required>
                <NuxtInput v-model="entryName" class="w-full" :ui="{ base: 'bg-muted' }" />
              </NuxtFormField>
              <NuxtFormField label="Tipo">
                <NuxtSelect v-model="entryKind" :items="kinds" value-key="value" label-key="label" class="w-full" :ui="{ base: 'bg-muted' }" />
              </NuxtFormField>
              <NuxtFormField
                label="Produto associado (SKU)"
                description="Obrigatório para publicar e usar esta receita na produção."
                required
              >
                <NuxtInput v-model="entryOutputSku" class="w-full uppercase" placeholder="Ex.: PAO-FRANCES" :ui="{ base: 'bg-muted' }" />
              </NuxtFormField>
              <NuxtFormField label="Observações gerais">
                <NuxtTextarea v-model="entryNotes" :rows="3" class="w-full" :ui="{ base: 'bg-muted' }" />
              </NuxtFormField>
            </div>
          </section>

          <details v-if="editorTab === 'technical'" class="group rounded-md border bg-card">
            <summary class="flex cursor-pointer list-none items-center gap-3 p-3">
              <div class="min-w-0 flex-1">
                <h2 class="text-sm font-semibold">Padrão ao usar como ingrediente</h2>
                <p class="text-xs text-muted-foreground">É apenas uma sugestão. Cada receita recebe uma cópia independente.</p>
              </div>
              <Icon name="lucide:chevron-down" class="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
            </summary>
            <div class="grid gap-3 border-t p-3">
              <div v-if="!ingredientDefaults" class="grid gap-3 text-sm text-muted-foreground">
                <p>Nenhum padrão definido. Ao inserir esta receita como ingrediente, a quantidade será informada na receita de destino.</p>
                <NuxtButton class="w-full justify-center sm:w-auto" color="neutral" variant="outline" label="Definir padrão" @click="startIngredientDefaults" />
              </div>
              <template v-else>
                <NuxtFormField label="Critério">
                  <NuxtSelect
                    :model-value="quantityPreset(ingredientDefaults.quantity)"
                    :items="quantityPresets"
                    value-key="value"
                    class="w-full"
                    :ui="{ base: 'bg-muted' }"
                    @update:model-value="onDefaultPreset"
                  />
                </NuxtFormField>
                <template v-if="quantityPreset(ingredientDefaults.quantity) === 'range'">
                  <div class="grid gap-2 sm:grid-cols-3">
                    <NuxtFormField v-for="field in (['minimum', 'target', 'maximum'] as const)" :key="field" :label="field === 'minimum' ? 'Mínimo' : field === 'target' ? 'Alvo' : 'Máximo'">
                      <NuxtInputNumber
                        :model-value="ingredientDefaults.quantity[field]"
                        :min="0"
                        :step="ingredientDefaults.quantity.kind === 'ratio' ? percentageRule.step : quantityRule(ingredientDefaults.quantity.unit ?? 'g').step"
                        locale="pt-BR"
                        class="w-full"
                        :ui="{ base: 'bg-muted tabular-nums' }"
                        @update:model-value="(value: number | null | undefined) => onDefaultBound(field, value)"
                      />
                    </NuxtFormField>
                  </div>
                  <NuxtFormField label="Expressa em">
                    <NuxtSelect
                      :model-value="ingredientDefaults.quantity.kind === 'ratio' ? 'ratio' : ingredientDefaults.quantity.unit ?? 'g'"
                      :items="quantityExpressionOptions"
                      value-key="value"
                      class="w-full"
                      :ui="{ base: 'bg-muted' }"
                      @update:model-value="onDefaultExpression"
                    />
                  </NuxtFormField>
                </template>
                <OperatorFieldRow v-else>
                  <template #value>
                    <NuxtFormField label="Quantidade">
                      <NuxtInputNumber
                        :model-value="ingredientDefaults.quantity.target"
                        :min="0"
                        :step="ingredientDefaults.quantity.kind === 'ratio' ? percentageRule.step : quantityRule(ingredientDefaults.quantity.unit ?? 'g').step"
                        locale="pt-BR"
                        class="w-full"
                        :ui="{ base: 'bg-muted tabular-nums' }"
                        @update:model-value="onDefaultTarget"
                      />
                    </NuxtFormField>
                  </template>
                  <template #context>
                    <NuxtFormField label="Expressa em">
                      <NuxtSelect
                        :model-value="ingredientDefaults.quantity.kind === 'ratio' ? 'ratio' : ingredientDefaults.quantity.unit ?? 'g'"
                        :items="quantityExpressionOptions"
                        value-key="value"
                        class="w-full"
                        :ui="{ base: 'bg-muted' }"
                        @update:model-value="onDefaultExpression"
                      />
                    </NuxtFormField>
                  </template>
                </OperatorFieldRow>
                <NuxtFormField v-if="ingredientDefaults.quantity.kind === 'ratio'" label="Base">
                  <NuxtSelect
                    :model-value="ingredientDefaults.quantity.basis?.kind ?? 'total'"
                    :items="anchors"
                    value-key="value"
                    class="w-full"
                    :ui="{ base: 'bg-muted' }"
                    @update:model-value="onDefaultBasis"
                  />
                </NuxtFormField>
                <NuxtFormField v-if="ingredientDefaults.quantity.kind === 'ratio' && ingredientDefaults.quantity.basis?.kind === 'ingredient'" label="Ingrediente da base">
                  <NuxtSelectMenu
                    :model-value="ingredientDefaults.quantity.basis.sku || undefined"
                    :items="anchorCandidates"
                    value-key="value"
                    placeholder="Escolha o ingrediente"
                    class="w-full"
                    aria-label="Ingrediente padrão usado como base percentual"
                    @update:model-value="onDefaultBasisSku"
                  />
                </NuxtFormField>
                <NuxtFormField label="Composição" description="Adicional aumenta a fórmula. Inclusa redistribui ingredientes já previstos nela.">
                  <NuxtSelect v-model="ingredientDefaults.composition" :items="compositionOptions" value-key="value" class="w-full" :ui="{ base: 'bg-muted' }" />
                </NuxtFormField>
                <NuxtButton class="w-full justify-center sm:w-auto" color="neutral" variant="ghost" label="Remover padrão" @click="ingredientDefaults = null" />
              </template>
            </div>
          </details>

          <section v-if="editorTab === 'technical'" class="grid gap-3 rounded-md border bg-card p-3">
            <div>
              <h2 class="text-sm font-semibold">Rendimento</h2>
              <p class="text-xs text-muted-foreground">Quantidade obtida ao executar esta fórmula uma vez.</p>
            </div>
            <div class="grid grid-cols-[minmax(0,1fr)_minmax(6rem,0.55fr)] gap-2">
              <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                Quantidade
                <NuxtInputNumber
                  :key="`yield-quantity-${yieldUnit}`"
                  v-model="yieldQuantityNumber"
                  :min="quantityRule(yieldUnit as FormulaUnit).min"
                  :step="quantityRule(yieldUnit as FormulaUnit).step"
                  :format-options="{ maximumFractionDigits: quantityRule(yieldUnit as FormulaUnit).maximumFractionDigits }"
                  locale="pt-BR"
                  class="w-full"
                  :ui="{ base: 'bg-muted tabular-nums' }"
                  aria-label="Quantidade do rendimento"
                />
              </label>
              <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                Unidade
                <NuxtSelect
                  :model-value="yieldUnit"
                  :items="yieldUnits"
                  class="w-full"
                  aria-label="Unidade do rendimento"
                  :ui="{ base: 'bg-muted' }"
                  @update:model-value="onYieldUnit"
                />
              </label>
            </div>
          </section>

          <!-- Ingredientes -->
          <section v-if="editorTab === 'technical'" class="overflow-hidden rounded-md border bg-card">
            <div class="grid gap-3 border-b p-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
              <div>
                <h2 class="text-sm font-semibold">Ingredientes</h2>
                <p class="text-xs text-muted-foreground">Cada ingrediente pode ser comprado ou preparado pela casa a partir de outra receita.</p>
              </div>
              <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                Base do cálculo (100%)
                <span class="grid gap-2 sm:flex sm:flex-wrap sm:items-center">
                  <NuxtSelect
                    :model-value="formula.anchor.kind"
                    :items="anchors"
                    value-key="value"
                    class="w-full sm:w-44"
                    aria-label="Base do cálculo (100%)"
                    :ui="{ base: 'bg-muted' }"
                    @update:model-value="onAnchorKind"
                  />
                  <NuxtSelectMenu
                    v-if="formula.anchor.kind === 'ingredient'"
                    :model-value="formula.anchor.sku || undefined"
                    :items="anchorCandidates"
                    value-key="value"
                    placeholder="Escolha o ingrediente"
                    class="w-full sm:w-48"
                    :search-input="{ autofocus: !touch, placeholder: 'Buscar ingrediente' }"
                    aria-label="Ingrediente usado como base do cálculo"
                    @update:model-value="onAnchorSku"
                  />
                </span>
              </label>
            </div>
            <div class="grid gap-2 border-b bg-muted/40 px-3 py-2 sm:flex sm:flex-wrap sm:items-center">
              <span class="text-xs tabular-nums text-muted-foreground" data-testid="formula-summary">
                Base {{ gramsLabel(localAnchorTotal) }} · Massa total {{ gramsLabel(localTotal) }}
              </span>
            </div>
            <div v-if="!formula.ingredients.length" class="grid gap-3 px-3 py-6 text-center">
              <p class="text-sm text-muted-foreground">Adicione o primeiro ingrediente da receita.</p>
              <NuxtButton
                class="w-full justify-center sm:mx-auto sm:w-auto"
                color="primary"
                icon="i-lucide-plus"
                label="Adicionar ingrediente"
                @click="addIngredient"
              />
            </div>
            <template v-else>
            <ol class="grid gap-3 bg-muted/30 p-3" data-testid="recipe-bom-items">
              <li
                v-for="(item, index) in formula.ingredients"
                :key="item.ref"
                :data-focus-target="`ingredient-${index}-picker`"
                class="scroll-mt-20 overflow-hidden rounded-md border bg-card outline-none"
              >
                <header class="grid gap-2 border-b p-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
                  <div class="grid min-w-0 gap-1 text-xs font-medium text-muted-foreground">
                    Ingrediente
                    <IngredientPicker
                      :model-value="item.sku"
                      :matched-name="itemMatchedName(index)"
                      :auto-open="newIngredientIndex === index"
                      data-focus-control
                      @update:model-value="onItemSku(index, $event)"
                      @select="onItemSelect(index, $event)"
                    />
                  </div>
                  <div class="grid grid-cols-3 gap-1 sm:flex sm:justify-end" data-ingredient-actions>
                    <NuxtButton color="neutral" variant="ghost" aria-label="Subir ingrediente" :disabled="index === 0" @click="move(index, -1)">
                      <NuxtIcon name="i-lucide-chevron-up" aria-hidden="true" />
                      <span class="sm:sr-only">Subir</span>
                    </NuxtButton>
                    <NuxtButton color="neutral" variant="ghost" aria-label="Descer ingrediente" :disabled="index === formula.ingredients.length - 1" @click="move(index, 1)">
                      <NuxtIcon name="i-lucide-chevron-down" aria-hidden="true" />
                      <span class="sm:sr-only">Descer</span>
                    </NuxtButton>
                    <NuxtButton color="error" variant="ghost" aria-label="Remover ingrediente" @click="remove(index)">
                      <NuxtIcon name="i-lucide-trash-2" aria-hidden="true" />
                      <span class="sm:sr-only">Remover</span>
                    </NuxtButton>
                  </div>
                  <div v-if="item.recipe_version_ref" class="flex items-center gap-2 text-xs text-muted-foreground sm:col-span-2">
                    <NuxtBadge color="neutral" label="Prep" />
                    <span>Versão {{ recipeVersionNumber(item.recipe_version_ref) }}</span>
                  </div>
                </header>

                <div class="grid gap-4 p-3 lg:grid-cols-[minmax(0,1.35fr)_minmax(16rem,0.65fr)]">
                  <fieldset class="grid min-w-0 content-start gap-3" data-ingredient-quantity-group>
                    <legend class="text-sm font-semibold">Quantidade</legend>
                    <p class="text-xs text-muted-foreground">Quanto entra na receita.</p>

                  <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                    Critério
                    <NuxtSelect
                      :model-value="quantityPreset(item.quantity)"
                      :items="quantityPresets"
                      value-key="value"
                      class="w-full"
                      :ui="{ base: 'bg-muted' }"
                      :aria-label="`Critério da quantidade de ${item.name || 'ingrediente'}`"
                      @update:model-value="(preset: string) => onQuantityPreset(index, preset)"
                    />
                  </label>

                  <OperatorFieldRow
                    v-if="quantityPreset(item.quantity) !== 'range'"
                    data-ingredient-quantity-grid
                  >
                    <template #value>
                      <label :data-focus-target="`ingredient-${index}-quantity`" class="grid min-w-0 scroll-mt-20 gap-1 text-xs font-medium text-muted-foreground">
                        Quantidade
                        <NuxtInputNumber
                          :key="`quantity-${item.sku || index}-${item.quantity.kind}-${item.quantity.unit || 'ratio'}`"
                          :model-value="item.quantity.target || null"
                          :min="item.quantity.kind === 'ratio' ? percentageRule.min : quantityRule(item.quantity.unit ?? 'g').min"
                          :step="item.quantity.kind === 'ratio' ? percentageRule.step : quantityRule(item.quantity.unit ?? 'g').step"
                          :format-options="{ maximumFractionDigits: item.quantity.kind === 'ratio' ? percentageRule.maximumFractionDigits : quantityRule(item.quantity.unit ?? 'g').maximumFractionDigits }"
                          locale="pt-BR"
                          class="w-full"
                          :ui="{ base: 'bg-muted tabular-nums' }"
                          aria-label="Quantidade"
                          data-focus-control
                          @update:model-value="(value: number | null | undefined) => onItemQuantity(index, value)"
                        />
                      </label>
                    </template>
                    <template #context>
                      <label class="grid min-w-0 gap-1 text-xs font-medium text-muted-foreground">
                        Expressa em
                        <NuxtSelect
                          :model-value="item.quantity.kind === 'ratio' ? 'ratio' : item.quantity.unit ?? 'g'"
                          :items="quantityExpressionOptions"
                          value-key="value"
                          class="min-w-0 w-full"
                          :ui="{ base: 'bg-muted' }"
                          :aria-label="`Quantidade de ${item.name || 'ingrediente'} expressa em`"
                          @update:model-value="(expression: string) => onQuantityExpression(index, expression)"
                        />
                      </label>
                    </template>
                  </OperatorFieldRow>

                  <template v-else>
                    <div class="grid gap-2 sm:grid-cols-3" data-ingredient-quantity-range>
                      <label v-for="field in (['minimum', 'target', 'maximum'] as const)" :key="field" class="grid min-w-0 gap-1 text-xs font-medium text-muted-foreground">
                        {{ field === 'minimum' ? 'Mínimo' : field === 'target' ? 'Alvo' : 'Máximo' }}
                        <NuxtInputNumber
                          :model-value="item.quantity[field]"
                          :min="item.quantity.kind === 'ratio' ? 0.1 : quantityRule(item.quantity.unit ?? 'g').min"
                          :step="item.quantity.kind === 'ratio' ? percentageRule.step : quantityRule(item.quantity.unit ?? 'g').step"
                          locale="pt-BR"
                          class="w-full"
                          :ui="{ base: 'bg-muted tabular-nums' }"
                          @update:model-value="(value: number | null | undefined) => onQuantityBound(index, field, value)"
                        />
                      </label>
                    </div>
                    <label class="grid min-w-0 gap-1 text-xs font-medium text-muted-foreground">
                      Expressa em
                      <NuxtSelect
                        :model-value="item.quantity.kind === 'ratio' ? 'ratio' : item.quantity.unit ?? 'g'"
                        :items="quantityExpressionOptions"
                        value-key="value"
                        class="min-w-0 w-full"
                        :ui="{ base: 'bg-muted' }"
                        :aria-label="`Quantidade de ${item.name || 'ingrediente'} expressa em`"
                        @update:model-value="(expression: string) => onQuantityExpression(index, expression)"
                      />
                    </label>
                  </template>

                  <template v-if="item.quantity.kind === 'ratio'">
                    <label class="grid min-w-0 gap-1 text-xs font-medium text-muted-foreground">
                      Base
                      <NuxtSelect
                        :model-value="item.quantity.basis?.kind ?? 'total'"
                        :items="anchors"
                        value-key="value"
                        class="min-w-0 w-full"
                        :ui="{ base: 'bg-muted' }"
                        :aria-label="`Base percentual de ${item.name || 'ingrediente'}`"
                        @update:model-value="(kind: string) => onQuantityBasis(index, kind)"
                      />
                    </label>
                    <label v-if="item.quantity.basis?.kind === 'ingredient'" class="grid min-w-0 gap-1 text-xs font-medium text-muted-foreground">
                      Ingrediente da base
                      <NuxtSelectMenu
                        :model-value="item.quantity.basis.sku || undefined"
                        :items="anchorCandidates"
                        value-key="value"
                        placeholder="Escolha o ingrediente"
                        class="min-w-0 w-full"
                        aria-label="Ingrediente usado como base percentual"
                        @update:model-value="(sku: string) => onQuantityBasisSku(index, sku)"
                      />
                    </label>
                  </template>

                  <label v-if="item.quantity.kind === 'fixed' && item.quantity.unit === 'un'" class="grid gap-1 text-xs font-medium text-muted-foreground">
                    Gramas por unidade
                    <span class="font-normal">Necessário para incluir a contagem no peso da receita.</span>
                    <NuxtInput
                      :model-value="String(item.grams_per_unit ?? '')"
                      type="text"
                      inputmode="decimal"
                      class="w-full"
                      :ui="{ base: 'bg-muted' }"
                      @input="onItemGramsPerUnit(index, $event)"
                    />
                  </label>
                  </fieldset>

                  <NuxtCard
                    v-if="item.sku"
                    variant="soft"
                    data-ingredient-formula-group
                  >
                    <div class="grid min-w-0 content-start gap-3">
                    <div>
                      <h3 class="text-sm font-semibold">Na fórmula</h3>
                      <p class="text-xs text-muted-foreground">Como este ingrediente participa.</p>
                    </div>
                    <dl v-if="pctOf(item, localAnchorTotal)" class="flex items-center justify-between gap-3 border-b pb-2 text-sm">
                      <dt class="text-xs text-muted-foreground">Participação</dt>
                      <dd class="font-medium tabular-nums">{{ pctOf(item, localAnchorTotal) }}% da base</dd>
                    </dl>
                    <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                      Papel
                      <NuxtSelect
                        :model-value="item.role"
                        :items="roles"
                        value-key="value"
                        class="w-full"
                        :ui="{ base: 'bg-muted' }"
                        :aria-label="`Papel na fórmula de ${item.name || 'ingrediente'}`"
                        @update:model-value="(role: string) => onItemRole(index, role)"
                      />
                    </label>
                    <label v-if="item.recipe_version_ref" class="grid gap-1 text-xs font-medium text-muted-foreground">
                      Composição
                      <NuxtSelect
                        :model-value="item.composition"
                        :items="compositionOptions"
                        value-key="value"
                        class="w-full"
                        :ui="{ base: 'bg-muted' }"
                        @update:model-value="(composition: string) => onComposition(index, composition)"
                      />
                      <span class="font-normal">Adicional soma à fórmula. Inclusa redistribui ingredientes já previstos.</span>
                    </label>
                    </div>
                  </NuxtCard>
                </div>
              </li>
            </ol>
            <div class="border-t p-3" data-testid="add-ingredient-footer">
              <NuxtButton
                class="w-full justify-center sm:w-auto"
                color="primary"
                icon="i-lucide-plus"
                label="Adicionar ingrediente"
                @click="addIngredient"
              />
            </div>
            </template>
          </section>

          <section v-if="editorTab === 'preparation'" class="overflow-hidden rounded-md border bg-card">
            <div class="flex flex-wrap items-start gap-3 border-b p-3">
              <div>
                <h2 class="text-sm font-semibold">Modo de preparo</h2>
                <p class="text-xs text-muted-foreground">Registre cada etapa com instrução, tempo, temperatura e ponto de referência.</p>
              </div>
              <NuxtButton class="ml-auto" color="neutral" variant="outline" icon="i-lucide-plus" label="Etapa" @click="addStep" />
            </div>
            <p v-if="!steps.length" class="px-3 py-8 text-center text-sm text-muted-foreground">
              Nenhuma etapa informada. Adicione a primeira etapa do preparo.
            </p>
            <ol v-else class="divide-y">
              <li v-for="(step, index) in steps" :key="index" class="grid gap-3 p-3 sm:grid-cols-2">
                <div class="flex items-end gap-2 sm:col-span-2">
                  <NuxtFormField :label="`Etapa ${index + 1}`" required class="min-w-0 flex-1">
                    <NuxtInput
                      :model-value="step.name"
                      class="w-full"
                      placeholder="Ex.: Misturar, sovar, fermentar"
                      :ui="{ base: 'bg-muted' }"
                      @update:model-value="updateStep(index, { name: String($event) })"
                    />
                  </NuxtFormField>
                  <div class="flex shrink-0 items-center">
                    <NuxtButton icon="i-lucide-chevron-up" color="neutral" variant="ghost" square aria-label="Subir etapa" :disabled="index === 0" @click="moveStep(index, -1)" />
                    <NuxtButton icon="i-lucide-chevron-down" color="neutral" variant="ghost" square aria-label="Descer etapa" :disabled="index === steps.length - 1" @click="moveStep(index, 1)" />
                    <NuxtButton icon="i-lucide-trash-2" color="error" variant="ghost" square aria-label="Remover etapa" @click="removeStep(index)" />
                  </div>
                </div>
                <NuxtFormField label="Instruções" class="sm:col-span-2">
                  <NuxtTextarea
                    :model-value="step.instructions ?? ''"
                    :rows="3"
                    class="w-full"
                    placeholder="Descreva o gesto e o ponto esperado."
                    :ui="{ base: 'bg-muted' }"
                    @update:model-value="updateStep(index, { instructions: String($event) })"
                  />
                </NuxtFormField>
                <NuxtFormField label="Tempo previsto (min)">
                  <NuxtInput :model-value="stepMinutes(step)" inputmode="decimal" class="w-full" :ui="{ base: 'bg-muted' }" @input="onStepMinutes(index, $event)" />
                </NuxtFormField>
                <NuxtFormField label="Temperatura (°C)">
                  <NuxtInput :model-value="String(step.temperature_celsius ?? '')" inputmode="decimal" class="w-full" :ui="{ base: 'bg-muted' }" @input="onStepTemperature(index, $event)" />
                </NuxtFormField>
                <NuxtFormField label="Ponto de referência ou cuidado" class="sm:col-span-2">
                  <NuxtTextarea
                    :model-value="step.note ?? ''"
                    :rows="2"
                    class="w-full"
                    placeholder="Ex.: parar ao atingir o ponto de véu."
                    :ui="{ base: 'bg-muted' }"
                    @update:model-value="updateStep(index, { note: String($event) })"
                  />
                </NuxtFormField>
              </li>
            </ol>
          </section>

          <section v-if="editorTab === 'preparation'" class="grid gap-3 rounded-md border bg-card p-3">
            <div>
              <h2 class="text-sm font-semibold">Registro desta versão</h2>
              <p class="text-xs text-muted-foreground">Contexto para quem consultar o histórico da receita.</p>
            </div>
            <NuxtFormField label="Resumo da alteração" description="Um rótulo curto para reconhecer esta versão no histórico.">
              <NuxtInput v-model="label" type="text" placeholder="Ex.: hidratação ajustada para 75%" class="w-full" :ui="{ base: 'bg-muted' }" />
            </NuxtFormField>
            <NuxtFormField label="Notas da versão">
              <NuxtTextarea v-model="notes" :rows="3" class="w-full" :ui="{ base: 'bg-muted' }" />
            </NuxtFormField>
          </section>

          <section v-if="editorTab === 'production'" class="grid gap-3">
            <div>
              <h2 class="text-base font-semibold">Configuração da produção</h2>
              <p class="text-sm text-muted-foreground">Regras de planejamento, lote e validade desta receita.</p>
            </div>
            <RecipeExecutionFormPanel
              v-if="entry.execution?.exists"
              v-model:dirty="executionDirty"
              :execution="entry.execution"
              :busy="busy"
              @save="saveExecutionForm"
            />
            <div v-else class="grid place-items-center gap-2 rounded-md border border-dashed bg-card px-4 py-10 text-center">
              <Icon name="lucide:info" class="size-6 text-muted-foreground" />
              <p class="text-sm font-medium">Publique a primeira versão para configurar a produção.</p>
            </div>
          </section>
        </div>

        <!-- ── Resumo da fórmula ───────────────────────────────────────── -->
        <aside v-if="editorTab === 'technical'" class="grid min-w-0 content-start gap-3 xl:sticky xl:top-0 xl:self-start">
          <div class="grid gap-2 sm:flex sm:flex-wrap sm:items-center">
            <p class="text-xs font-medium uppercase tracking-wider text-muted-foreground">Resumo da fórmula</p>
            <Icon v-if="lensPending" name="lucide:loader-circle" class="size-4 animate-spin text-muted-foreground" />
            <NuxtButton
              class="w-full justify-center sm:ml-auto sm:w-auto"
              color="neutral"
              variant="outline"
              icon="i-lucide-scale"
              :label="standardizing ? 'Padronizando…' : `Padronizar para ${HOUSE_BASIS_G} g ${anchorNoun}`"
              :disabled="standardizing || !formula.ingredients.length"
              @click="standardizeToHouse"
            />
          </div>

          <div v-if="before" class="grid gap-1 rounded-md border bg-muted/40 px-3 py-2 text-sm">
            <p class="font-medium">Padronizada para {{ gramsLabel(HOUSE_BASIS_G) }} {{ anchorNoun }}</p>
            <p class="tabular-nums text-muted-foreground">
              Antes: base {{ gramsLabel(before.anchorTotal) }} · massa {{ gramsLabel(before.total) }}
              <br />
              Depois: base {{ gramsLabel(localAnchorTotal) }} · massa {{ gramsLabel(localTotal) }}
            </p>
            <NuxtButton class="justify-self-start" color="primary" variant="ghost" label="Desfazer" @click="undoStandardize" />
          </div>

          <FormulaLens :lens="lens" :pending="lensPending" :error="lensError" compact />

          <div v-if="origin.length" class="rounded-md border">
            <!-- Cabeçalho de disclosure ocupa a linha inteira; é o acionador estrutural do painel. -->
            <NuxtButton
              color="neutral"
              variant="ghost"
              block
              :icon="originOpen ? 'i-lucide-chevron-down' : 'i-lucide-chevron-right'"
              label="Como foi informada"
              :ui="{ base: 'justify-start px-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground' }"
              :aria-expanded="originOpen"
              @click="originOpen = !originOpen"
            />
            <ul v-if="originOpen" class="divide-y border-t text-sm">
              <li v-for="(line, index) in origin" :key="index" class="px-3 py-1.5 text-muted-foreground">{{ line }}</li>
            </ul>
          </div>
        </aside>
      </div>
    </section>

    <OperatorActionBar
      v-if="draft && canEdit && editorTab !== 'production'"
      :action="mobilePublishAction"
      :secondary="mobileSaveAction"
      :context-label="hasUnsavedChanges ? 'Alterações ainda não salvas' : `Rascunho da versão ${draft.number}`"
      label="Salvar receita"
    />
  </main>
</template>
