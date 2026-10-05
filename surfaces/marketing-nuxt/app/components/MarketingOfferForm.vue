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

function selectedValues(event: Event): string[] {
  const target = event.target;
  if (!(target instanceof HTMLSelectElement)) return [];
  return Array.from(target.selectedOptions, (option) => option.value);
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

    <div class="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
      <section class="space-y-4 rounded-xl border border-border bg-card p-5">
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

        <div class="grid gap-4 sm:grid-cols-2">
          <label class="grid gap-1.5 text-sm font-medium">
            Começa em
            <UiDateTimeField
              v-model="validFrom"
              label="Início da oferta"
              required
              :aria-invalid="Boolean(fieldError('valid_from'))"
            />
            <span v-if="fieldError('valid_from')" class="text-xs text-destructive">
              {{ fieldError("valid_from") }}
            </span>
          </label>
          <label class="grid gap-1.5 text-sm font-medium">
            Termina em
            <UiDateTimeField
              v-model="validUntil"
              label="Fim da oferta"
              required
              :aria-invalid="Boolean(fieldError('valid_until'))"
            />
            <span v-if="fieldError('valid_until')" class="text-xs text-destructive">
              {{ fieldError("valid_until") }}
            </span>
          </label>
        </div>
        <p class="text-xs text-muted-foreground">
          Horário da loja:
          {{ options?.shop_timezone || "configurado pelo servidor" }}.
        </p>
      </section>

      <section class="space-y-4 rounded-xl border border-border bg-card p-5">
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

        <label class="grid gap-1.5 text-sm font-medium">
          Produtos
          <select
            multiple
            size="6"
            class="min-h-36 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            @change="skus = selectedValues($event)"
          >
            <option
              v-for="choice in options?.products ?? []"
              :key="choice.value"
              :value="choice.value"
            >
              {{ choice.label }}
            </option>
          </select>
          <span class="text-xs font-normal text-muted-foreground">
            Use Ctrl/⌘ para selecionar mais de um.
          </span>
        </label>

        <label class="grid gap-1.5 text-sm font-medium">
          Coleções
          <select
            multiple
            size="4"
            class="min-h-28 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            @change="collections = selectedValues($event)"
          >
            <option
              v-for="choice in options?.collections ?? []"
              :key="choice.value"
              :value="choice.value"
            >
              {{ choice.label }}
            </option>
          </select>
        </label>
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
        <label class="grid gap-1.5 text-sm font-medium">
          Canais de venda
          <select
            multiple
            size="3"
            class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            @change="channels = selectedValues($event)"
          >
            <option
              v-for="choice in options?.channels ?? []"
              :key="choice.value"
              :value="choice.value"
            >
              {{ choice.label }}
            </option>
          </select>
        </label>
        <label class="grid gap-1.5 text-sm font-medium">
          Entrega ou retirada
          <select
            multiple
            size="2"
            class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            @change="fulfillmentTypes = selectedValues($event)"
          >
            <option
              v-for="choice in options?.fulfillment_types ?? []"
              :key="choice.value"
              :value="choice.value"
            >
              {{ choice.label }}
            </option>
          </select>
        </label>
        <label class="grid gap-1.5 text-sm font-medium">
          Segmentos de clientes
          <select
            multiple
            size="3"
            class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            @change="customerSegments = selectedValues($event)"
          >
            <option
              v-for="choice in options?.customer_segments ?? []"
              :key="choice.value"
              :value="choice.value"
            >
              {{ choice.label }}
            </option>
          </select>
        </label>
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
