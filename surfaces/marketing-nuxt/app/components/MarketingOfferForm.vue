<script setup lang="ts">
import type { MarketingOfferOptions } from "~/types/campaign";

const props = defineProps<{
  kind: "offer" | "coupon";
  options?: MarketingOfferOptions;
  busy?: boolean;
  globalError?: string;
  fieldErrors?: Record<string, string[]>;
}>();
const emit = defineEmits<{
  submit: [payload: Record<string, unknown>];
  cancel: [];
}>();

function localInput(date: Date): string {
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return shifted.toISOString().slice(0, 16);
}

const now = new Date();
const name = ref("");
const couponCode = ref("");
const type = ref<"percent" | "fixed" | "free_delivery">("percent");
const value = ref("10");
const validFrom = ref(localInput(now));
const validUntil = ref(localInput(new Date(now.getTime() + 7 * 86_400_000)));
const minOrder = ref("0");
const maxUses = ref("0");
const skus = ref<string[]>([]);
const collections = ref<string[]>([]);
const channels = ref<string[]>([]);
const fulfillmentTypes = ref<string[]>([]);
const customerSegments = ref<string[]>([]);
const birthdayOnly = ref(false);
const isActive = ref(true);
const minValidityDate = localInput(now).slice(0, 10);
const advancedOpen = ref(false);
// O `NuxtForm` pede um estado; a validação é a do `canSubmit` (e a do servidor).
const formState = computed(() => ({
  name: name.value,
  coupon_code: couponCode.value,
}));

const validityDates = computed({
  get: () => ({
    start: validFrom.value.slice(0, 10),
    end: validUntil.value.slice(0, 10),
  }),
  set: (next: { start?: string; end?: string }) => {
    const startTime = validFrom.value.slice(11, 16) || "00:00";
    const endTime = validUntil.value.slice(11, 16) || "23:59";
    validFrom.value = next.start ? `${next.start}T${startTime}` : "";
    validUntil.value = next.end ? `${next.end}T${endTime}` : "";
  },
});

const validityTimes = computed({
  get: () => ({
    start: validFrom.value.slice(11, 16),
    end: validUntil.value.slice(11, 16),
  }),
  set: (next: { start?: string; end?: string }) => {
    const startDate = validFrom.value.slice(0, 10);
    const endDate = validUntil.value.slice(0, 10);
    validFrom.value = startDate && next.start ? `${startDate}T${next.start}` : "";
    validUntil.value = endDate && next.end ? `${endDate}T${next.end}` : "";
  },
});

const validityProblem = computed(() => {
  const startsAt = Date.parse(validFrom.value);
  const endsAt = Date.parse(validUntil.value);
  if (!Number.isFinite(startsAt) || !Number.isFinite(endsAt)) return "";
  return endsAt <= startsAt
    ? "O fim da vigência precisa acontecer depois do início."
    : "";
});

const valueLabel = computed(() => {
  if (type.value === "percent") return "Percentual de desconto";
  if (type.value === "fixed") return "Desconto em reais";
  return "Teto do frete em reais";
});
const valueHint = computed(() =>
  type.value === "free_delivery"
    ? "Use 0 para cobrir todo o frete."
    : "O desconto é conferido novamente no carrinho.",
);
const canSubmit = computed(
  () => {
    const amount = Number(value.value);
    const startsAt = Date.parse(validFrom.value);
    const endsAt = Date.parse(validUntil.value);
    const code = couponCode.value.trim();
    return (
      name.value.trim().length > 0 &&
      Number.isFinite(amount) &&
      (type.value === "free_delivery" ? amount >= 0 : amount > 0) &&
      (type.value !== "percent" || amount <= 100) &&
      Number.isFinite(startsAt) &&
      Number.isFinite(endsAt) &&
      endsAt > startsAt &&
      (props.kind === "offer" || /^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(code))
    );
  },
);

const fieldLabels: Record<string, string> = {
  payload: "Cadastro",
  kind: "Tipo de cadastro",
  name: "Nome para a equipe",
  coupon_code: "Código do cupom",
  type: "Tipo de benefício",
  value: "Valor do benefício",
  valid_from: "Começa em",
  valid_until: "Termina em",
  skus: "Produtos",
  collections: "Coleções",
  min_order_q: "Pedido mínimo",
  max_uses: "Limite de usos",
  channels: "Canais de venda",
  fulfillment_types: "Entrega ou retirada",
  customer_segments: "Segmentos de clientes",
  birthday_only: "Somente aniversariantes",
  is_active: "Ativar ao salvar",
  ref: "Referência",
};
const visibleErrors = computed(() =>
  Object.entries(props.fieldErrors ?? {}).flatMap(([field, messages]) =>
    messages.map((message) => ({
      field,
      label: fieldLabels[field] ?? field,
      message,
    })),
  ),
);

function fieldError(field: string): string {
  return props.fieldErrors?.[field]?.[0] ?? "";
}

function cents(raw: string): number {
  const normalized = raw.trim().replace(",", ".");
  const parsed = Number(normalized || 0);
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : 0;
}

function submit() {
  if (!canSubmit.value || props.busy) return;
  emit("submit", {
    kind: props.kind,
    name: name.value.trim(),
    coupon_code:
      props.kind === "coupon" ? couponCode.value.trim().toUpperCase() : "",
    type: type.value,
    value: type.value === "percent" ? Number(value.value) : cents(value.value),
    valid_from: validFrom.value,
    valid_until: validUntil.value,
    min_order_q: cents(minOrder.value),
    max_uses: props.kind === "coupon" ? Number(maxUses.value || 0) : 0,
    skus: skus.value,
    collections: collections.value,
    channels: channels.value,
    fulfillment_types: fulfillmentTypes.value,
    customer_segments: customerSegments.value,
    birthday_only: birthdayOnly.value,
    is_active: isActive.value,
  });
}
</script>

<template>
  <NuxtForm
    :state="formState"
    class="mx-auto w-full max-w-5xl space-y-6"
    @submit="submit"
  >
    <NuxtAlert
      v-if="globalError || visibleErrors.length"
      color="error"
      variant="subtle"
      icon="i-lucide-circle-alert"
      :title="globalError || 'Revise os campos destacados.'"
      tabindex="-1"
    >
      <template v-if="visibleErrors.length" #description>
        <ul class="list-disc space-y-1 pl-5">
          <li
            v-for="error in visibleErrors"
            :key="`${error.field}:${error.message}`"
          >
            <strong>{{ error.label }}:</strong> {{ error.message }}
          </li>
        </ul>
      </template>
    </NuxtAlert>

    <div
      class="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]"
    >
      <NuxtCard class="min-w-0">
        <div class="space-y-4">
          <div>
            <p class="text-xs font-semibold text-primary">
              {{
                kind === "coupon"
                  ? "Identificação do cupom"
                  : "Identificação da oferta"
              }}
            </p>
            <h2 class="mt-1 text-base font-semibold">
              {{
                kind === "coupon" ? "Código e desconto" : "Benefício comercial"
              }}
            </h2>
          </div>

          <NuxtFormField
            v-if="kind === 'coupon'"
            label="Código do cupom"
            help="Sem espaços; letras, números, hífen e sublinhado."
            :error="fieldError('coupon_code') || undefined"
            required
          >
            <NuxtInput
              id="marketing-offer-coupon-code"
              v-model="couponCode"
              autocomplete="off"
              :maxlength="50"
              placeholder="EX.: PRIMEIRACOMPRA"
              class="w-full uppercase"
              required
              :aria-invalid="Boolean(fieldError('coupon_code'))"
            />
          </NuxtFormField>

          <NuxtFormField
            label="Nome para a equipe"
            :error="fieldError('name') || undefined"
            required
          >
            <NuxtInput
              id="marketing-offer-name"
              v-model="name"
              :maxlength="200"
              :placeholder="
                kind === 'coupon' ? 'Primeira compra' : 'Semana do croissant'
              "
              class="w-full"
              required
              :aria-invalid="Boolean(fieldError('name'))"
            />
          </NuxtFormField>

          <div class="grid gap-4 sm:grid-cols-2">
            <NuxtFormField
              label="Tipo de benefício"
              :error="fieldError('type') || undefined"
            >
              <NuxtSelect
                id="marketing-offer-type"
                v-model="type"
                :items="options?.types ?? []"
                class="w-full"
                :aria-invalid="Boolean(fieldError('type'))"
              />
            </NuxtFormField>
            <NuxtFormField
              :label="valueLabel"
              :help="valueHint"
              :error="fieldError('value') || undefined"
              required
            >
              <NuxtInput
                id="marketing-offer-value"
                v-model="value"
                type="number"
                :min="type === 'free_delivery' ? 0 : 0.01"
                :max="type === 'percent' ? 100 : undefined"
                :step="type === 'percent' ? 1 : 0.01"
                class="w-full"
                required
                :aria-invalid="Boolean(fieldError('value'))"
              />
            </NuxtFormField>
          </div>

          <div class="grid gap-4">
            <NuxtFormField
              label="Período de validade"
              required
              :error="
                fieldError('valid_from') ||
                fieldError('valid_until') ||
                undefined
              "
            >
              <UiDateRangeField
                id="marketing-offer-validity-dates"
                v-model="validityDates"
                label="Período de validade"
                :min="minValidityDate"
                :clearable="false"
                :allow-open-ended="false"
                required
                :aria-invalid="
                  Boolean(fieldError('valid_from') || fieldError('valid_until'))
                "
              />
            </NuxtFormField>

            <NuxtFormField
              label="Horário de início e fim"
              :help="
                options?.shop_timezone
                  ? `Horário da loja: ${options.shop_timezone}.`
                  : 'Vale o horário da loja.'
              "
              :error="validityProblem || undefined"
              required
            >
              <UiTimeRangeField
                id="marketing-offer-validity-times"
                v-model="validityTimes"
                label="Horário de início e fim"
                required
                :aria-invalid="Boolean(validityProblem)"
              />
            </NuxtFormField>
          </div>
        </div>
      </NuxtCard>

      <NuxtCard class="min-w-0">
        <div class="space-y-4">
          <div>
            <p class="text-xs font-semibold text-primary">Alcance</p>
            <h2 class="mt-1 text-base font-semibold">Onde o benefício vale</h2>
            <p class="mt-1 text-sm text-muted-foreground">
              Sem produto ou coleção, vale para todo o catálogo. Para usar uma
              oferta em campanha, escolha ao menos um produto ou coleção.
            </p>
          </div>

          <div v-if="options?.products.length" class="max-h-72 overflow-y-auto">
            <NuxtCheckboxGroup
              v-model="skus"
              :items="options?.products ?? []"
              legend="Produtos"
              variant="card"
            />
          </div>
          <p v-else class="text-sm text-muted-foreground">
            Nenhum produto disponível para restringir esta oferta.
          </p>

          <div
            v-if="options?.collections.length"
            class="max-h-56 overflow-y-auto"
          >
            <NuxtCheckboxGroup
              v-model="collections"
              :items="options?.collections ?? []"
              legend="Coleções"
              variant="card"
            />
          </div>
          <p v-else class="text-sm text-muted-foreground">
            Nenhuma coleção disponível para restringir esta oferta.
          </p>
        </div>
      </NuxtCard>
    </div>

    <NuxtCard>
      <NuxtCollapsible v-model:open="advancedOpen" :unmount-on-hide="false">
        <NuxtButton
          color="neutral"
          variant="ghost"
          block
          class="justify-start"
          label="Condições avançadas"
          :trailing-icon="
            advancedOpen ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'
          "
          data-offer-advanced-toggle
        />
        <template #content>
          <div class="mt-2 space-y-4">
            <p class="text-sm text-muted-foreground">
              Deixe uma lista vazia para aceitar todos os casos daquela
              condição.
            </p>
            <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              <NuxtFormField label="Pedido mínimo em reais">
                <NuxtInput
                  id="marketing-offer-min-order"
                  v-model="minOrder"
                  type="number"
                  min="0"
                  step="0.01"
                  class="w-full"
                />
              </NuxtFormField>
              <NuxtFormField
                v-if="kind === 'coupon'"
                label="Limite total de usos"
                help="0 = ilimitado."
              >
                <NuxtInput
                  id="marketing-offer-max-uses"
                  v-model="maxUses"
                  type="number"
                  min="0"
                  step="1"
                  class="w-full"
                />
              </NuxtFormField>
              <NuxtCheckboxGroup
                v-if="options?.channels.length"
                v-model="channels"
                :items="options?.channels ?? []"
                legend="Canais de venda"
                variant="card"
              />
              <NuxtCheckboxGroup
                v-if="options?.fulfillment_types.length"
                v-model="fulfillmentTypes"
                :items="options?.fulfillment_types ?? []"
                legend="Entrega ou retirada"
                variant="card"
              />
              <NuxtCheckboxGroup
                v-if="options?.customer_segments.length"
                v-model="customerSegments"
                :items="options?.customer_segments ?? []"
                legend="Segmentos de clientes"
                variant="card"
              />
            </div>
            <div class="flex flex-wrap gap-5">
              <NuxtCheckbox
                v-model="birthdayOnly"
                label="Somente aniversariantes"
              />
              <NuxtCheckbox v-model="isActive" label="Ativar ao salvar" />
            </div>
          </div>
        </template>
      </NuxtCollapsible>
    </NuxtCard>

    <div
      class="flex flex-col-reverse gap-2 border-t border-default pt-5 sm:flex-row sm:justify-end"
    >
      <NuxtButton
        color="neutral"
        variant="outline"
        label="Cancelar"
        :disabled="busy"
        @click="emit('cancel')"
      />
      <NuxtButton
        type="submit"
        icon="i-lucide-check"
        :disabled="!canSubmit"
        :loading="busy"
        :label="kind === 'coupon' ? 'Criar cupom' : 'Criar oferta'"
      />
    </div>
  </NuxtForm>
</template>
