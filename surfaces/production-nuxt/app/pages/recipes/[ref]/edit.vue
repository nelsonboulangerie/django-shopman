<script setup lang="ts">
import { alertActions } from "../../../../../operator-kit/app/utils/alertActions";
// O editor do rascunho (/recipes/[ref]/edit?v=n). Rendimento, âncora, a tabela
// editável (nome, insumo com busca, quantidade, unidade, papel), partes, etapas e
// notas; à direita a PRÉVIA DA LENTE, recalculada pelo servidor com debounce. O
// botão "Padronizar para 1000 g" mostra o antes/depois e deixa desfazer; a receita
// como foi informada (`origin`) fica visível como referência histórica. "Salvar
// rascunho" grava; "Salvar e publicar" grava e publica, voltando à receita.
import type { AnchorKind, Formula, FormulaUnit, IngredientOptionProjection, IngredientRole, PartKind, RecipeKind, RecipeVersionProjection } from "~/types/recipeBook";
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
  removeItem,
  removePart,
  setAnchor,
  stepsForPayload,
  stepsFromText,
  stepsToText,
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
const stepsText = ref("");
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
    stepsText.value = stepsToText(version.steps);
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

// ── Feedback imediato (a conta oficial é a lente) ───────────────────────────
const localAnchorTotal = computed(() => anchorTotalOf(formula.value));
const localTotal = computed(() => totalMassOf(formula.value));
const anchorIsFlour = computed(() => formula.value.anchor.kind === "flour");
// O padrão da casa vale para qualquer âncora: 1000 g de farinha no pão, 1000 g
// de massa total num creme, 1000 g do ingrediente-âncora numa ganache.
const anchorNoun = computed(() => {
  if (formula.value.anchor.kind === "flour") return "de farinha";
  if (formula.value.anchor.kind === "ingredient") return "do ingrediente âncora";
  return "de massa total";
});
const unmatchedCount = computed(() => (lens.value ? unmatchedItems(lens.value.items).length : 0));

// ── Itens ───────────────────────────────────────────────────────────────────
function onItemName(index: number, event: Event) {
  formula.value = updateItem(formula.value, index, { name: (event.target as HTMLInputElement).value });
}
function onItemQuantity(index: number, event: Event) {
  const raw = (event.target as HTMLInputElement).value.replace(",", ".");
  formula.value = updateItem(formula.value, index, { quantity: Number(raw) || 0 });
}
function onItemUnit(index: number, unit: string) {
  formula.value = updateItem(formula.value, index, { unit: unit as FormulaUnit });
}
function onItemRole(index: number, role: string) {
  formula.value = updateItem(formula.value, index, { role: role as IngredientRole });
}
function onItemGramsPerUnit(index: number, event: Event) {
  const raw = (event.target as HTMLInputElement).value.replace(",", ".");
  formula.value = updateItem(formula.value, index, { grams_per_unit: raw ? Number(raw) || null : null });
}
function onItemSku(index: number, sku: string) {
  formula.value = updateItem(formula.value, index, { sku });
}
function onItemSelect(index: number, option: IngredientOptionProjection) {
  const item = formula.value.items[index];
  if (!item) return;
  const patch: Partial<typeof item> = { sku: option.sku };
  if (!item.name.trim()) patch.name = option.name;
  if (item.role === "other" && ROLE_OPTIONS.some((role) => role.value === option.role)) {
    patch.role = option.role as IngredientRole;
  }
  formula.value = updateItem(formula.value, index, patch);
}
function itemMatchedName(index: number): string {
  const item = formula.value.items[index];
  if (!item?.sku) return "";
  return lens.value?.items.find((row) => row.sku === item.sku)?.name || item.name || item.sku;
}
function add() {
  formula.value = addItem(formula.value, emptyItem({ role: formula.value.items.length ? "other" : "flour" }));
}
function remove(index: number) {
  formula.value = removeItem(formula.value, index);
}
function move(index: number, delta: number) {
  formula.value = moveItem(formula.value, index, index + delta);
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
const executionModeLabel = computed(() => {
  const execution = entry.value?.execution;
  if (!execution) return "";
  return execution.production_mode_options.find((option) => option.value === execution.production_mode)?.label || execution.production_mode;
});

// ── Partes ──────────────────────────────────────────────────────────────────
function addNewPart() {
  formula.value = addPart(formula.value, emptyPart("preferment"));
}
function onPartKind(index: number, kind: string) {
  const next = kind as PartKind;
  formula.value = updatePart(formula.value, index, next === "old_dough" ? { kind: next, cap_pct: 20 } : { kind: next, cap_pct: null });
}
function onPartSku(index: number, sku: string) {
  formula.value = updatePart(formula.value, index, { sku });
}
function onPartSelect(index: number, option: IngredientOptionProjection) {
  formula.value = updatePart(formula.value, index, { sku: option.sku, entry_ref: option.entry_ref });
}
function onPartNumber(index: number, field: "flour_pct" | "quantity" | "cap_pct", event: Event) {
  const raw = (event.target as HTMLInputElement).value.replace(",", ".");
  formula.value = updatePart(formula.value, index, { [field]: raw ? Number(raw) || null : null });
}
function onPartUnit(index: number, unit: string) {
  formula.value = updatePart(formula.value, index, { unit: unit as FormulaUnit });
}
function dropPart(index: number) {
  formula.value = removePart(formula.value, index);
}
function partMatchedName(index: number): string {
  const part = formula.value.parts[index];
  if (!part?.sku) return "";
  return lens.value?.parts.find((row) => row.sku === part.sku)?.name || part.sku;
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
const executionOpen = ref(false);

function editorSnapshot(): string {
  return JSON.stringify({
    name: entryName.value,
    kind: entryKind.value,
    outputSku: entryOutputSku.value,
    entryNotes: entryNotes.value,
    formula: formula.value,
    yieldQuantity: yieldQuantity.value,
    yieldUnit: yieldUnit.value,
    stepsText: stepsText.value,
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

const hasUnsavedChanges = computed(() => !!editorBaseline.value && editorSnapshot() !== editorBaseline.value);
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
    // O textarea edita nomes; o que a etapa de mesmo nome já tinha segue junto.
    steps: stepsFromText(stepsText.value, draft.value?.steps ?? []),
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
  executionOpen.value = false;
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
        <template v-if="draft && canEdit">
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
        </template>
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

      <div v-else-if="entry && draft" class="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(20rem,2fr)]">
        <!-- ── Editor ──────────────────────────────────────────────────── -->
        <div class="grid min-w-0 content-start gap-4">
          <NuxtAlert
            v-if="saveError"
            color="error"
            variant="subtle"
            icon="i-lucide-circle-alert"
            :title="saveError"
            :actions="alertActions('error', [{ label: 'Salvar de novo', disabled: busy, onClick: () => save() }])"
          />

          <section class="grid gap-3 rounded-md border bg-card p-3">
            <h2 class="text-sm font-semibold">Informações da receita</h2>
            <div class="grid gap-3 sm:grid-cols-2">
              <NuxtFormField label="Nome da receita" required>
                <NuxtInput v-model="entryName" class="w-full" />
              </NuxtFormField>
              <NuxtFormField label="Tipo">
                <NuxtSelect v-model="entryKind" :items="kinds" value-key="value" label-key="label" class="w-full" />
              </NuxtFormField>
              <NuxtFormField
                label="Produto associado (SKU)"
                description="Obrigatório para publicar e usar esta receita na produção."
                required
              >
                <NuxtInput v-model="entryOutputSku" class="w-full uppercase" placeholder="Ex.: PAO-FRANCES" />
              </NuxtFormField>
              <NuxtFormField label="Observações gerais">
                <NuxtTextarea v-model="entryNotes" :rows="3" class="w-full" />
              </NuxtFormField>
            </div>
          </section>

          <!-- Rendimento, âncora, o que mudou -->
          <section class="grid gap-3 rounded-md border bg-card p-3">
            <h2 class="text-sm font-semibold">Rendimento</h2>
            <div class="grid gap-3 sm:grid-cols-[auto_auto_1fr]">
            <label class="grid gap-1 text-xs font-medium text-muted-foreground">
              Rendimento
              <span class="flex items-center gap-1">
                <NuxtInput v-model="yieldQuantity" type="text" inputmode="decimal" class="w-20" />
                <NuxtSelect v-model="yieldUnit" :items="yieldUnits" class="w-24" aria-label="Unidade do rendimento" />
              </span>
            </label>
            <label class="grid gap-1 text-xs font-medium text-muted-foreground">
              Âncora (100%)
              <span class="flex items-center gap-1">
                <NuxtSelect
                  :model-value="formula.anchor.kind"
                  :items="anchors"
                  value-key="value"
                  class="w-44"
                  aria-label="Âncora (100%)"
                  @update:model-value="onAnchorKind"
                />
                <NuxtSelectMenu
                  v-if="formula.anchor.kind === 'ingredient'"
                  :model-value="formula.anchor.sku || undefined"
                  :items="anchorCandidates"
                  value-key="value"
                  placeholder="Escolha o ingrediente"
                  class="w-48"
                  :search-input="{ autofocus: !touch, placeholder: 'Buscar ingrediente' }"
                  aria-label="Ingrediente-âncora"
                  @update:model-value="onAnchorSku"
                />
              </span>
            </label>
            <label class="grid gap-1 text-xs font-medium text-muted-foreground">
              O que mudou (rótulo curto)
              <NuxtInput v-model="label" type="text" placeholder="Ex.: hidratação 72 → 75" class="w-full" />
            </label>
            </div>
          </section>

          <!-- Ingredientes -->
          <div class="rounded-md border">
            <div class="flex flex-wrap items-center gap-2 border-b bg-muted/40 px-3 py-2">
              <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Ingredientes</p>
              <span class="text-xs tabular-nums text-muted-foreground">
                âncora {{ gramsLabel(localAnchorTotal) }} · massa {{ gramsLabel(localTotal) }}
              </span>
              <NuxtButton class="ml-auto" color="neutral" variant="outline" icon="i-lucide-plus" label="Ingrediente" @click="add" />
            </div>
            <p v-if="!formula.items.length" class="px-3 py-6 text-center text-sm text-muted-foreground">
              Adicione os ingredientes da receita, inclusive os usados nos pré-preparos.
            </p>
            <ol v-else class="divide-y">
              <li
                v-for="(item, index) in formula.items"
                :key="index"
                class="grid gap-2 p-3 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1.4fr)_auto_auto_auto_auto]"
                :class="item.role === 'flour' && anchorIsFlour ? 'bg-primary/5' : ''"
              >
                <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                  Nome
                  <NuxtInput :model-value="item.name" type="text" placeholder="Ex.: Farinha T65" class="w-full" @input="onItemName(index, $event)" />
                </label>
                <div class="grid gap-1 text-xs font-medium text-muted-foreground">
                  Insumo
                  <IngredientPicker
                    :model-value="item.sku"
                    :matched-name="itemMatchedName(index)"
                    @update:model-value="onItemSku(index, $event)"
                    @select="onItemSelect(index, $event)"
                  />
                </div>
                <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                  Qtd
                  <NuxtInput
                    :model-value="String(item.quantity || '')"
                    type="text"
                    inputmode="decimal"
                    class="w-24"
                    :ui="{ base: 'text-right tabular-nums' }"
                    @input="onItemQuantity(index, $event)"
                  />
                </label>
                <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                  Un
                  <NuxtSelect
                    :model-value="item.unit"
                    :items="units"
                    class="w-24"
                    :aria-label="`Unidade de ${item.name || 'ingrediente'}`"
                    @update:model-value="(unit: string) => onItemUnit(index, unit)"
                  />
                </label>
                <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                  Função no cálculo
                  <NuxtSelect
                    :model-value="item.role"
                    :items="roles"
                    value-key="value"
                    class="w-36"
                    :aria-label="`Papel de ${item.name || 'ingrediente'}`"
                    @update:model-value="(role: string) => onItemRole(index, role)"
                  />
                </label>
                <div class="flex items-end gap-1">
                  <span class="mb-2 w-12 text-right text-sm tabular-nums text-muted-foreground" :title="'Percentual sobre a âncora (prévia local)'">
                    {{ pctOf(item, localAnchorTotal) ? `${pctOf(item, localAnchorTotal)}%` : "" }}
                  </span>
                  <!-- A microbarra da linha: ordenar e remover, ícones `ghost`. -->
                  <NuxtButton icon="i-lucide-chevron-up" color="neutral" variant="ghost" square aria-label="Subir" :disabled="index === 0" @click="move(index, -1)" />
                  <NuxtButton icon="i-lucide-chevron-down" color="neutral" variant="ghost" square aria-label="Descer" :disabled="index === formula.items.length - 1" @click="move(index, 1)" />
                  <NuxtButton icon="i-lucide-trash-2" color="error" variant="ghost" square aria-label="Remover ingrediente" @click="remove(index)" />
                </div>
                <label v-if="item.unit === 'un'" class="grid gap-1 text-xs font-medium text-muted-foreground sm:col-span-6">
                  Gramas por unidade (sem isso a contagem fica fora da conta)
                  <NuxtInput
                    :model-value="String(item.grams_per_unit ?? '')"
                    type="text"
                    inputmode="decimal"
                    class="w-28"
                    @input="onItemGramsPerUnit(index, $event)"
                  />
                </label>
              </li>
            </ol>
          </div>

          <!-- Pré-preparos -->
          <div class="rounded-md border">
            <div class="flex flex-wrap items-center gap-2 border-b bg-muted/40 px-3 py-2">
              <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Pré-preparos</p>
              <span class="text-xs text-muted-foreground">levain, autólise, grãos hidratados ou massa velha usados nesta receita</span>
              <NuxtButton class="ml-auto" color="neutral" variant="outline" icon="i-lucide-plus" label="Pré-preparo" @click="addNewPart" />
            </div>
            <p v-if="!formula.parts.length" class="px-3 py-4 text-center text-sm text-muted-foreground">
              Nenhum pré-preparo separado. Todos os ingredientes entram diretamente no modo de preparo.
            </p>
            <ol v-else class="divide-y">
              <li v-for="(part, index) in formula.parts" :key="index" class="grid gap-2 p-3 sm:grid-cols-[auto_minmax(0,1.4fr)_auto_auto_auto]">
                <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                  Tipo
                  <NuxtSelect
                    :model-value="part.kind"
                    :items="partKinds"
                    value-key="value"
                    class="w-44"
                    aria-label="Tipo da parte"
                    @update:model-value="(kind: string) => onPartKind(index, kind)"
                  />
                </label>
                <template v-if="part.kind === 'old_dough'">
                  <p class="self-end pb-2 text-sm text-muted-foreground sm:col-span-2">A própria base da véspera; declara só o teto.</p>
                  <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                    Teto (%)
                    <NuxtInput :model-value="String(part.cap_pct ?? '')" type="text" inputmode="decimal" class="w-20" :ui="{ base: 'text-right' }" @input="onPartNumber(index, 'cap_pct', $event)" />
                  </label>
                </template>
                <template v-else>
                  <div class="grid gap-1 text-xs font-medium text-muted-foreground">
                    Receita da parte (SKU)
                    <IngredientPicker
                      :model-value="part.sku ?? ''"
                      :matched-name="partMatchedName(index)"
                      placeholder="Buscar levain, poolish…"
                      @update:model-value="onPartSku(index, $event)"
                      @select="onPartSelect(index, $event)"
                    />
                  </div>
                  <label v-if="anchorIsFlour" class="grid gap-1 text-xs font-medium text-muted-foreground">
                    Farinha (%)
                    <NuxtInput :model-value="String(part.flour_pct ?? '')" type="text" inputmode="decimal" class="w-20" :ui="{ base: 'text-right' }" @input="onPartNumber(index, 'flour_pct', $event)" />
                  </label>
                  <label v-else class="grid gap-1 text-xs font-medium text-muted-foreground">
                    Quantidade
                    <span class="flex items-center gap-1">
                      <NuxtInput :model-value="String(part.quantity ?? '')" type="text" inputmode="decimal" class="w-20" :ui="{ base: 'text-right' }" @input="onPartNumber(index, 'quantity', $event)" />
                      <NuxtSelect
                        :model-value="part.unit ?? 'g'"
                        :items="units"
                        class="w-24"
                        aria-label="Unidade da parte"
                        @update:model-value="(unit: string) => onPartUnit(index, unit)"
                      />
                    </span>
                  </label>
                  <span v-if="anchorIsFlour" class="hidden sm:block" />
                </template>
                <div class="flex items-end">
                  <!-- Remoção compacta pertence à linha editável; mantém o alinhamento da grade. -->
                  <NuxtButton icon="i-lucide-trash-2" color="error" variant="ghost" square aria-label="Remover parte" @click="dropPart(index)" />
                </div>
              </li>
            </ol>
          </div>

          <!-- Modo de preparo e notas -->
          <section class="grid gap-3 rounded-md border bg-card p-3">
            <h2 class="text-sm font-semibold">Modo de preparo</h2>
            <label class="grid gap-1 text-xs font-medium text-muted-foreground">
              Etapas (uma por linha)
              <NuxtTextarea v-model="stepsText" :rows="6" placeholder="Autólise 40 min&#10;Sova até o ponto de véu&#10;…" class="w-full" />
            </label>
            <label class="grid gap-1 text-xs font-medium text-muted-foreground">
              Notas desta versão
              <NuxtTextarea v-model="notes" :rows="3" class="w-full" />
            </label>
          </section>

          <section class="grid gap-3 rounded-md border bg-card p-3">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="grid gap-1">
                <h2 class="text-sm font-semibold">Configuração da produção</h2>
                <p class="text-sm text-muted-foreground">Regras de planejamento, lote e validade desta receita.</p>
              </div>
              <NuxtButton
                v-if="entry.execution?.exists"
                color="neutral"
                variant="outline"
                icon="i-lucide-settings-2"
                label="Editar configuração"
                @click="executionOpen = true"
              />
            </div>
            <dl v-if="entry.execution?.exists" class="grid gap-2 text-sm sm:grid-cols-3">
              <div>
                <dt class="text-xs text-muted-foreground">Modo de produção</dt>
                <dd class="font-medium">{{ executionModeLabel }}</dd>
              </div>
              <div>
                <dt class="text-xs text-muted-foreground">Capacidade por dia</dt>
                <dd class="font-medium">{{ entry.execution.capacity_per_day || "Sem limite definido" }}</dd>
              </div>
              <div>
                <dt class="text-xs text-muted-foreground">Validade</dt>
                <dd class="font-medium">
                  {{ entry.execution.shelf_life_days == null ? "Não informada" : `${entry.execution.shelf_life_days} ${entry.execution.shelf_life_days === 1 ? "dia" : "dias"}` }}
                </dd>
              </div>
            </dl>
            <p v-else class="text-sm text-muted-foreground">
              Publique a primeira versão para configurar como esta receita entra no planejamento e na produção.
            </p>
          </section>
        </div>

        <!-- ── Resumo da fórmula ───────────────────────────────────────── -->
        <aside class="grid min-w-0 content-start gap-3 xl:sticky xl:top-0 xl:self-start">
          <div class="flex flex-wrap items-center gap-2">
            <p class="text-xs font-medium uppercase tracking-wider text-muted-foreground">Resumo da fórmula</p>
            <Icon v-if="lensPending" name="lucide:loader-circle" class="size-4 animate-spin text-muted-foreground" />
            <NuxtButton
              class="ml-auto"
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
              Antes: âncora {{ gramsLabel(before.anchorTotal) }} · massa {{ gramsLabel(before.total) }}
              <br />
              Depois: âncora {{ gramsLabel(localAnchorTotal) }} · massa {{ gramsLabel(localTotal) }}
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

    <RecipeExecutionFormPanel
      v-if="entry?.execution"
      v-model:open="executionOpen"
      :execution="entry.execution"
      :busy="busy"
      @save="saveExecutionForm"
    />
  </main>
</template>
