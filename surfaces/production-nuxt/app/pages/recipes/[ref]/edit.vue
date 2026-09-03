<script setup lang="ts">
// O editor do rascunho (/recipes/[ref]/edit?v=n). Rendimento, âncora, a tabela
// editável (nome, insumo com busca, quantidade, unidade, papel), partes, passos e
// notas; à direita a PRÉVIA DA LENTE, recalculada pelo servidor com debounce. O
// botão "Padronizar para 1000 g" mostra o antes/depois e deixa desfazer; a receita
// como foi informada (`origin`) fica visível como referência histórica. "Salvar
// rascunho" grava; "Salvar e publicar" grava e publica, voltando à receita.
import type { AnchorKind, Formula, FormulaUnit, IngredientOptionProjection, IngredientRole, PartKind, RecipeVersionProjection } from "~/types/recipeBook";
import {
  ANCHOR_OPTIONS,
  HOUSE_BASIS_G,
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
  stepsFromText,
  stepsToText,
  totalMassOf,
  unmatchedItems,
  updateItem,
  updatePart,
} from "~/presentation/recipeBook";

const route = useRoute();
const entryRef = String(route.params.ref ?? "");

const { entry, canEdit, latestDraft, versionByNumber, notFound, forbidden, pending, error, refresh, busy, createVersion, updateDraft, publish } =
  useRecipeEntry(entryRef);

useHead({ title: computed(() => `Editar · ${entry.value?.name || "Receita"} · Produção`) });

// ── O rascunho em edição ────────────────────────────────────────────────────
const requestedNumber = computed(() => Number(route.query.v) || null);
const draft = computed<RecipeVersionProjection | null>(() => {
  const requested = versionByNumber(requestedNumber.value);
  if (requested) return requested.status === "draft" ? requested : null;
  return latestDraft.value;
});
const requestedNotDraft = computed(() => {
  const requested = versionByNumber(requestedNumber.value);
  return !!requested && requested.status !== "draft";
});

// Estado local, semeado UMA vez quando o rascunho chega (o refresh depois de salvar
// não pode sobrescrever o que o padeiro está digitando).
const formula = ref<Formula>(emptyFormula());
const yieldQuantity = ref("");
const yieldUnit = ref("kg");
const stepsText = ref("");
const notes = ref("");
const label = ref("");
const seededNumber = ref<number | null>(null);

watch(
  draft,
  (version) => {
    if (!version || seededNumber.value === version.number) return;
    formula.value = formulaFromServed(version.formula);
    yieldQuantity.value = version.yield_quantity;
    yieldUnit.value = version.yield_unit || "kg";
    stepsText.value = stepsToText(version.steps);
    notes.value = version.notes;
    label.value = version.label;
    seededNumber.value = version.number;
    before.value = null;
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
function onItemUnit(index: number, event: Event) {
  formula.value = updateItem(formula.value, index, { unit: (event.target as HTMLSelectElement).value as FormulaUnit });
}
function onItemRole(index: number, event: Event) {
  formula.value = updateItem(formula.value, index, { role: (event.target as HTMLSelectElement).value as IngredientRole });
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
function onAnchorKind(event: Event) {
  const next = (event.target as HTMLSelectElement).value as AnchorKind;
  const firstSku = formula.value.items.find((item) => item.sku)?.sku ?? "";
  formula.value = setAnchor(formula.value, next, next === "ingredient" ? firstSku : "");
}
function onAnchorSku(event: Event) {
  formula.value = setAnchor(formula.value, "ingredient", (event.target as HTMLSelectElement).value);
}
const anchorCandidates = computed(() => formula.value.items.filter((item) => item.sku));

// ── Partes ──────────────────────────────────────────────────────────────────
function addNewPart() {
  formula.value = addPart(formula.value, emptyPart("preferment"));
}
function onPartKind(index: number, event: Event) {
  const next = (event.target as HTMLSelectElement).value as PartKind;
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
function onPartUnit(index: number, event: Event) {
  formula.value = updatePart(formula.value, index, { unit: (event.target as HTMLSelectElement).value as FormulaUnit });
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
const before = ref<{ formula: Formula; anchorTotal: number; total: number } | null>(null);
async function standardizeToHouse() {
  const snapshot = { formula: formula.value, anchorTotal: localAnchorTotal.value, total: localTotal.value };
  const next = await standardize(HOUSE_BASIS_G);
  if (!next) return;
  before.value = snapshot;
  formula.value = next;
}
function undoStandardize() {
  if (!before.value) return;
  formula.value = before.value.formula;
  before.value = null;
}
const origin = computed(() => (draft.value ? originLines(draft.value.origin) : []));
const originOpen = ref(false);

// ── Salvar / publicar ───────────────────────────────────────────────────────
const saveError = ref("");
function draftPatch() {
  return {
    formula: formula.value,
    yield_quantity: yieldQuantity.value.trim(),
    yield_unit: yieldUnit.value,
    steps: stepsFromText(stepsText.value),
    notes: notes.value,
    label: label.value.trim(),
  };
}
async function save(): Promise<boolean> {
  if (!draft.value) return false;
  saveError.value = "";
  const result = await updateDraft(draft.value.number, draftPatch());
  if (result.ok) {
    useSonner.success("Rascunho salvo.");
    return true;
  }
  saveError.value = result.message ?? "";
  return false;
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

// Sem rascunho: oferece criar um (cópia da atual) sem sair da tela.
async function startDraft() {
  const base = entry.value?.versions[0];
  const result = await createVersion(
    base
      ? {
          from_version: base.number,
          formula: formulaFromServed(base.formula),
          yield_quantity: base.yield_quantity,
          yield_unit: base.yield_unit,
          steps: [...base.steps],
          notes: base.notes,
          label: "",
        }
      : { formula: emptyFormula(), yield_quantity: "1", yield_unit: "kg", steps: [], notes: "", label: "" },
  );
  if (result.ok && result.version) await navigateTo(`/recipes/${entryRef}/edit?v=${result.version.number}`, { replace: true });
}

const inputClass = "h-9 w-full rounded-md border bg-background px-2 text-sm text-foreground outline-none transition focus:ring-1 focus:ring-ring";
const selectClass = "h-9 rounded-md border bg-background px-2 text-sm text-foreground";
</script>

<template>
  <main class="flex min-h-screen flex-col">
    <RecipeHeader
      :title="entry ? `Editar · ${entry.name}` : 'Editar receita'"
      :subtitle="draft ? `Rascunho · Versão ${draft.number}` : ''"
      :back="`/recipes/${entryRef}`"
      hide-refresh
    >
      <template #actions>
        <template v-if="draft && canEdit">
          <button
            type="button"
            class="inline-flex h-9 items-center gap-1.5 rounded-md border px-3 text-sm font-medium transition hover:bg-accent disabled:opacity-50"
            :disabled="busy"
            @click="save"
          >
            <Icon name="lucide:save" class="size-4" />
            <span class="hidden sm:inline">Salvar rascunho</span>
          </button>
          <button
            type="button"
            class="inline-flex h-9 items-center gap-1.5 rounded-md border border-transparent bg-primary px-3 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            :disabled="busy || unmatchedCount > 0 || !entry?.output_sku"
            :title="!entry?.output_sku ? 'Associe um SKU na receita antes de publicar' : unmatchedCount ? 'Case todos os ingredientes antes de publicar' : ''"
            @click="saveAndPublish"
          >
            <Icon name="lucide:check" class="size-4" />
            <span class="hidden sm:inline">Salvar e publicar</span>
          </button>
        </template>
      </template>
    </RecipeHeader>

    <section v-if="forbidden || (!pending && entry && !canEdit)" class="grid flex-1 place-items-center p-6 text-center">
      <div class="grid max-w-md gap-2 rounded-lg border border-dashed p-10">
        <Icon name="lucide:lock" class="mx-auto size-8 text-muted-foreground" />
        <p class="text-base font-semibold">Só leitura</p>
        <p class="text-sm text-muted-foreground">Editar receitas pede a permissão de gestão da produção.</p>
        <NuxtLink :to="`/recipes/${entryRef}`" class="mt-1 text-sm text-primary underline-offset-2 hover:underline">Ver a receita</NuxtLink>
      </div>
    </section>

    <section v-else-if="notFound" class="grid flex-1 place-items-center p-6 text-center">
      <div class="grid max-w-md gap-2 rounded-lg border border-dashed p-10">
        <Icon name="lucide:book-x" class="mx-auto size-8 text-muted-foreground" />
        <p class="text-base font-semibold">Receita não encontrada</p>
        <NuxtLink to="/recipes" class="mt-1 text-sm text-primary underline-offset-2 hover:underline">Voltar ao inventário</NuxtLink>
      </div>
    </section>

    <section v-else class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <p v-if="pending && !entry" class="text-sm text-muted-foreground">Carregando…</p>

      <div
        v-else-if="error && !entry"
        class="grid place-items-center gap-2 rounded-lg border border-dashed border-destructive/30 py-16 text-center text-muted-foreground"
      >
        <Icon name="lucide:cloud-off" class="size-8 text-destructive/70" />
        <p class="text-base font-medium text-foreground">Não foi possível carregar a receita.</p>
        <button
          type="button"
          class="mt-1 inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition hover:bg-accent"
          @click="refresh()"
        >
          <Icon name="lucide:refresh-cw" class="size-4" /> Tentar de novo
        </button>
      </div>

      <div
        v-else-if="entry && !draft"
        class="grid place-items-center gap-2 rounded-lg border border-dashed py-16 text-center text-muted-foreground"
      >
        <Icon name="lucide:pencil-line" class="size-8" />
        <p class="text-base font-medium text-foreground">
          {{ requestedNotDraft ? "Essa versão já foi publicada e não se edita." : "Sem rascunho para editar." }}
        </p>
        <p class="text-sm">Uma nova versão copia a mais recente em rascunho; a publicada continua intacta.</p>
        <button
          v-if="!entry.is_archived"
          type="button"
          class="mt-1 inline-flex items-center gap-1.5 rounded-md border border-transparent bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
          :disabled="busy"
          @click="startDraft"
        >
          <Icon name="lucide:copy-plus" class="size-4" /> Nova versão
        </button>
      </div>

      <div v-else-if="entry && draft" class="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(20rem,2fr)]">
        <!-- ── Editor ──────────────────────────────────────────────────── -->
        <div class="grid min-w-0 content-start gap-4">
          <p v-if="saveError" class="rounded-md border border-destructive/30 px-3 py-2 text-sm text-destructive">{{ saveError }}</p>

          <!-- Rendimento, âncora, o que mudou -->
          <div class="grid gap-3 rounded-lg border bg-card p-3 sm:grid-cols-[auto_auto_1fr]">
            <label class="grid gap-1 text-xs font-medium text-muted-foreground">
              Rendimento
              <span class="flex items-center gap-1">
                <input v-model="yieldQuantity" type="text" inputmode="decimal" class="h-9 w-20 rounded-md border bg-background px-2 text-sm text-foreground" />
                <select v-model="yieldUnit" :class="selectClass">
                  <option v-for="unit in YIELD_UNIT_OPTIONS" :key="unit" :value="unit">{{ unit }}</option>
                </select>
              </span>
            </label>
            <label class="grid gap-1 text-xs font-medium text-muted-foreground">
              Âncora (100%)
              <span class="flex items-center gap-1">
                <select :value="formula.anchor.kind" :class="selectClass" @change="onAnchorKind">
                  <option v-for="option in ANCHOR_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
                </select>
                <select
                  v-if="formula.anchor.kind === 'ingredient'"
                  :value="formula.anchor.sku ?? ''"
                  :class="selectClass"
                  aria-label="Ingrediente-âncora"
                  @change="onAnchorSku"
                >
                  <option value="">Escolha…</option>
                  <option v-for="item in anchorCandidates" :key="item.sku" :value="item.sku">{{ item.name || item.sku }}</option>
                </select>
              </span>
            </label>
            <label class="grid gap-1 text-xs font-medium text-muted-foreground">
              O que mudou (rótulo curto)
              <input v-model="label" type="text" placeholder="Ex.: hidratação 72 → 75" :class="inputClass" />
            </label>
          </div>

          <!-- Ingredientes -->
          <div class="rounded-lg border">
            <div class="flex flex-wrap items-center gap-2 border-b bg-muted/40 px-3 py-2">
              <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Ingredientes (receita base)</p>
              <span class="text-xs tabular-nums text-muted-foreground">
                âncora {{ gramsLabel(localAnchorTotal) }} · massa {{ gramsLabel(localTotal) }}
              </span>
              <button
                type="button"
                class="ml-auto inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition hover:bg-accent"
                @click="add"
              >
                <Icon name="lucide:plus" class="size-4" /> Ingrediente
              </button>
            </div>
            <p v-if="!formula.items.length" class="px-3 py-6 text-center text-sm text-muted-foreground">
              Nenhum ingrediente ainda. Toda a farinha entra aqui, inclusive a do levain e da autólise.
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
                  <input :value="item.name" type="text" placeholder="Ex.: Farinha T65" :class="inputClass" @input="onItemName(index, $event)" />
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
                  <input
                    :value="item.quantity || ''"
                    type="text"
                    inputmode="decimal"
                    class="h-9 w-24 rounded-md border bg-background px-2 text-right text-sm tabular-nums text-foreground"
                    @input="onItemQuantity(index, $event)"
                  />
                </label>
                <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                  Un
                  <select :value="item.unit" :class="selectClass" @change="onItemUnit(index, $event)">
                    <option v-for="unit in UNIT_OPTIONS" :key="unit" :value="unit">{{ unit }}</option>
                  </select>
                </label>
                <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                  Papel
                  <select :value="item.role" :class="selectClass" @change="onItemRole(index, $event)">
                    <option v-for="role in ROLE_OPTIONS" :key="role.value" :value="role.value">{{ role.label }}</option>
                  </select>
                </label>
                <div class="flex items-end gap-1">
                  <span class="mb-2 w-12 text-right text-sm tabular-nums text-muted-foreground" :title="'Percentual sobre a âncora (prévia local)'">
                    {{ pctOf(item, localAnchorTotal) ? `${pctOf(item, localAnchorTotal)}%` : "" }}
                  </span>
                  <button type="button" class="grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent disabled:opacity-40" aria-label="Subir" :disabled="index === 0" @click="move(index, -1)">
                    <Icon name="lucide:chevron-up" class="size-4" />
                  </button>
                  <button type="button" class="grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent disabled:opacity-40" aria-label="Descer" :disabled="index === formula.items.length - 1" @click="move(index, 1)">
                    <Icon name="lucide:chevron-down" class="size-4" />
                  </button>
                  <button type="button" class="grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-destructive/10 hover:text-destructive" aria-label="Remover ingrediente" @click="remove(index)">
                    <Icon name="lucide:trash-2" class="size-4" />
                  </button>
                </div>
                <label v-if="item.unit === 'un'" class="grid gap-1 text-xs font-medium text-muted-foreground sm:col-span-6">
                  Gramas por unidade (sem isso a contagem fica fora da conta)
                  <input
                    :value="item.grams_per_unit ?? ''"
                    type="text"
                    inputmode="decimal"
                    class="h-9 w-28 rounded-md border bg-background px-2 text-sm text-foreground"
                    @input="onItemGramsPerUnit(index, $event)"
                  />
                </label>
              </li>
            </ol>
          </div>

          <!-- Partes -->
          <div class="rounded-lg border">
            <div class="flex flex-wrap items-center gap-2 border-b bg-muted/40 px-3 py-2">
              <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Partes</p>
              <span class="text-xs text-muted-foreground">quanto da base passa por levain, autólise, embebido ou massa velha</span>
              <button
                type="button"
                class="ml-auto inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition hover:bg-accent"
                @click="addNewPart"
              >
                <Icon name="lucide:plus" class="size-4" /> Parte
              </button>
            </div>
            <p v-if="!formula.parts.length" class="px-3 py-4 text-center text-sm text-muted-foreground">Sem partes: tudo vai direto na mistura.</p>
            <ol v-else class="divide-y">
              <li v-for="(part, index) in formula.parts" :key="index" class="grid gap-2 p-3 sm:grid-cols-[auto_minmax(0,1.4fr)_auto_auto_auto]">
                <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                  Tipo
                  <select :value="part.kind" :class="selectClass" @change="onPartKind(index, $event)">
                    <option v-for="option in PART_KIND_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
                  </select>
                </label>
                <template v-if="part.kind === 'old_dough'">
                  <p class="self-end pb-2 text-sm text-muted-foreground sm:col-span-2">A própria base da véspera; declara só o teto.</p>
                  <label class="grid gap-1 text-xs font-medium text-muted-foreground">
                    Teto (%)
                    <input :value="part.cap_pct ?? ''" type="text" inputmode="decimal" class="h-9 w-20 rounded-md border bg-background px-2 text-right text-sm text-foreground" @input="onPartNumber(index, 'cap_pct', $event)" />
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
                    <input :value="part.flour_pct ?? ''" type="text" inputmode="decimal" class="h-9 w-20 rounded-md border bg-background px-2 text-right text-sm text-foreground" @input="onPartNumber(index, 'flour_pct', $event)" />
                  </label>
                  <label v-else class="grid gap-1 text-xs font-medium text-muted-foreground">
                    Quantidade
                    <span class="flex items-center gap-1">
                      <input :value="part.quantity ?? ''" type="text" inputmode="decimal" class="h-9 w-20 rounded-md border bg-background px-2 text-right text-sm text-foreground" @input="onPartNumber(index, 'quantity', $event)" />
                      <select :value="part.unit ?? 'g'" :class="selectClass" @change="onPartUnit(index, $event)">
                        <option v-for="unit in UNIT_OPTIONS" :key="unit" :value="unit">{{ unit }}</option>
                      </select>
                    </span>
                  </label>
                  <span v-if="anchorIsFlour" class="hidden sm:block" />
                </template>
                <div class="flex items-end">
                  <button type="button" class="grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-destructive/10 hover:text-destructive" aria-label="Remover parte" @click="dropPart(index)">
                    <Icon name="lucide:trash-2" class="size-4" />
                  </button>
                </div>
              </li>
            </ol>
          </div>

          <!-- Passos e notas -->
          <div class="grid gap-3 rounded-lg border bg-card p-3">
            <label class="grid gap-1 text-xs font-medium text-muted-foreground">
              Passos (um por linha)
              <UiTextarea v-model="stepsText" :rows="6" placeholder="Autólise 40 min&#10;Sova até o ponto de véu&#10;…" />
            </label>
            <label class="grid gap-1 text-xs font-medium text-muted-foreground">
              Notas desta versão
              <UiTextarea v-model="notes" :rows="3" />
            </label>
          </div>
        </div>

        <!-- ── Prévia da lente ─────────────────────────────────────────── -->
        <aside class="grid min-w-0 content-start gap-3 xl:sticky xl:top-0 xl:self-start">
          <div class="flex flex-wrap items-center gap-2">
            <p class="text-xs font-medium uppercase tracking-wider text-muted-foreground">Prévia da lente</p>
            <Icon v-if="lensPending" name="lucide:loader-circle" class="size-4 animate-spin text-muted-foreground" />
            <button
              type="button"
              class="ml-auto inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition hover:bg-accent disabled:opacity-50"
              :disabled="standardizing || !formula.items.length"
              @click="standardizeToHouse"
            >
              <Icon name="lucide:scale" class="size-4" />
              {{ standardizing ? "Padronizando…" : `Padronizar para ${HOUSE_BASIS_G} g ${anchorNoun}` }}
            </button>
          </div>

          <div v-if="before" class="grid gap-1 rounded-md border bg-muted/40 px-3 py-2 text-sm">
            <p class="font-medium">Padronizada para {{ gramsLabel(HOUSE_BASIS_G) }} {{ anchorNoun }}</p>
            <p class="tabular-nums text-muted-foreground">
              Antes: âncora {{ gramsLabel(before.anchorTotal) }} · massa {{ gramsLabel(before.total) }}
              <br />
              Depois: âncora {{ gramsLabel(localAnchorTotal) }} · massa {{ gramsLabel(localTotal) }}
            </p>
            <button type="button" class="justify-self-start text-sm text-primary underline-offset-2 hover:underline" @click="undoStandardize">Desfazer</button>
          </div>

          <FormulaLens :lens="lens" :pending="lensPending" :error="lensError" compact />

          <div v-if="origin.length" class="rounded-lg border">
            <button
              type="button"
              class="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground"
              :aria-expanded="originOpen"
              @click="originOpen = !originOpen"
            >
              <Icon :name="originOpen ? 'lucide:chevron-down' : 'lucide:chevron-right'" class="size-4" />
              Como foi informada
            </button>
            <ul v-if="originOpen" class="divide-y border-t text-sm">
              <li v-for="(line, index) in origin" :key="index" class="px-3 py-1.5 text-muted-foreground">{{ line }}</li>
            </ul>
          </div>
        </aside>
      </div>
    </section>
  </main>
</template>
