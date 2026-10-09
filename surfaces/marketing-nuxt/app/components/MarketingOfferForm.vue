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
  <form class="mx-auto w-full max-w-5xl space-y-6" @submit.prevent="submit">
    <div
      v-if="globalError || visibleErrors.length"
      class="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm"
      role="alert"
      tabindex="-1"
    >
      <p class="font-semibold">
        {{ globalError || "Revise os campos destacados." }}
      </p>
      <ul v-if="visibleErrors.length" class="mt-2 list-disc space-y-1 pl-5">
        <li v-for="error in visibleErrors" :key="`${error.field}:${error.message}`">
          <strong>{{ error.label }}:</strong> {{ error.message }}
        </li>
      </ul>
    </div>

    <div class="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
      <section class="min-w-0 space-y-4 rounded-xl border border-border bg-card p-4 sm:p-5">
        <div>
          <p class="text-xs font-semibold uppercase tracking-wide text-primary">
            {{
              kind === "coupon"
                ? "Identificação do cupom"
                : "Identificação da oferta"
            }}
          </p>
          <h2 class="mt-1 text-lg font-semibold">
            {{
              kind === "coupon" ? "Código e desconto" : "Benefício comercial"
            }}
          </h2>
        </div>

        <label
          v-if="kind === 'coupon'"
          class="grid gap-1.5 text-sm font-medium"
        >
          Código do cupom
          <UiInput
            id="marketing-offer-coupon-code"
            v-model="couponCode"
            autocomplete="off"
            :maxlength="50"
            placeholder="EX.: PRIMEIRACOMPRA"
            class="uppercase"
            required
            :aria-invalid="Boolean(fieldError('coupon_code'))"
          />
          <span class="text-xs font-normal text-muted-foreground">
            Sem espaços; letras, números, hífen e sublinhado.
          </span>
          <span v-if="fieldError('coupon_code')" class="text-xs text-destructive">
            {{ fieldError("coupon_code") }}
          </span>
        </label>

        <label class="grid gap-1.5 text-sm font-medium">
          Nome para a equipe
          <UiInput
            id="marketing-offer-name"
            v-model="name"
            :maxlength="200"
            :placeholder="
              kind === 'coupon' ? 'Primeira compra' : 'Semana do croissant'
            "
            required
            :aria-invalid="Boolean(fieldError('name'))"
          />
          <span v-if="fieldError('name')" class="text-xs text-destructive">
            {{ fieldError("name") }}
          </span>
        </label>

        <div class="grid gap-4 sm:grid-cols-2">
          <label class="grid gap-1.5 text-sm font-medium">
            Tipo de benefício
            <UiNativeSelect
              v-model="type"
              :aria-invalid="Boolean(fieldError('type'))"
            >
              <option
                v-for="choice in options?.types ?? []"
                :key="choice.value"
                :value="choice.value"
              >
                {{ choice.label }}
              </option>
            </UiNativeSelect>
            <span v-if="fieldError('type')" class="text-xs text-destructive">
              {{ fieldError("type") }}
            </span>
          </label>
          <label class="grid gap-1.5 text-sm font-medium">
            {{ valueLabel }}
            <UiInput
              v-model="value"
              type="number"
              :min="type === 'free_delivery' ? 0 : 0.01"
              :max="type === 'percent' ? 100 : undefined"
              :step="type === 'percent' ? 1 : 0.01"
              required
              :aria-invalid="Boolean(fieldError('value'))"
            />
            <span class="text-xs font-normal text-muted-foreground">{{
              valueHint
            }}</span>
            <span v-if="fieldError('value')" class="text-xs text-destructive">
              {{ fieldError("value") }}
            </span>
          </label>
        </div>

        <div class="grid gap-4">
          <NuxtFormField
            label="Período de validade"
            required
            :error="fieldError('valid_from') || fieldError('valid_until') || undefined"
          >
            <UiDateRangeField
              id="marketing-offer-validity-dates"
              v-model="validityDates"
              label="Período de validade"
              :min="minValidityDate"
              :clearable="false"
              :allow-open-ended="false"
              required
              :aria-invalid="Boolean(fieldError('valid_from') || fieldError('valid_until'))"
            />
          </NuxtFormField>

          <NuxtFormField
            label="Horário de início e fim"
            :help="options?.shop_timezone ? `Horário da loja: ${options.shop_timezone}.` : 'Vale o horário da loja.'"
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
      </section>

      <section class="min-w-0 space-y-4 rounded-xl border border-border bg-card p-4 sm:p-5">
        <div>
          <p class="text-xs font-semibold uppercase tracking-wide text-primary">
            Alcance
          </p>
          <h2 class="mt-1 text-lg font-semibold">Onde o benefício vale</h2>
          <p class="mt-1 text-sm text-muted-foreground">
            Sem produto ou coleção, vale para todo o catálogo. Para usar uma
            oferta em campanha, escolha ao menos um produto ou coleção.
          </p>
        </div>

        <UiCheckboxGroup
          v-if="options?.products.length"
          v-model="skus"
          :items="options?.products ?? []"
          legend="Produtos"
          variant="card"
          :ui="{
            fieldset: 'max-h-72 overflow-y-auto',
            legend: 'mb-1.5 text-sm font-medium',
          }"
        />
        <p v-else class="text-sm text-muted-foreground">
          Nenhum produto disponível para restringir esta oferta.
        </p>

        <UiCheckboxGroup
          v-if="options?.collections.length"
          v-model="collections"
          :items="options?.collections ?? []"
          legend="Coleções"
          variant="card"
          :ui="{
            fieldset: 'max-h-56 overflow-y-auto',
            legend: 'mb-1.5 text-sm font-medium',
          }"
        />
        <p v-else class="text-sm text-muted-foreground">
          Nenhuma coleção disponível para restringir esta oferta.
        </p>
      </section>
    </div>

    <details class="rounded-xl border border-border bg-card p-5">
      <summary class="cursor-pointer font-semibold">
        Condições avançadas
      </summary>
      <p class="mt-1 text-sm text-muted-foreground">
        Deixe uma lista vazia para aceitar todos os casos daquela condição.
      </p>
      <div class="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <label class="grid gap-1.5 text-sm font-medium">
          Pedido mínimo em reais
          <UiInput v-model="minOrder" type="number" min="0" step="0.01" />
        </label>
        <label
          v-if="kind === 'coupon'"
          class="grid gap-1.5 text-sm font-medium"
        >
          Limite total de usos
          <UiInput v-model="maxUses" type="number" min="0" step="1" />
          <span class="text-xs font-normal text-muted-foreground"
            >0 = ilimitado.</span
          >
        </label>
        <UiCheckboxGroup
          v-if="options?.channels.length"
          v-model="channels"
          :items="options?.channels ?? []"
          legend="Canais de venda"
          variant="card"
          :ui="{ legend: 'mb-1.5 text-sm font-medium' }"
        />
        <UiCheckboxGroup
          v-if="options?.fulfillment_types.length"
          v-model="fulfillmentTypes"
          :items="options?.fulfillment_types ?? []"
          legend="Entrega ou retirada"
          variant="card"
          :ui="{ legend: 'mb-1.5 text-sm font-medium' }"
        />
        <UiCheckboxGroup
          v-if="options?.customer_segments.length"
          v-model="customerSegments"
          :items="options?.customer_segments ?? []"
          legend="Segmentos de clientes"
          variant="card"
          :ui="{ legend: 'mb-1.5 text-sm font-medium' }"
        />
      </div>
      <div class="mt-4 flex flex-wrap gap-5">
        <UiCheckbox v-model="birthdayOnly" label="Somente aniversariantes" />
        <UiCheckbox v-model="isActive" label="Ativar ao salvar" />
      </div>
    </details>

    <div
      class="flex flex-col-reverse gap-2 border-t border-border pt-5 sm:flex-row sm:justify-end"
    >
      <UiButton
        type="button"
        variant="outline"
        :disabled="busy"
        @click="emit('cancel')"
      >
        Cancelar
      </UiButton>
      <UiButton type="submit" :disabled="!canSubmit || busy" :aria-busy="busy">
        <Icon name="lucide:check" class="size-4" />
        {{
          busy
            ? "Salvando…"
            : kind === "coupon"
              ? "Criar cupom"
              : "Criar oferta"
        }}
      </UiButton>
    </div>
  </form>
</template>
