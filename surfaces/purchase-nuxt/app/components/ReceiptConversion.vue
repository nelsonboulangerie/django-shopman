<script setup lang="ts">
import type { ConversionKind, MaterialConversion, ReceiptLinePreview } from "~/types/purchase";
import { formatFactor } from "~/presentation/purchase";

const props = defineProps<{
  preview: ReceiptLinePreview;
  conversions: MaterialConversion[];
  pending?: boolean;
}>();

const emit = defineEmits<{
  select: [conversionId: string | null];
  accept: [];
  declare: [input: { label: string; factor: string; kind: ConversionKind }];
}>();

const declaring = ref(false);
const label = ref("");
const factor = ref("");
const kind = ref<ConversionKind>("conventional");

const suggestion = computed(() => props.preview.conversionSuggestion);
const blocked = computed(() => Boolean(props.preview.line.requiresConversion) && !props.preview.conversion);
// Procedência é informação: um fator lido do par tributável da NF vale mais do
// que um lido da gramatura no meio do nome do produto, e quem confirma merece
// saber qual dos dois está assinando.
const sourceLabel = computed(() =>
  suggestion.value?.source === "invoice-tax-pair" ?
    "unidade tributável da NF"
  : "descrição do produto na NF",
);
const canSave = computed(() => label.value.trim().length > 0 && Number(factor.value.replace(",", ".")) > 0);

function openDeclare() {
  label.value = suggestion.value?.label ?? "";
  factor.value = suggestion.value?.factor ?? "";
  kind.value = suggestion.value?.kind ?? "conventional";
  declaring.value = true;
}

function submitDeclare() {
  if (!canSave.value) return;
  emit("declare", {
    label: label.value.trim(),
    factor: factor.value.replace(",", "."),
    kind: kind.value,
  });
  declaring.value = false;
}
</script>

<template>
  <div>
    <!-- `value=""` e nao `:value="null"`: quem le a selecao aqui e o DOM, e o
         DOM so guarda string. Um `null` ligado viraria a string "null" e a
         linha voltaria com uma conversao inexistente. -->
    <select
      :value="preview.line.conversionId ?? ''"
      class="h-10 w-full rounded-md border border-border bg-background px-2 text-sm"
      @change="emit('select', ($event.target as HTMLSelectElement).value || null)"
    >
      <option value="">Unidade-base</option>
      <option v-for="conversion in conversions" :key="conversion.id" :value="conversion.id">{{ conversion.label }}</option>
    </select>
    <p class="mt-1 text-xs text-muted-foreground">
      {{ formatFactor(preview.conversion?.toBaseFactor ?? 1, preview.material.unit, preview.approximate) }}
    </p>

    <!-- A sugestão só aparece enquanto ela tem o que dizer: ou a linha ainda
         espera uma conversão, ou a nota discorda da que foi escolhida. Depois
         de aceita, ela não é mais notícia. -->
    <div
      v-if="suggestion && !declaring && (blocked || preview.conversionDiverges)"
      class="mt-2 rounded-md border p-2"
      :class="blocked ? 'border-warning/30 bg-warning/10' : 'border-destructive/30 bg-destructive/10'"
    >
      <p class="flex items-center gap-1.5 text-xs font-medium" :class="blocked ? 'text-warning' : 'text-destructive'">
        <Icon :name="blocked ? 'lucide:ruler' : 'lucide:triangle-alert'" class="size-3.5" />
        {{ blocked ? `Conversão sugerida: ${suggestion.label}` : "A NF diverge da conversão escolhida" }}
      </p>
      <p class="mt-1 text-xs text-muted-foreground">{{ suggestion.note }}</p>
      <p class="mt-0.5 text-xs text-muted-foreground">Origem: {{ sourceLabel }}.</p>
      <div class="mt-2 flex flex-wrap items-center gap-2">
        <button
          type="button"
          :disabled="pending"
          class="inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-2.5 text-xs font-semibold text-primary-foreground disabled:opacity-50"
          @click="emit('accept')"
        >
          <Icon name="lucide:check" class="size-3.5" />
          {{ blocked ? "Usar conversão" : "Cadastrar a da NF" }}
        </button>
        <button
          type="button"
          class="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-2.5 text-xs font-medium hover:bg-accent"
          @click="openDeclare"
        >
          Outra conversão
        </button>
      </div>
    </div>

    <button
      v-else-if="blocked && !declaring"
      type="button"
      class="mt-2 inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-2.5 text-xs font-medium hover:bg-accent"
      @click="openDeclare"
    >
      <Icon name="lucide:plus" class="size-3.5" />
      Cadastrar conversão
    </button>

    <div v-if="declaring" class="mt-2 space-y-2 rounded-md border border-border bg-background p-2">
      <label class="block text-xs font-medium text-muted-foreground">
        Como se chama a embalagem
        <input
          v-model="label"
          class="mt-1 h-9 w-full rounded-md border border-border bg-card px-2 text-sm"
          :placeholder="preview.line.invoiceUnit ? `${preview.line.invoiceUnit.toLowerCase()} 500 g` : 'saco 25 kg'"
        />
      </label>
      <label class="block text-xs font-medium text-muted-foreground">
        Quanto vale UM, em {{ preview.material.unit }}
        <input
          v-model="factor"
          inputmode="decimal"
          class="mt-1 h-9 w-full rounded-md border border-border bg-card px-2 text-sm tabular-nums"
          placeholder="0,5"
        />
      </label>
      <label class="block text-xs font-medium text-muted-foreground">
        Tipo
        <select v-model="kind" class="mt-1 h-9 w-full rounded-md border border-border bg-card px-2 text-sm">
          <option value="conventional">Convencionada (o fornecedor embala assim)</option>
          <option value="approximate">Aproximada (equivalência estimada)</option>
        </select>
      </label>
      <div class="flex flex-wrap items-center gap-2">
        <button
          type="button"
          :disabled="!canSave || pending"
          class="inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-2.5 text-xs font-semibold text-primary-foreground disabled:opacity-50"
          @click="submitDeclare"
        >
          <Icon name="lucide:check" class="size-3.5" />
          Salvar conversão
        </button>
        <button
          type="button"
          class="inline-flex h-8 items-center rounded-md border border-border px-2.5 text-xs font-medium hover:bg-accent"
          @click="declaring = false"
        >
          Cancelar
        </button>
      </div>
    </div>
  </div>
</template>
