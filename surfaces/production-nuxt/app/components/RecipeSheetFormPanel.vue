<script setup lang="ts">
// A ficha de execução no CASCO canônico do kit (#1792): a gaveta lateral com
// seções, o aviso do que não foi salvo, a barra de ação e a pergunta antes de
// descartar. O painel conduz; quem grava é a página (criar ou editar, conforme
// a ficha carregada). A conta de massa aparece em prévia local ANTES de salvar,
// mas quem recusa é o modelo — a mesma régua do Admin, revalidada nos itens.
import type { RecipeSheetDetailProjection, RecipeSheetItemDraft, RecipeSheetPayload } from "~/types/recipeBook";
import OperatorFormSection from "../../../operator-kit/app/components/OperatorFormSection.vue";
import OperatorFormShell from "../../../operator-kit/app/components/OperatorFormShell.vue";
import { useDirtyForm } from "../../../operator-kit/app/composables/useDirtyForm";
import {
  SHEET_UNIT_OPTIONS,
  SHEET_YIELD_UNIT_OPTIONS,
  addSheetItem,
  emptySheetDraft,
  itemsFromProjection,
  massBalancePreview,
  moveSheetItem,
  removeSheetItem,
  sheetDraftError,
  sheetPayloadFromDraft,
  type SheetDraft,
} from "~/presentation/recipeSheet";
import { PRODUCTION_MODE_HELP, PRODUCTION_MODE_OPTIONS } from "~/presentation/recipeBook";

const props = defineProps<{
  open: boolean;
  sheet: RecipeSheetDetailProjection | null;
  busy?: boolean;
}>();
const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [payload: RecipeSheetPayload];
}>();

const form = reactive<SheetDraft>(emptySheetDraft());
const { dirty, changedKeys, capture } = useDirtyForm(() => ({
  name: form.name,
  ref: form.ref,
  outputSku: form.outputSku,
  batchSize: form.batchSize,
  isActive: form.isActive,
  stepsText: form.stepsText,
  maxStartedMinutes: form.maxStartedMinutes,
  capacityPerDay: form.capacityPerDay,
  requiresBatchTracking: form.requiresBatchTracking,
  shelfLifeDays: form.shelfLifeDays,
  shelfLifeReviewed: form.shelfLifeReviewed,
  productionLifecycle: form.productionLifecycle,
  productionMode: form.productionMode,
  items: form.items.map((item) => ({ ...item })),
}));

function seed() {
  const draft = emptySheetDraft();
  const sheet = props.sheet;
  if (sheet) {
    draft.name = sheet.name;
    draft.ref = sheet.ref;
    draft.outputSku = sheet.output_sku;
    draft.batchSize = sheet.batch_size;
    draft.isActive = sheet.is_active;
    draft.stepsText = sheet.steps.map((step) => step.name).join("\n");
    draft.maxStartedMinutes = sheet.execution.max_started_minutes == null ? "" : String(sheet.execution.max_started_minutes);
    draft.capacityPerDay = sheet.execution.capacity_per_day;
    draft.requiresBatchTracking = sheet.execution.requires_batch_tracking;
    draft.shelfLifeDays = sheet.execution.shelf_life_days == null ? "" : String(sheet.execution.shelf_life_days);
    draft.shelfLifeReviewed = sheet.execution.shelf_life_reviewed;
    draft.productionLifecycle = sheet.execution.production_lifecycle;
    draft.productionMode = sheet.execution.production_mode;
    draft.items = itemsFromProjection(sheet.items);
  }
  if (!draft.items.length) draft.items = [emptySheetItem()];
  Object.assign(form, draft);
}

function emptySheetItem(): RecipeSheetItemDraft {
  return { inputSku: "", quantity: "", unit: "kg", usableFactor: "1", isOptional: false, note: "" };
}

watch(
  () => [props.open, props.sheet?.revision],
  () => {
    if (!props.open) return;
    seed();
    nextTick(capture);
  },
  { immediate: true },
);

const isCreate = computed(() => !props.sheet);
const outputUnit = computed(() => props.sheet?.output_unit ?? "");
const units = [...SHEET_UNIT_OPTIONS];
const yieldUnits = [...SHEET_YIELD_UNIT_OPTIONS];
const lifecycleOptions = computed(() => props.sheet?.execution.lifecycle_options ?? []);
const productionModeOptions = computed(() => props.sheet?.execution.production_mode_options ?? [...PRODUCTION_MODE_OPTIONS]);
const error = computed(() => sheetDraftError(form));
const valid = computed(() => !error.value);
const mass = computed(() => massBalancePreview(form.items, form.batchSize, outputUnit.value));
const massColor = computed(() => (mass.value.tone === "warning" ? "warning" : mass.value.tone === "ok" ? "success" : "neutral"));

function add() {
  form.items = addSheetItem(form.items);
}
function remove(index: number) {
  form.items = removeSheetItem(form.items, index);
}
function move(index: number, delta: number) {
  form.items = moveSheetItem(form.items, index, index + delta);
}
function matchedName(item: RecipeSheetItemDraft): string {
  return item.inputSku || "";
}
function save() {
  if (!valid.value) return;
  emit("save", sheetPayloadFromDraft(form, props.sheet?.steps ?? [], props.sheet?.revision));
}
</script>

<template>
  <OperatorFormShell
    :open="open"
    :title="isCreate ? 'Nova ficha de execução' : 'Editar ficha de execução'"
    :description="isCreate ? 'O BOM que a produção executa: rendimento, ingredientes e operação.' : `Ficha ${form.ref}.`"
    :dirty="dirty"
    :dirty-count="changedKeys.length"
    :busy="busy"
    :save-label="isCreate ? 'Criar ficha' : 'Salvar ficha'"
    save-icon="i-lucide-save"
    :save-disabled="!valid"
    :save-disabled-reason="error"
    @update:open="emit('update:open', $event)"
    @save="save"
  >
    <OperatorFormSection section-key="identity" title="Identificação" description="O que a ficha produz e quanto rende.">
      <div class="grid gap-3 sm:grid-cols-2">
        <NuxtFormField label="Nome" required class="sm:col-span-2">
          <NuxtInput v-model="form.name" class="w-full" data-focus-control />
        </NuxtFormField>
        <NuxtFormField label="Referência" :description="isCreate ? 'Sem acento; deixe vazia para gerar do nome.' : 'A referência nasce na criação.'">
          <NuxtInput v-model="form.ref" class="w-full" :disabled="!isCreate" :ui="{ base: 'font-mono' }" />
        </NuxtFormField>
        <NuxtFormField label="SKU de saída" required description="O produto ou preparo que esta ficha executa.">
          <NuxtInput v-model="form.outputSku" class="w-full" :ui="{ base: 'font-mono uppercase' }" />
        </NuxtFormField>
        <NuxtFormField label="Rendimento base" required :description="outputUnit ? `Na unidade do SKU (${outputUnit}).` : 'A unidade vem do cadastro do SKU.'">
          <span class="flex items-center gap-1">
            <NuxtInput v-model="form.batchSize" inputmode="decimal" class="w-28" />
            <NuxtSelect v-if="!outputUnit" :model-value="form.items[0]?.unit ?? 'kg'" :items="yieldUnits" class="w-24" disabled aria-label="Unidade do rendimento" />
            <span v-else class="text-sm text-muted-foreground">{{ outputUnit }}</span>
          </span>
        </NuxtFormField>
        <NuxtCheckbox v-model="form.isActive" label="Ficha ativa" description="Só uma ficha ativa por SKU de saída." class="sm:col-span-2" />
      </div>
    </OperatorFormSection>

    <OperatorFormSection section-key="items" title="Ingredientes" description="O que sai do estoque por rendimento base.">
      <div class="flex items-center justify-between gap-2">
        <span class="text-xs tabular-nums text-muted-foreground">
          {{ form.items.length === 1 ? '1 ingrediente' : form.items.length + ' ingredientes' }}
        </span>
        <NuxtButton color="neutral" variant="outline" icon="i-lucide-plus" label="Ingrediente" @click="add" />
      </div>

      <NuxtAlert
        :color="massColor"
        variant="subtle"
        icon="i-lucide-scale"
        :title="mass.message"
        :description="mass.totalDisplay ? `Insumos: ${mass.totalDisplay} · rendimento: ${mass.batchDisplay || 'não informado'}` : ''"
      />

      <p v-if="!form.items.length" class="rounded-md border border-dashed px-3 py-6 text-center text-sm text-muted-foreground">
        Nenhum ingrediente ainda. Toda a ficha começa pelo que entra.
      </p>
      <ol v-else class="grid gap-3">
        <li v-for="(item, index) in form.items" :key="index" class="grid gap-2 rounded-md border p-3">
          <div class="grid gap-2 sm:grid-cols-[minmax(0,2fr)_auto_auto_auto_auto]">
            <div class="grid gap-1 text-xs font-medium text-muted-foreground">
              Insumo
              <IngredientPicker
                :model-value="item.inputSku"
                :matched-name="matchedName(item)"
                @update:model-value="(sku: string) => (item.inputSku = sku)"
              />
            </div>
            <label class="grid gap-1 text-xs font-medium text-muted-foreground">
              Qtd
              <NuxtInput v-model="item.quantity" inputmode="decimal" class="w-24" :ui="{ base: 'text-right tabular-nums' }" />
            </label>
            <label class="grid gap-1 text-xs font-medium text-muted-foreground">
              Un
              <NuxtSelect v-model="item.unit" :items="units" class="w-24" :aria-label="`Unidade de ${item.inputSku || 'ingrediente'}`" />
            </label>
            <label class="grid gap-1 text-xs font-medium text-muted-foreground">
              Aproveitamento
              <NuxtInput v-model="item.usableFactor" inputmode="decimal" class="w-24" :ui="{ base: 'text-right tabular-nums' }" />
            </label>
            <div class="flex items-end gap-1">
              <NuxtButton icon="i-lucide-chevron-up" color="neutral" variant="ghost" square aria-label="Subir" :disabled="index === 0" @click="move(index, -1)" />
              <NuxtButton icon="i-lucide-chevron-down" color="neutral" variant="ghost" square aria-label="Descer" :disabled="index === form.items.length - 1" @click="move(index, 1)" />
              <NuxtButton icon="i-lucide-trash-2" color="error" variant="ghost" square aria-label="Remover ingrediente" @click="remove(index)" />
            </div>
          </div>
          <div class="grid gap-2 sm:grid-cols-[auto_minmax(0,1fr)]">
            <NuxtCheckbox v-model="item.isOptional" label="Opcional" />
            <NuxtFormField label="Nota do ingrediente" description="Aparece na ficha; não muda a quantidade.">
              <NuxtInput v-model="item.note" class="w-full" />
            </NuxtFormField>
          </div>
        </li>
      </ol>
    </OperatorFormSection>

    <OperatorFormSection section-key="operation" title="Operação" description="Como a ficha se comporta no planejamento e no chão.">
      <div class="grid gap-3 sm:grid-cols-2">
        <NuxtFormField label="Modo de produção" :description="PRODUCTION_MODE_HELP" class="sm:col-span-2">
          <NuxtRadioGroup
            v-model="form.productionMode"
            :items="productionModeOptions"
            value-key="value"
            label-key="label"
            orientation="horizontal"
            data-testid="sheet-production-mode"
          />
        </NuxtFormField>
        <NuxtFormField label="Tempo máximo de lote aberto (min)" description="Vazio usa o padrão da loja.">
          <NuxtInput v-model="form.maxStartedMinutes" inputmode="numeric" class="w-full" />
        </NuxtFormField>
        <NuxtFormField label="Capacidade por dia" description="Vazio deixa a ocupação sem teto próprio.">
          <NuxtInput v-model="form.capacityPerDay" inputmode="decimal" class="w-full" />
        </NuxtFormField>
        <NuxtFormField v-if="lifecycleOptions.length" label="Ciclo de produção" class="sm:col-span-2">
          <NuxtSelect v-model="form.productionLifecycle" :items="lifecycleOptions" value-key="value" label-key="label" class="w-full" />
        </NuxtFormField>
        <NuxtCheckbox v-model="form.requiresBatchTracking" label="Rastrear lote ao concluir a produção" class="sm:col-span-2" />
        <NuxtFormField label="Validade (dias)" description="Zero é mesmo dia; vazio não presume prazo.">
          <NuxtInput v-model="form.shelfLifeDays" inputmode="numeric" class="w-32" />
        </NuxtFormField>
        <div class="flex items-end">
          <NuxtCheckbox v-model="form.shelfLifeReviewed" label="Prazo revisado pelo responsável" description="Alterar os dias exige nova confirmação." />
        </div>
      </div>
    </OperatorFormSection>

    <OperatorFormSection section-key="steps" title="Etapas" description="Uma por linha, na ordem operacional.">
      <NuxtTextarea v-model="form.stepsText" :rows="5" class="w-full" placeholder="Autólise 40 min" />
    </OperatorFormSection>
  </OperatorFormShell>
</template>
