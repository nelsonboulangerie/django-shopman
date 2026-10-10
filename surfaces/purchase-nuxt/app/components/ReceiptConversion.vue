<script setup lang="ts">
import type { ConversionKind, MaterialConversion, ReceiptLinePreview } from "~/types/purchase";
import { formatQty } from "~/presentation/purchase";

const props = defineProps<{
  preview: ReceiptLinePreview;
  conversions: MaterialConversion[];
  pending?: boolean;
}>();

const emit = defineEmits<{
  select: [conversionId: string | null];
  accept: [];
  acceptAxes: [];
  declare: [input: { label: string; factor: string; kind: ConversionKind }];
}>();

const declaring = ref(false);
const choosing = ref(false);
const label = ref("");
const factor = ref("");
const kind = ref<ConversionKind>("conventional");

const suggestion = computed(() => props.preview.conversionSuggestion);
const blocked = computed(() => Boolean(props.preview.line.requiresConversion) && !props.preview.conversion);
const diverging = computed(() => props.preview.conversionDiverges);

/**
 * A conta que a proposta faz, pronta: "4 × saco 25 kg = 100 kg".
 *
 * O operador não precisa multiplicar nada — ele confere um resultado. Era isto
 * que faltava: a tela mostrava o fator ("1 SC = 25 kg") e deixava a conta com
 * quem está com a nota na mão e o entregador esperando.
 */
const proposal = computed(() => {
  const value = suggestion.value;
  if (!value) return null;
  const perUnit = Number(value.factor);
  if (!Number.isFinite(perUnit) || perUnit <= 0) return null;
  const quantity = props.preview.line.purchaseQty;
  return {
    label: value.label,
    perUnit,
    line: `${quantity} × ${value.label}`,
    total: formatQty(quantity * perUnit, props.preview.material.unit),
    note: value.note,
  };
});

/** De onde saiu, em português — "unidade tributável" é fiscalês, não conversa. */
const provenance = computed(() =>
  suggestion.value?.source === "invoice-tax-pair" ?
    "É a própria nota que diz."
  : "Está escrito no nome do produto, na nota.",
);

// O card só existe enquanto há algo a decidir. Resolvido, o campo volta a ser
// um campo comum — o destaque some junto com o motivo dele.
const deciding = computed(() => (blocked.value || diverging.value) && !declaring.value && !choosing.value);
const showsField = computed(() => !deciding.value || choosing.value);
const canSave = computed(() => label.value.trim().length > 0 && Number(factor.value.replace(",", ".")) > 0);

function openDeclare() {
  label.value = suggestion.value?.label ?? "";
  factor.value = suggestion.value?.factor ?? "";
  kind.value = suggestion.value?.kind ?? "conventional";
  choosing.value = false;
  declaring.value = true;
}

/**
 * "Direto na unidade" é a ausência de embalagem. O `NuxtSelect` não aceita item de
 * valor vazio (o item real lança), então ela ganha um valor próprio que vira
 * `null` na saída: a linha nunca volta com uma conversão que não existe.
 */
const DIRECT = "__direct__";
const conversionItems = computed(() => [
  { value: DIRECT, label: `Direto em ${props.preview.material.unit}` },
  ...props.conversions.map((conversion) => ({ value: conversion.id, label: conversion.label })),
]);
const kindItems = [
  { value: "conventional", label: "Exato: é assim que vem embalado" },
  { value: "approximate", label: "Aproximado: é uma estimativa" },
];

function selectConversion(value: unknown) {
  emit("select", !value || value === DIRECT ? null : String(value));
}

function submitDeclare() {
  if (!canSave.value) return;
  emit("declare", { label: label.value.trim(), factor: factor.value.replace(",", "."), kind: kind.value });
  declaring.value = false;
}
</script>

<template>
  <ReceiptField
    :attention="deciding"
    :wrong="diverging"
    :title="diverging ? 'A nota discorda desta conta' : 'Confirme a conta desta entrega'"
    :icon="diverging ? 'lucide:triangle-alert' : 'lucide:calculator'"
  >

    <!-- A CONTA, e não o fator: quem recebe confere um resultado. -->
    <div v-if="deciding && proposal" class="rounded-md bg-card px-3 py-2">
      <p class="text-sm text-muted-foreground">{{ proposal.line }}</p>
      <p class="mt-0.5 text-base font-semibold tabular-nums">= {{ proposal.total }}</p>
    </div>

    <!-- Sem fator ainda (o insumo só foi escolhido agora): a nota já dá o total,
         e é isso que se mostra. O fator se calcula ao aceitar. -->
    <div v-else-if="deciding && preview.invoiceAxes" class="rounded-md bg-card px-3 py-2">
      <p class="text-sm text-muted-foreground">A nota diz</p>
      <p class="mt-0.5 text-base font-semibold tabular-nums">{{ preview.invoiceAxes }}</p>
    </div>

    <p v-if="deciding && (proposal || preview.invoiceAxes)" class="mt-2 text-xs text-muted-foreground">
      {{ proposal ? provenance : "Falta dizer quanto pesa cada uma para o estoque contar certo." }}
    </p>

    <div v-if="deciding && (proposal || preview.invoiceAxes)" class="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
      <NuxtButton
        icon="i-lucide-check"
        label="Confere"
        class="justify-center"
        :disabled="pending"
        :loading="pending"
        @click="proposal ? emit('accept') : emit('acceptAxes')"
      />
      <NuxtButton variant="outline" color="neutral" label="Não é assim" class="justify-center" @click="choosing = true" />
    </div>

    <!-- Nem proposta nem eixos: a nota não respondeu, e a tela diz o que fazer. -->
    <div v-else-if="deciding">
      <p class="text-sm text-muted-foreground">
        A nota não diz quanto vale cada {{ preview.line.invoiceUnit || "embalagem" }} em {{ preview.material.unit }}.
      </p>
      <div class="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
        <NuxtButton icon="i-lucide-plus" label="Cadastrar embalagem" class="justify-center" @click="openDeclare" />
        <NuxtButton
          v-if="conversions.length"
          variant="outline"
          color="neutral"
          label="Escolher uma já cadastrada"
          class="justify-center"
          @click="choosing = true"
        />
      </div>
    </div>

    <!-- O campo: normal quando não há nada a decidir, ou revelado por "Não é assim". -->
    <div v-if="showsField && !declaring" :class="choosing ? 'mt-3' : ''">
      <NuxtFormField label="Como isto é contado">
        <NuxtSelect
          class="w-full"
          :model-value="preview.line.conversionId ?? DIRECT"
          :items="conversionItems"
          data-receipt-conversion-select
          @update:model-value="selectConversion"
        />
      </NuxtFormField>
      <div class="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center">
        <NuxtButton variant="outline" color="neutral" icon="i-lucide-plus" label="Cadastrar embalagem" @click="openDeclare" />
        <NuxtButton v-if="choosing" variant="ghost" color="neutral" label="Voltar" @click="choosing = false" />
      </div>
    </div>

    <NuxtCard v-if="declaring" variant="soft" class="mt-2" data-receipt-conversion-declare>
      <div class="space-y-2">
        <p class="text-xs font-semibold text-foreground">Cadastrar embalagem</p>
        <NuxtFormField label="Como você chama isto">
          <NuxtInput
            v-model="label"
            class="w-full"
            :placeholder="preview.line.invoiceUnit ? `${preview.line.invoiceUnit.toLowerCase()} 5 kg` : 'saco 25 kg'"
          />
        </NuxtFormField>
        <NuxtFormField :label="`Quanto vale UMA, em ${preview.material.unit}`">
          <NuxtInput v-model="factor" inputmode="decimal" class="w-full tabular-nums" placeholder="25" />
        </NuxtFormField>
        <NuxtFormField label="Esse número é">
          <NuxtSelect v-model="kind" class="w-full" :items="kindItems" />
        </NuxtFormField>
        <div class="flex flex-col gap-2 pt-1 sm:flex-row sm:items-center">
          <NuxtButton
            icon="i-lucide-check"
            label="Salvar"
            class="justify-center"
            :disabled="!canSave || pending"
            :loading="pending"
            @click="submitDeclare"
          />
          <NuxtButton variant="outline" color="neutral" label="Cancelar" class="justify-center" @click="declaring = false" />
        </div>
      </div>
    </NuxtCard>
  </ReceiptField>
</template>
