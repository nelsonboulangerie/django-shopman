<script setup lang="ts">
import { alertActions } from "../../../../../operator-kit/app/utils/alertActions";
import type { OperatorActionBarAction } from "../../../../../operator-kit/app/presentation/actionBar";
// O editor do rascunho (/recipes/[ref]/edit?v=n). Rendimento, âncora, a tabela
// editável (ingrediente com busca, quantidade, unidade, papel), partes, etapas e
// notas; à direita a PRÉVIA DA LENTE, recalculada pelo servidor com debounce. O
// botão "Padronizar para 1000 g" mostra o antes/depois e deixa desfazer; a receita
// como foi informada (`origin`) fica visível como referência histórica. "Salvar
// rascunho" grava; "Salvar e publicar" grava e publica, voltando à receita.
import type { AnchorKind, Formula, FormulaUnit, IngredientOptionProjection, IngredientRole, PartKind, RecipeKind, RecipeStepInput, RecipeVersionProjection } from "~/types/recipeBook";
import {
  ANCHOR_OPTIONS,
  HOUSE_BASIS_G,
  KIND_OPTIONS,
  PART_KIND_OPTIONS,
  ROLE_OPTIONS,
  UNIT_OPTIONS,
  YIELD_UNIT_OPTIONS,
  addItem,
  addPart,
  anchorTotalOf,
  emptyFormula,
  emptyItem,
  emptyPart,
  formulaFromServed,
  gramsLabel,
  moveItem,
  originLines,
  pctOf,
  partReferenceCode,
  referenceGuidance,
  removeItem,
  removePart,
  roleLabel,
  setAnchor,
  stepsForPayload,
  totalMassOf,
  unmatchedItems,
  updateItem,
  updatePart,
} from "~/presentation/recipeBook";

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
    entrySeeded.value = true;
  },
  { immediate: true },
);

const kind = computed(() => entry.value?.kind ?? "other");
const { lens, pending: lensPending, error: lensError, standardizing, standardize } = useFormulaLens(formula, kind);
const { ranges: referenceRanges } = useRecipeReference(entryKind);

// ── Feedback imediato (a conta oficial é a lente) ───────────────────────────
const localAnchorTotal = computed(() => anchorTotalOf(formula.value));
const localTotal = computed(() => totalMassOf(formula.value));
const anchorIsFlour = computed(() => formula.value.anchor.kind === "flour");
// O padrão da casa vale para qualquer âncora: 1000 g de farinha no pão, 1000 g
// de massa total num creme, 1000 g do ingrediente-âncora numa ganache.
const anchorNoun = computed(() => {
  if (formula.value.anchor.kind === "flour") return "de farinha";
  if (formula.value.anchor.kind === "ingredient") return "do ingrediente-base";
  return "de massa total";
});
const unmatchedCount = computed(() => (lens.value ? unmatchedItems(lens.value.items).length : 0));

// ── Itens ───────────────────────────────────────────────────────────────────
const quantityRules: Record<FormulaUnit, { step: number; min: number; maximumFractionDigits: number }> = {
  g: { step: 1, min: 1, maximumFractionDigits: 0 },
  kg: { step: 0.001, min: 0.001, maximumFractionDigits: 3 },
  ml: { step: 1, min: 1, maximumFractionDigits: 0 },
  L: { step: 0.001, min: 0.001, maximumFractionDigits: 3 },
  un: { step: 1, min: 1, maximumFractionDigits: 0 },
};
const massFactor: Partial<Record<FormulaUnit, number>> = { g: 1, kg: 1000 };
const volumeFactor: Partial<Record<FormulaUnit, number>> = { ml: 1, L: 1000 };
const roleEditorIndex = ref<number | null>(null);
const newIngredientIndex = ref<number | null>(null);
const ingredientFocusKey = ref<string | null>(null);
useNextFocus(ingredientFocusKey);
const yieldQuantityNumber = computed<number | null>({
  get: () => {
    const value = Number(String(yieldQuantity.value).replace(",", "."));
    return Number.isFinite(value) && value > 0 ? value : null;
  },
  set: (value) => {
    yieldQuantity.value = value == null ? "" : String(normalizedQuantity(value, yieldUnit.value as FormulaUnit));
  },
});

function quantityRule(unit: FormulaUnit) {
  return quantityRules[unit];
}
function normalizedQuantity(value: number, unit: FormulaUnit): number {
  const precision = quantityRules[unit].maximumFractionDigits;
  const factor = 10 ** precision;
  return Math.round((value + Number.EPSILON) * factor) / factor;
}
function convertedQuantity(quantity: number, from: FormulaUnit, to: FormulaUnit): number | null {
  const factors = massFactor[from] && massFactor[to] ? massFactor : volumeFactor[from] && volumeFactor[to] ? volumeFactor : null;
  if (!factors) return from === to ? quantity : null;
  return Number((quantity * (factors[from] ?? 1) / (factors[to] ?? 1)).toFixed(3));
}
function formulaDefaultUnit(unit: string): FormulaUnit {
  if (unit === "kg" || unit === "g") return "g";
  if (unit === "L" || unit === "ml") return "ml";
  return "un";
}
function onItemQuantity(index: number, value: number | null | undefined) {
  const item = formula.value.items[index];
  if (!item) return;
  formula.value = updateItem(formula.value, index, { quantity: value == null ? 0 : normalizedQuantity(value, item.unit) });
}
function onItemUnit(index: number, unit: string) {
  const item = formula.value.items[index];
  if (!item) return;
  const next = unit as FormulaUnit;
  const converted = convertedQuantity(item.quantity, item.unit, next);
  formula.value = updateItem(formula.value, index, { unit: next, quantity: converted ?? item.quantity });
  if (converted === null && item.quantity > 0) {
    useSonner.info("Quantidade mantida. Massa, volume e unidade não têm conversão automática entre si.");
  }
}
function onYieldUnit(unit: string) {
  const from = yieldUnit.value as FormulaUnit;
  const next = unit as FormulaUnit;
  const current = yieldQuantityNumber.value;
  if (current != null) {
    const converted = convertedQuantity(current, from, next);
    yieldQuantity.value = String(converted ?? current);
    if (converted === null) {
      useSonner.info("Rendimento mantido. Massa, volume e unidade não têm conversão automática entre si.");
    }
  }
  yieldUnit.value = next;
}
function onItemRole(index: number, role: string) {
  formula.value = updateItem(formula.value, index, { role: role as IngredientRole });
  roleEditorIndex.value = null;
}
function onItemGramsPerUnit(index: number, event: Event) {
  const raw = (event.target as HTMLInputElement).value.replace(",", ".");
  formula.value = updateItem(formula.value, index, { grams_per_unit: raw ? Number(raw) || null : null });
}
function onItemSku(index: number, sku: string) {
  formula.value = updateItem(formula.value, index, sku ? { sku } : { sku: "", name: "" });
}
function onItemSelect(index: number, option: IngredientOptionProjection) {
  const item = formula.value.items[index];
  if (!item) return;
  // A BOM tem um único tipo de linha: ingrediente. A origem do item escolhido
  // decide apenas qual estrutura o motor recebe. Não obriga o operador a saber,
  // antes de buscar, se o ingrediente é comprado ou produzido pela casa.
  if (option.is_part) {
    const partIndex = formula.value.parts.length;
    const partKind = (option.suggested_part_kind || "component") as PartKind;
    const partUnit = formulaDefaultUnit(option.unit);
    const partQuantity = convertedQuantity(item.quantity, item.unit, partUnit) ?? item.quantity;
    const part = {
      ...emptyPart(partKind),
      sku: option.sku,
      entry_ref: option.entry_ref,
      quantity: anchorIsFlour.value && partKind !== "component" ? null : partQuantity || null,
      unit: partUnit,
    };
    formula.value = addPart(removeItem(formula.value, index), part);
    newIngredientIndex.value = null;
    ingredientFocusKey.value = `part-${partIndex}-amount`;
    return;
  }
  const patch: Partial<typeof item> = { sku: option.sku, name: option.name };
  if (ROLE_OPTIONS.some((role) => role.value === option.role)) patch.role = option.role as IngredientRole;
  const nextUnit = formulaDefaultUnit(option.unit);
  patch.quantity = convertedQuantity(item.quantity, item.unit, nextUnit) ?? item.quantity;
  patch.unit = nextUnit;
  formula.value = updateItem(formula.value, index, patch);
  roleEditorIndex.value = null;
  newIngredientIndex.value = null;
  ingredientFocusKey.value = `ingredient-${index}-quantity`;
}
function itemMatchedName(index: number): string {
  const item = formula.value.items[index];
  if (!item?.sku) return "";
  return lens.value?.items.find((row) => row.sku === item.sku)?.name || item.name || item.sku;
}
function addIngredient() {
  const index = formula.value.items.length;
  newIngredientIndex.value = index;
  formula.value = addItem(formula.value, emptyItem());
  ingredientFocusKey.value = `ingredient-${index}-picker`;
}
function remove(index: number) {
  formula.value = removeItem(formula.value, index);
  roleEditorIndex.value = null;
  newIngredientIndex.value = null;
  ingredientFocusKey.value = null;
}
function move(index: number, delta: number) {
  formula.value = moveItem(formula.value, index, index + delta);
  roleEditorIndex.value = null;
  newIngredientIndex.value = null;
  ingredientFocusKey.value = null;
}

// ── Âncora ──────────────────────────────────────────────────────────────────
function onAnchorKind(kind: string) {
  const next = kind as AnchorKind;
  const firstSku = formula.value.items.find((item) => item.sku)?.sku ?? "";
  formula.value = setAnchor(formula.value, next, next === "ingredient" ? firstSku : "");
}
function onAnchorSku(sku: string) {
  formula.value = setAnchor(formula.value, "ingredient", sku);
}
const anchorCandidates = computed(() =>
  formula.value.items
    .filter((item) => item.sku)
    .map((item) => ({ value: item.sku, label: item.name || item.sku })),
);
// Listas curtas e fixas da ficha: `NuxtSelect` (o `[...]` tira o readonly do tipo).
const yieldUnits = [...YIELD_UNIT_OPTIONS];
const units = [...UNIT_OPTIONS];
const roles = [...ROLE_OPTIONS];
const anchors = [...ANCHOR_OPTIONS];
const partKinds = [...PART_KIND_OPTIONS];
const kinds = [...KIND_OPTIONS];
const editorTab = ref("technical");
const editorTabs = [
  { label: "Ficha técnica", value: "technical" },
  { label: "Modo de preparo", value: "preparation" },
  { label: "Produção", value: "production" },
];

// ── Partes ──────────────────────────────────────────────────────────────────
function onPartKind(index: number, kind: string) {
  const next = kind as PartKind;
  if (next === "old_dough") {
    formula.value = updatePart(formula.value, index, { kind: next, cap_pct: 20, flour_pct: null, quantity: null });
    return;
  }
  formula.value = updatePart(
    formula.value,
    index,
    next === "component" || !anchorIsFlour.value
      ? { kind: next, cap_pct: null, flour_pct: null }
      : { kind: next, cap_pct: null, quantity: null },
  );
}
function onPartSku(index: number, sku: string) {
  formula.value = updatePart(formula.value, index, { sku });
}
function onPartSelect(index: number, option: IngredientOptionProjection) {
  formula.value = updatePart(formula.value, index, { sku: option.sku, entry_ref: option.entry_ref });
}
function onPartNumber(index: number, field: "flour_pct" | "quantity" | "cap_pct", event: Event) {
  const raw = (event.target as HTMLInputElement).value.replace(",", ".");
  const value = raw ? Number(raw) || null : null;
  formula.value = updatePart(formula.value, index, {
    [field]: value == null ? null : normalizedQuantity(value, "kg"),
  });
}
function onPartQuantity(index: number, value: number | null | undefined) {
  const part = formula.value.parts[index];
  const unit = (part?.unit ?? "g") as FormulaUnit;
  formula.value = updatePart(formula.value, index, { quantity: value == null ? null : normalizedQuantity(value, unit) });
}
function onPartUnit(index: number, unit: string) {
  const part = formula.value.parts[index];
  if (!part) return;
  const next = unit as FormulaUnit;
  const current = part.quantity ?? null;
  const converted = current == null ? null : convertedQuantity(current, part.unit ?? "g", next);
  formula.value = updatePart(formula.value, index, { unit: next, quantity: converted ?? current });
}
function dropPart(index: number) {
  formula.value = removePart(formula.value, index);
}
function partMatchedName(index: number): string {
  const part = formula.value.parts[index];
  if (!part?.sku) return "";
  return lens.value?.parts.find((row) => row.sku === part.sku)?.name || part.sku;
}
function partGuidance(index: number): string {
  const part = formula.value.parts[index];
  if (!part) return "";
  const code = partReferenceCode(part, partMatchedName(index));
  return referenceGuidance(referenceRanges.value.find((range) => range.code === code));
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
  if (entryChanged) {
    const entryResult = await patchEntry({
      name: cleanName,
      kind: entryKind.value,
      output_sku: cleanOutputSku,
      notes: entryNotes.value,
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
                <p class="text-xs text-muted-foreground">Cada ingrediente pode ser comprado ou produzido pela casa a partir de outra receita.</p>
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
              <span class="text-xs tabular-nums text-muted-foreground">
                base {{ gramsLabel(localAnchorTotal) }} · massa total {{ gramsLabel(localTotal) }}
              </span>
            </div>
            <div v-if="!formula.items.length && !formula.parts.length" class="grid gap-3 px-3 py-6 text-center">
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
            <ol class="divide-y" data-testid="recipe-bom-items">
              <li
                v-for="(item, index) in formula.items"
                :key="`item-${index}`"
                :data-focus-target="`ingredient-${index}-picker`"
                class="grid scroll-mt-20 gap-3 p-3 outline-none sm:grid-cols-[minmax(0,1fr)_auto]"
                :class="item.role === 'flour' && anchorIsFlour ? 'bg-primary/5' : ''"
              >
                <div class="grid gap-1 text-xs font-medium text-muted-foreground sm:col-span-2">
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
                <div class="grid grid-cols-[minmax(0,1fr)_minmax(6rem,0.55fr)] gap-2">
                  <label :data-focus-target="`ingredient-${index}-quantity`" class="grid scroll-mt-20 gap-1 text-xs font-medium text-muted-foreground">
                    Quantidade
                    <NuxtInputNumber
                      :key="`quantity-${item.sku || index}-${item.unit}`"
                      :model-value="item.quantity || null"
                      :min="quantityRule(item.unit).min"
                      :step="quantityRule(item.unit).step"
                      :format-options="{ maximumFractionDigits: quantityRule(item.unit).maximumFractionDigits }"
                      locale="pt-BR"
                      class="w-full"
                      :ui="{ base: 'bg-muted tabular-nums' }"
                      aria-label="Quantidade"
                      data-focus-control
                      @update:model-value="(value: number | null | undefined) => onItemQuantity(index, value)"
                    />
                  </label>
                  <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                    Unidade
                    <NuxtSelect
                      :model-value="item.unit"
                      :items="units"
                      class="w-full"
                      :ui="{ base: 'bg-muted' }"
                      :aria-label="`Unidade de ${item.name || 'ingrediente'}`"
                      @update:model-value="(unit: string) => onItemUnit(index, unit)"
                    />
                  </label>
                </div>
                <div class="flex items-end justify-end gap-1">
                  <span class="mb-2 w-12 text-right text-sm tabular-nums text-muted-foreground" :title="'Percentual sobre a base do cálculo (prévia local)'">
                    {{ pctOf(item, localAnchorTotal) ? `${pctOf(item, localAnchorTotal)}%` : "" }}
                  </span>
                  <!-- A microbarra da linha: ordenar e remover, ícones `ghost`. -->
                  <NuxtButton icon="i-lucide-chevron-up" color="neutral" variant="ghost" square aria-label="Subir" :disabled="index === 0" @click="move(index, -1)" />
                  <NuxtButton icon="i-lucide-chevron-down" color="neutral" variant="ghost" square aria-label="Descer" :disabled="index === formula.items.length - 1" @click="move(index, 1)" />
                  <NuxtButton icon="i-lucide-trash-2" color="error" variant="ghost" square aria-label="Remover ingrediente" @click="remove(index)" />
                </div>
                <div v-if="item.sku && roleEditorIndex !== index" class="flex min-w-0 items-center gap-2 sm:col-span-2">
                  <span class="text-xs text-muted-foreground">Papel na fórmula:</span>
                  <NuxtBadge color="neutral" variant="soft" :label="roleLabel(item.role)" />
                  <NuxtButton
                    class="ml-auto"
                    color="neutral"
                    variant="ghost"
                    size="xs"
                    label="Alterar"
                    :aria-label="`Alterar papel na fórmula de ${item.name || 'ingrediente'}`"
                    @click="roleEditorIndex = index"
                  />
                </div>
                <label v-else-if="item.sku" class="grid gap-1 text-xs font-medium text-muted-foreground sm:col-span-2">
                  Papel na fórmula
                  <span class="font-normal">Define como este ingrediente participa dos percentuais e conversões.</span>
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
                <label v-if="item.unit === 'un'" class="grid gap-1 text-xs font-medium text-muted-foreground sm:col-span-2">
                  Gramas por unidade (sem isso a contagem fica fora da conta)
                  <NuxtInput
                    :model-value="String(item.grams_per_unit ?? '')"
                    type="text"
                    inputmode="decimal"
                    class="w-28"
                    :ui="{ base: 'bg-muted' }"
                    @input="onItemGramsPerUnit(index, $event)"
                  />
                </label>
              </li>
              <li
                v-for="(part, index) in formula.parts"
                :key="`recipe-${index}`"
                class="grid gap-3 p-3 sm:grid-cols-[minmax(10rem,0.9fr)_minmax(0,1.4fr)_minmax(13rem,1fr)_auto]"
              >
                <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                  Uso na receita
                  <NuxtSelect
                    :model-value="part.kind"
                    :items="partKinds"
                    value-key="value"
                    class="w-full"
                    aria-label="Uso da receita como ingrediente"
                    :ui="{ base: 'bg-muted' }"
                    @update:model-value="(kind: string) => onPartKind(index, kind)"
                  />
                </label>
                <template v-if="part.kind === 'old_dough'">
                  <p class="self-end pb-2 text-sm text-muted-foreground">Massa da própria receita, reservada da produção anterior.</p>
                  <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                    Limite de substituição
                    <NuxtInput
                      :model-value="String(part.cap_pct ?? '')"
                      type="number"
                      inputmode="decimal"
                      min="0.001"
                      max="99.999"
                      step="0.1"
                      placeholder="0"
                      class="w-full sm:w-40"
                      :ui="{ base: 'bg-muted tabular-nums text-right' }"
                      aria-label="Limite percentual de substituição por massa velha"
                      @input="onPartNumber(index, 'cap_pct', $event)"
                    >
                      <template #trailing><span class="text-sm text-muted-foreground">%</span></template>
                    </NuxtInput>
                    <span v-if="partGuidance(index)" class="font-normal text-muted-foreground">{{ partGuidance(index) }}</span>
                  </label>
                </template>
                <template v-else>
                  <div class="grid min-w-0 gap-1 text-xs font-medium text-muted-foreground">
                    Ingrediente
                    <IngredientPicker
                      :model-value="part.sku ?? ''"
                      :matched-name="partMatchedName(index)"
                      @update:model-value="onPartSku(index, $event)"
                      @select="onPartSelect(index, $event)"
                    />
                  </div>
                  <label v-if="anchorIsFlour && part.kind !== 'component'" :data-focus-target="`part-${index}-amount`" class="grid scroll-mt-20 gap-1 text-xs font-medium text-muted-foreground">
                    Base de cálculo nesta preparação
                    <NuxtInput
                      data-focus-control
                      :model-value="String(part.flour_pct ?? '')"
                      type="number"
                      inputmode="decimal"
                      min="0.001"
                      max="100"
                      step="0.1"
                      placeholder="0"
                      class="w-full"
                      :ui="{ base: 'bg-muted tabular-nums text-right' }"
                      aria-label="Percentual da base de cálculo nesta preparação"
                      @input="onPartNumber(index, 'flour_pct', $event)"
                    >
                      <template #trailing><span class="text-sm text-muted-foreground">%</span></template>
                    </NuxtInput>
                    <span v-if="partGuidance(index)" class="font-normal text-muted-foreground">{{ partGuidance(index) }}</span>
                  </label>
                  <label v-else :data-focus-target="`part-${index}-amount`" class="grid scroll-mt-20 gap-1 text-xs font-medium text-muted-foreground">
                    Quantidade
                    <span class="grid grid-cols-[minmax(0,1fr)_minmax(6rem,0.55fr)] gap-2">
                      <NuxtInputNumber
                        data-focus-control
                        :key="`part-quantity-${part.sku || index}-${part.unit}`"
                        :model-value="part.quantity ?? null"
                        :min="quantityRule((part.unit ?? 'g') as FormulaUnit).min"
                        :step="quantityRule((part.unit ?? 'g') as FormulaUnit).step"
                        :format-options="{ maximumFractionDigits: quantityRule((part.unit ?? 'g') as FormulaUnit).maximumFractionDigits }"
                        locale="pt-BR"
                        class="w-full"
                        :ui="{ base: 'bg-muted tabular-nums' }"
                        aria-label="Quantidade da receita usada como ingrediente"
                        @update:model-value="(value: number | null | undefined) => onPartQuantity(index, value)"
                      />
                      <NuxtSelect
                        :model-value="part.unit ?? 'g'"
                        :items="units"
                        class="w-full"
                        aria-label="Unidade da parte"
                        :ui="{ base: 'bg-muted' }"
                        @update:model-value="(unit: string) => onPartUnit(index, unit)"
                      />
                    </span>
                  </label>
                </template>
                <div class="flex items-end">
                  <!-- Remoção compacta pertence à linha editável; mantém o alinhamento da grade. -->
                  <NuxtButton icon="i-lucide-trash-2" color="error" variant="ghost" square aria-label="Remover ingrediente" @click="dropPart(index)" />
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
              :disabled="standardizing || !formula.items.length"
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
