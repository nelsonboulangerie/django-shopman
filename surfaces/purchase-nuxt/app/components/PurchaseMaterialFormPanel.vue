<script setup lang="ts">
// O cadastro do insumo no casco da suíte: criar, editar e duplicar. O casco
// conduz (seções, estado sujo, descarte e próximo foco); aqui mora o formulário
// e o que a tela é dona do payload. Conversões e custos são gestos inline, com
// Aplicar e Cancelar (D9): eles voltam pela projeção, não por estado paralelo.
import { nextTick } from "vue";

import type {
  ConversionKind,
  Material,
  MaterialConversion,
  MaterialUnit,
  PurchaseFormMode,
  Supplier,
  SupplierMaterialCost,
} from "~/types/purchase";
import OperatorFormSection from "../../../operator-kit/app/components/OperatorFormSection.vue";
import OperatorFormShell from "../../../operator-kit/app/components/OperatorFormShell.vue";
import { useDirtyForm } from "../../../operator-kit/app/composables/useDirtyForm";
import { costPerBaseUnitQ, formatMoney, parseMoneyInput, purchaseUnitLabel } from "~/presentation/purchase";

const props = withDefaults(
  defineProps<{
    open: boolean;
    mode: PurchaseFormMode;
    source?: Material | null;
    categories?: string[];
    suppliers?: Supplier[];
    conversions?: MaterialConversion[];
    costs?: SupplierMaterialCost[];
    savedVersion?: number;
    busy?: boolean;
    error?: string;
  }>(),
  {
    source: null,
    categories: () => [],
    suppliers: () => [],
    conversions: () => [],
    costs: () => [],
    savedVersion: 0,
    busy: false,
    error: "",
  },
);

type ConversionSave = {
  conversionId: string | null;
  label: string;
  factor: string;
  kind: ConversionKind;
  supplierRef: string | null;
  isActive: boolean;
};
type CostSave = {
  supplierRef: string;
  conversionId: string | null;
  costInput: string;
  makePreferred: boolean;
};

const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [payload: Record<string, unknown>];
  "save-conversion": [payload: ConversionSave];
  "save-cost": [payload: CostSave];
}>();

const UNIT_OPTIONS = [
  { value: "un", label: "Unidade (un)" },
  { value: "kg", label: "Quilograma (kg)" },
  { value: "g", label: "Grama (g)" },
  { value: "l", label: "Litro (l)" },
  { value: "ml", label: "Mililitro (ml)" },
];
const KIND_OPTIONS = [
  { value: "conventional", label: "Convencionada (exata)" },
  { value: "approximate", label: "Aproximada (carrega o ≈)" },
];

const form = reactive({
  sku: "",
  name: "",
  unit: "un" as MaterialUnit,
  shelfLifeDaysText: "",
  isActive: true,
  category: "",
});
const conversion = reactive({
  open: false,
  id: "",
  label: "",
  factor: "",
  kind: "conventional" as ConversionKind,
  supplierRef: "",
  isActive: true,
});
const cost = reactive({
  open: false,
  supplierRef: "",
  conversionId: "",
  costInput: "",
  makePreferred: false,
});

const isDuplicate = computed(() => props.mode === "duplicate");
const isEdit = computed(() => props.mode === "edit");
const title = computed(() => (isDuplicate.value ? "Duplicar insumo" : isEdit.value ? "Editar insumo" : "Novo insumo"));
const description = computed(() => {
  if (isDuplicate.value) return props.source ? "Cópia de " + props.source.name + " (" + props.source.sku + ")." : "";
  if (isEdit.value) return props.source ? props.source.name + " (" + props.source.sku + ")." : "";
  return "Cria o cadastro de compra do insumo. Fornecedor, custo e conversão entram depois.";
});
const saveLabel = computed(() => (isDuplicate.value ? "Duplicar insumo" : isEdit.value ? "Salvar insumo" : "Criar insumo"));
const duplicateNote =
  "A cópia traz nome, unidade, validade e categoria. Não traz código de barras, mínimo, custo nem conversão: o novo SKU começa limpo.";

function suggestSku(sku: string): string {
  return sku + "-COPIA";
}
function suggestName(name: string): string {
  return name + " (cópia)";
}

function resetConversion() {
  conversion.open = false;
  conversion.id = "";
  conversion.label = "";
  conversion.factor = "";
  conversion.kind = "conventional";
  conversion.supplierRef = "";
  conversion.isActive = true;
}
function resetCost() {
  cost.open = false;
  cost.supplierRef = "";
  cost.conversionId = "";
  cost.costInput = "";
  cost.makePreferred = false;
}

function reset() {
  const source = props.source;
  if (props.mode === "create" || !source) {
    form.sku = "";
    form.name = "";
    form.unit = "un";
    form.shelfLifeDaysText = "";
    form.isActive = true;
    form.category = "";
  } else if (isDuplicate.value) {
    form.sku = suggestSku(source.sku);
    form.name = suggestName(source.name);
    form.unit = source.unit;
    form.shelfLifeDaysText = source.shelfLifeDays != null ? String(source.shelfLifeDays) : "";
    form.isActive = true;
    form.category = source.category;
  } else {
    form.sku = source.sku;
    form.name = source.name;
    form.unit = source.unit;
    form.shelfLifeDaysText = source.shelfLifeDays != null ? String(source.shelfLifeDays) : "";
    form.isActive = source.isActive;
    form.category = source.category;
  }
  resetConversion();
  resetCost();
}

const { dirty, changedKeys, capture } = useDirtyForm(() => ({
  ...form,
  conversion: { ...conversion },
  cost: { ...cost },
}));
const activeSection = ref<string | null>("identity");

watch(
  () => [props.open, props.mode, props.source?.sku],
  () => {
    if (!props.open) return;
    reset();
    activeSection.value = "identity";
    capture();
  },
  { immediate: true },
);

const shelfLifeNumber = computed(() => {
  const text = form.shelfLifeDaysText.trim();
  if (!text) return null;
  const value = Number(text.replace(",", "."));
  return Number.isInteger(value) && value >= 0 && value <= 36500 ? value : null;
});
const shelfLifeInvalid = computed(() => form.shelfLifeDaysText.trim() !== "" && shelfLifeNumber.value === null);
const sameSourceSku = computed(
  () => isDuplicate.value && Boolean(props.source) && form.sku.trim().toLowerCase() === props.source!.sku.trim().toLowerCase(),
);
const valid = computed(() => {
  if (!isEdit.value && !form.sku.trim()) return false;
  if (!form.name.trim()) return false;
  if (sameSourceSku.value) return false;
  if (shelfLifeInvalid.value) return false;
  return true;
});
const saveDisabledReason = computed(() => {
  if (!isEdit.value && !form.sku.trim()) return "Informe o SKU para salvar.";
  if (!form.name.trim()) return "Informe o nome para salvar.";
  if (sameSourceSku.value) return "O SKU da cópia precisa ser diferente do original.";
  if (shelfLifeInvalid.value) return "A validade precisa ser um número inteiro de dias. Deixe vazio se não perece.";
  return "";
});

function submit() {
  if (!valid.value) return;
  const shelfLife = shelfLifeInvalid.value ? null : shelfLifeNumber.value;
  if (isDuplicate.value) {
    emit("save", {
      sku: form.sku.trim(),
      name: form.name.trim(),
      ...(props.source?.revision ? { expectedRevision: props.source.revision } : {}),
    });
    return;
  }
  if (isEdit.value) {
    emit("save", {
      name: form.name.trim(),
      unit: form.unit,
      shelfLifeDays: shelfLife,
      isActive: form.isActive,
      category: form.category.trim(),
      ...(props.source?.revision ? { expectedRevision: props.source.revision } : {}),
    });
    return;
  }
  emit("save", {
    sku: form.sku.trim(),
    name: form.name.trim(),
    unit: form.unit,
    shelfLifeDays: shelfLife,
    isActive: form.isActive,
    category: form.category.trim(),
  });
}

// ── Conversões ───────────────────────────────────────────────────────────────
const materialConversions = computed(() => props.conversions.filter((row) => row.materialSku === props.source?.sku));

function newConversion() {
  resetConversion();
  conversion.open = true;
  activeSection.value = "conversions";
}
function editConversion(row: MaterialConversion) {
  conversion.open = true;
  conversion.id = row.id;
  conversion.label = row.label;
  conversion.factor = String(row.toBaseFactor).replace(".", ",");
  conversion.kind = row.kind;
  conversion.supplierRef = row.supplierRef ?? "";
  conversion.isActive = row.isActive;
  activeSection.value = "conversions";
}
const conversionFactor = computed(() => Number(conversion.factor.replace(",", ".")));
const conversionValid = computed(() => conversion.label.trim() !== "" && conversionFactor.value > 0);
const conversionDisabledReason = computed(() => {
  if (!conversion.label.trim()) return "Dê um nome à embalagem, como saco 25 kg.";
  if (!(conversionFactor.value > 0)) return "O fator precisa ser maior que zero.";
  return "";
});
function submitConversion() {
  if (!conversionValid.value) return;
  emit("save-conversion", {
    conversionId: conversion.id || null,
    label: conversion.label.trim(),
    factor: conversion.factor.trim(),
    kind: conversion.kind,
    supplierRef: conversion.supplierRef || null,
    isActive: conversion.isActive,
  });
}
function toggleConversion(row: MaterialConversion) {
  emit("save-conversion", {
    conversionId: row.id,
    label: row.label,
    factor: String(row.toBaseFactor).replace(".", ","),
    kind: row.kind,
    supplierRef: row.supplierRef,
    isActive: !row.isActive,
  });
}

// ── Custos ───────────────────────────────────────────────────────────────────
const materialCosts = computed(() => props.costs.filter((row) => row.materialSku === props.source?.sku));
const supplierOptions = computed(() => props.suppliers.map((row) => ({ value: row.ref, label: row.displayName })));
const costConversions = computed(() =>
  materialConversions.value
    .filter((row) => row.isActive && (!row.supplierRef || row.supplierRef === cost.supplierRef))
    .map((row) => ({ value: row.id, label: row.label })),
);
const costValid = computed(
  () => cost.supplierRef !== "" && parseMoneyInput(cost.costInput) > 0,
);
const costDisabledReason = computed(() => {
  if (!cost.supplierRef) return "Escolha o fornecedor do custo.";
  if (!(parseMoneyInput(cost.costInput) > 0)) return "Informe o valor pago na unidade de compra.";
  return "";
});
function newCost() {
  resetCost();
  cost.supplierRef = props.suppliers[0]?.ref ?? "";
  cost.open = true;
  activeSection.value = "costs";
}
function editCost(row: SupplierMaterialCost) {
  cost.open = true;
  cost.supplierRef = row.supplierRef;
  cost.conversionId = row.conversionId ?? "";
  cost.costInput = (row.costQ / 100).toFixed(2).replace(".", ",");
  cost.makePreferred = row.isPreferred;
  activeSection.value = "costs";
}
function submitCost() {
  if (!costValid.value) return;
  emit("save-cost", {
    supplierRef: cost.supplierRef,
    conversionId: cost.conversionId || null,
    costInput: cost.costInput.trim(),
    makePreferred: cost.makePreferred,
  });
}
function makePreferred(row: SupplierMaterialCost) {
  emit("save-cost", {
    supplierRef: row.supplierRef,
    conversionId: row.conversionId,
    costInput: (row.costQ / 100).toFixed(2).replace(".", ","),
    makePreferred: true,
  });
}
function costRowLabel(row: SupplierMaterialCost): string {
  const material = props.source;
  if (!material) return "";
  return purchaseUnitLabel(row, material, props.conversions);
}
function costRowBase(row: SupplierMaterialCost): number {
  return costPerBaseUnitQ(row, props.conversions);
}
function supplierName(ref: string): string {
  return props.suppliers.find((row) => row.ref === ref)?.displayName ?? ref;
}

watch(
  () => cost.supplierRef,
  () => {
    if (cost.conversionId && !costConversions.value.some((option) => option.value === cost.conversionId)) {
      cost.conversionId = "";
    }
  },
);

watch(
  () => props.savedVersion,
  async (_next, previous) => {
    if (previous === undefined || !props.open) return;
    resetConversion();
    resetCost();
    await nextTick();
    capture();
  },
);
</script>

<template>
  <OperatorFormShell
    :open="open"
    :title="title"
    :description="description"
    :dirty="dirty"
    :dirty-count="changedKeys.length"
    :busy="busy"
    :save-label="saveLabel"
    :save-disabled="!valid"
    :save-disabled-reason="saveDisabledReason"
    :active-section="activeSection"
    :size="isDuplicate ? 'standard' : 'wide'"
    :save-attrs="{ 'data-testid': 'material-form-save' }"
    :discard-attrs="{ 'data-testid': 'material-form-discard' }"
    action-label="Cadastro do insumo"
    @update:open="(value: boolean) => emit('update:open', value)"
    @save="submit"
  >
    <div class="flex flex-col gap-4" data-material-form>
      <NuxtAlert v-if="error" color="error" variant="subtle" icon="i-lucide-circle-alert" :description="error" />
      <NuxtAlert
        v-if="isDuplicate"
        color="info"
        variant="subtle"
        icon="i-lucide-copy"
        title="O que a cópia traz"
        :description="duplicateNote"
      />

      <OperatorFormSection section-key="identity" title="Identificação" description="Como o insumo se chama e em que unidade se conta.">
        <div class="grid gap-3 sm:grid-cols-2">
          <NuxtFormField label="SKU" required>
            <NuxtInput
              v-model="form.sku"
              :disabled="isEdit"
              placeholder="FARINHA-T65"
              class="w-full"
              data-testid="material-sku"
              data-focus-control
            />
          </NuxtFormField>
          <NuxtFormField label="Nome" required>
            <NuxtInput v-model="form.name" class="w-full" placeholder="Farinha de trigo tipo 65" data-testid="material-name" />
          </NuxtFormField>
          <NuxtFormField v-if="!isDuplicate" label="Unidade-base">
            <NuxtSelect v-model="form.unit" :items="UNIT_OPTIONS" class="w-full" />
          </NuxtFormField>
          <NuxtFormField v-if="!isDuplicate" label="Categoria" description="Agrupa o insumo na lista e nos filtros.">
            <NuxtInput v-model="form.category" class="w-full" placeholder="Farinhas" data-testid="material-category" />
          </NuxtFormField>
        </div>
        <div v-if="!isDuplicate && categories.length" class="flex flex-wrap gap-1.5">
          <NuxtButton
            v-for="category in categories.slice(0, 8)"
            :key="category"
            :label="category"
            color="neutral"
            variant="outline"
            @click="form.category = category"
          />
        </div>
      </OperatorFormSection>

      <OperatorFormSection
        v-if="!isDuplicate"
        section-key="shelf"
        title="Validade e situação"
        description="A validade padrão do que chega. Vazio = não perecível."
      >
        <div class="grid gap-3 sm:grid-cols-2">
          <NuxtFormField label="Validade (dias)">
            <NuxtInput v-model="form.shelfLifeDaysText" class="w-full" inputmode="numeric" placeholder="Vazio = não perecível" data-testid="material-shelf-life" />
          </NuxtFormField>
          <div class="flex items-center">
            <NuxtCheckbox v-model="form.isActive" label="Ativo na Base" description="Inativo sai dos pedidos e da sugestão de compra." />
          </div>
        </div>
      </OperatorFormSection>

      <OperatorFormSection
        v-if="isEdit && source"
        section-key="conversions"
        title="Conversões"
        description="Como a embalagem comprada vira a unidade-base do insumo."
      >
        <ul v-if="materialConversions.length" class="flex flex-col divide-y divide-default">
          <li v-for="row in materialConversions" :key="row.id" class="flex items-start justify-between gap-2 py-2">
            <span class="min-w-0">
              <span class="block text-sm font-medium" :class="row.isActive ? '' : 'text-muted line-through'">{{ row.label }}</span>
              <span class="block text-xs text-muted">
                1 {{ row.label }} = {{ row.toBaseFactor }} {{ source.unit }}
                <template v-if="row.kind === 'approximate'"> (aproximada)</template>
                <template v-if="row.supplierRef"> · {{ supplierName(row.supplierRef) }}</template>
              </span>
            </span>
            <span class="flex shrink-0 gap-1">
              <NuxtButton label="Editar" color="neutral" variant="ghost" @click="editConversion(row)" />
              <NuxtButton
                :label="row.isActive ? 'Desativar' : 'Reativar'"
                color="neutral"
                variant="ghost"
                @click="toggleConversion(row)"
              />
            </span>
          </li>
        </ul>
        <p v-else class="text-xs text-muted">Nenhuma conversão declarada. Sem ela, a compra é contada na unidade-base.</p>

        <form v-if="conversion.open" class="mt-2 flex flex-col gap-3 rounded-lg bg-elevated/60 p-3" data-testid="conversion-form" @submit.prevent="submitConversion()">
          <div class="grid gap-3 sm:grid-cols-2">
            <NuxtFormField label="Rótulo" required description="Como o operador chama: saco 25 kg, cartela.">
              <NuxtInput v-model="conversion.label" class="w-full" data-testid="conversion-label" />
            </NuxtFormField>
            <NuxtFormField label="Fator" required :description="'Quanto vale UM item de compra em ' + source.unit + '.'">
              <NuxtInput v-model="conversion.factor" class="w-full" inputmode="decimal" placeholder="25" data-testid="conversion-factor" />
            </NuxtFormField>
            <NuxtFormField label="Tipo">
              <NuxtSelect v-model="conversion.kind" :items="KIND_OPTIONS" class="w-full" />
            </NuxtFormField>
            <NuxtFormField label="Fornecedor" description="Vazio = vale para qualquer fornecedor.">
              <NuxtSelect v-model="conversion.supplierRef" :items="supplierOptions" class="w-full" placeholder="Qualquer fornecedor" />
            </NuxtFormField>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <NuxtButton
              type="submit"
              :label="conversion.id ? 'Salvar conversão' : 'Adicionar conversão'"
              :disabled="!conversionValid || busy"
              data-testid="conversion-submit"
            />
            <NuxtButton label="Cancelar" color="neutral" variant="outline" @click="resetConversion()" />
            <span v-if="conversionDisabledReason" class="text-xs text-muted">{{ conversionDisabledReason }}</span>
          </div>
        </form>
        <NuxtButton
          v-else
          label="Adicionar conversão"
          icon="i-lucide-plus"
          color="neutral"
          variant="outline"
          class="self-start"
          :disabled="busy"
          data-testid="conversion-add"
          @click="newConversion()"
        />
      </OperatorFormSection>

      <OperatorFormSection
        v-if="isEdit && source"
        section-key="costs"
        title="Custos"
        description="Quanto cada fornecedor cobra pela unidade de compra."
      >
        <ul v-if="materialCosts.length" class="flex flex-col divide-y divide-default">
          <li v-for="row in materialCosts" :key="row.id" class="flex items-start justify-between gap-2 py-2">
            <span class="min-w-0">
              <span class="block text-sm font-medium">{{ supplierName(row.supplierRef) }}</span>
              <span class="block text-xs text-muted tabular-nums">
                {{ formatMoney(row.costQ) }} / {{ costRowLabel(row) }}
                <template v-if="costRowBase(row) !== row.costQ"> · {{ formatMoney(costRowBase(row)) }} / {{ source.unit }}</template>
              </span>
            </span>
            <span class="flex shrink-0 items-center gap-1">
              <NuxtBadge v-if="row.isPreferred" color="success" label="Preferencial" />
              <NuxtButton
                v-else
                label="Tornar preferencial"
                color="neutral"
                variant="ghost"
                :disabled="busy"
                @click="makePreferred(row)"
              />
              <NuxtButton label="Editar" color="neutral" variant="ghost" @click="editCost(row)" />
            </span>
          </li>
        </ul>
        <p v-else class="text-xs text-muted">Nenhum custo lançado. Sem custo preferencial o insumo fica fora do pedido de compra.</p>

        <form v-if="cost.open" class="mt-2 flex flex-col gap-3 rounded-lg bg-elevated/60 p-3" data-testid="cost-form" @submit.prevent="submitCost()">
          <div class="grid gap-3 sm:grid-cols-2">
            <NuxtFormField label="Fornecedor" required>
              <NuxtSelect v-model="cost.supplierRef" :items="supplierOptions" class="w-full" data-testid="cost-supplier" />
            </NuxtFormField>
            <NuxtFormField label="Unidade de compra" description="Vazio = comprado na unidade-base.">
              <NuxtSelect v-model="cost.conversionId" :items="costConversions" class="w-full" placeholder="Unidade-base" />
            </NuxtFormField>
            <NuxtFormField label="Valor pago (R$)" required>
              <NuxtInput v-model="cost.costInput" class="w-full" inputmode="decimal" placeholder="180,00" data-testid="cost-input" />
            </NuxtFormField>
            <div class="flex items-end">
              <NuxtCheckbox v-model="cost.makePreferred" label="Custo preferencial" description="Alimenta o custeio e a sugestão de preço." />
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <NuxtButton type="submit" label="Salvar custo" :disabled="!costValid || busy" data-testid="cost-submit" />
            <NuxtButton label="Cancelar" color="neutral" variant="outline" @click="resetCost()" />
            <span v-if="costDisabledReason" class="text-xs text-muted">{{ costDisabledReason }}</span>
          </div>
        </form>
        <NuxtButton
          v-else
          label="Adicionar custo"
          icon="i-lucide-plus"
          color="neutral"
          variant="outline"
          class="self-start"
          :disabled="busy || !suppliers.length"
          data-testid="cost-add"
          @click="newCost()"
        />
      </OperatorFormSection>
    </div>
  </OperatorFormShell>
</template>
