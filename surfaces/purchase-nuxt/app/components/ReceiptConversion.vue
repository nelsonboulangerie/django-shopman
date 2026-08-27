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

function submitDeclare() {
  if (!canSave.value) return;
  emit("declare", { label: label.value.trim(), factor: factor.value.replace(",", "."), kind: kind.value });
  declaring.value = false;
}
</script>

<template>
  <div
    :class="
      deciding ?
        diverging ? 'rounded-md border border-destructive/40 bg-destructive/10 p-3'
        : 'rounded-md border border-warning/40 bg-warning/10 p-3'
      : ''
    "
  >
    <p
      v-if="deciding"
      class="flex items-center gap-1.5 text-xs font-semibold"
      :class="diverging ? 'text-destructive' : 'text-warning'"
    >
      <Icon :name="diverging ? 'lucide:triangle-alert' : 'lucide:calculator'" class="size-3.5" />
      {{ diverging ? "A nota discorda desta conta" : "Confirme a conta desta entrega" }}
    </p>

    <!-- A CONTA, e não o fator: quem recebe confere um resultado. -->
    <div v-if="deciding && proposal" class="mt-2 rounded-md bg-card px-3 py-2">
      <p class="text-sm text-muted-foreground">{{ proposal.line }}</p>
      <p class="mt-0.5 text-lg font-semibold tabular-nums">= {{ proposal.total }}</p>
    </div>

    <!-- Sem fator ainda (o insumo só foi escolhido agora): a nota já dá o total,
         e é isso que se mostra. O fator quem calcula é o servidor, ao aceitar. -->
    <div v-else-if="deciding && preview.invoiceAxes" class="mt-2 rounded-md bg-card px-3 py-2">
      <p class="text-sm text-muted-foreground">A nota diz</p>
      <p class="mt-0.5 text-lg font-semibold tabular-nums">{{ preview.invoiceAxes }}</p>
    </div>

    <p v-if="deciding && (proposal || preview.invoiceAxes)" class="mt-2 text-xs text-muted-foreground">
      {{ proposal ? provenance : "Falta dizer quanto pesa cada uma para o estoque contar certo." }}
    </p>

    <div v-if="deciding && (proposal || preview.invoiceAxes)" class="mt-3 flex flex-wrap items-center gap-2">
      <button
        type="button"
        :disabled="pending"
        class="inline-flex h-11 items-center gap-1.5 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground disabled:opacity-50"
        @click="proposal ? emit('accept') : emit('acceptAxes')"
      >
        <Icon name="lucide:check" class="size-4" />
        Confere
      </button>
      <button
        type="button"
        class="inline-flex h-11 items-center rounded-md border border-border bg-card px-4 text-sm font-medium hover:bg-accent"
        @click="choosing = true"
      >
        Não é assim
      </button>
    </div>

    <!-- Nem proposta nem eixos: a nota não respondeu, e a tela diz o que fazer. -->
    <div v-else-if="deciding" class="mt-2">
      <p class="text-sm text-muted-foreground">
        A nota não diz quanto vale cada {{ preview.line.invoiceUnit || "embalagem" }} em {{ preview.material.unit }}.
      </p>
      <div class="mt-3 flex flex-wrap items-center gap-2">
        <button type="button" class="inline-flex h-11 items-center gap-1.5 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground" @click="openDeclare">
          <Icon name="lucide:plus" class="size-4" />
          Cadastrar embalagem
        </button>
        <button v-if="conversions.length" type="button" class="inline-flex h-11 items-center rounded-md border border-border bg-card px-4 text-sm font-medium hover:bg-accent" @click="choosing = true">
          Escolher uma já cadastrada
        </button>
      </div>
    </div>

    <!-- O campo: normal quando não há nada a decidir, ou revelado por "Não é assim". -->
    <div v-if="showsField && !declaring">
      <label class="block text-xs font-medium text-muted-foreground" :class="choosing ? 'mt-3' : ''">
        Como isto é contado
        <!-- `value=""` e nao `:value="null"`: quem le a selecao aqui e o DOM, e
             o DOM so guarda string. Um `null` ligado viraria a string "null" e
             a linha voltaria com uma conversao inexistente. -->
        <select
          :value="preview.line.conversionId ?? ''"
          class="mt-1 h-11 w-full rounded-md border border-border bg-card px-3 text-sm text-foreground"
          @change="emit('select', ($event.target as HTMLSelectElement).value || null)"
        >
          <option value="">Direto em {{ preview.material.unit }}</option>
          <option v-for="conversion in conversions" :key="conversion.id" :value="conversion.id">{{ conversion.label }}</option>
        </select>
      </label>
      <div class="mt-2 flex flex-wrap items-center gap-2">
        <button type="button" class="inline-flex h-9 items-center gap-1.5 rounded-md border border-border bg-card px-3 text-xs font-medium hover:bg-accent" @click="openDeclare">
          <Icon name="lucide:plus" class="size-3.5" />
          Cadastrar embalagem
        </button>
        <button v-if="choosing" type="button" class="inline-flex h-9 items-center rounded-md px-3 text-xs font-medium text-muted-foreground hover:bg-accent" @click="choosing = false">
          Voltar
        </button>
      </div>
    </div>

    <div v-if="declaring" class="mt-2 space-y-2 rounded-md border border-border bg-card p-3">
      <p class="text-xs font-semibold text-foreground">Cadastrar embalagem</p>
      <label class="block text-xs font-medium text-muted-foreground">
        Como você chama isto
        <input
          v-model="label"
          class="mt-1 h-11 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground"
          :placeholder="preview.line.invoiceUnit ? `${preview.line.invoiceUnit.toLowerCase()} 5 kg` : 'saco 25 kg'"
        />
      </label>
      <label class="block text-xs font-medium text-muted-foreground">
        Quanto vale UMA, em {{ preview.material.unit }}
        <input
          v-model="factor"
          inputmode="decimal"
          class="mt-1 h-11 w-full rounded-md border border-border bg-background px-3 text-sm tabular-nums text-foreground"
          placeholder="25"
        />
      </label>
      <label class="block text-xs font-medium text-muted-foreground">
        Esse número é
        <select v-model="kind" class="mt-1 h-11 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground">
          <option value="conventional">Exato — é assim que vem embalado</option>
          <option value="approximate">Aproximado — é uma estimativa</option>
        </select>
      </label>
      <div class="flex flex-wrap items-center gap-2 pt-1">
        <button
          type="button"
          :disabled="!canSave || pending"
          class="inline-flex h-11 items-center gap-1.5 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground disabled:opacity-50"
          @click="submitDeclare"
        >
          <Icon name="lucide:check" class="size-4" />
          Salvar
        </button>
        <button type="button" class="inline-flex h-11 items-center rounded-md border border-border px-4 text-sm font-medium hover:bg-accent" @click="declaring = false">
          Cancelar
        </button>
      </div>
    </div>
  </div>
</template>
