<script setup lang="ts">
import type { MarketingOfferOptions } from "~/types/campaign";

const props = defineProps<{
  kind: "offer" | "coupon";
  options?: MarketingOfferOptions;
  busy?: boolean;
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
  () =>
    name.value.trim().length > 0 &&
    validFrom.value.length > 0 &&
    validUntil.value.length > 0 &&
    (props.kind === "offer" || couponCode.value.trim().length > 0),
);

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
            v-model="couponCode"
            autocomplete="off"
            maxlength="50"
            placeholder="EX.: PRIMEIRACOMPRA"
            class="uppercase"
            required
          />
          <span class="text-xs font-normal text-muted-foreground">
            Sem espaços; letras, números, hífen e sublinhado.
          </span>
        </label>

        <label class="grid gap-1.5 text-sm font-medium">
          Nome para a equipe
          <UiInput
            v-model="name"
            maxlength="200"
            :placeholder="
              kind === 'coupon' ? 'Primeira compra' : 'Semana do croissant'
            "
            required
          />
        </label>

        <div class="grid gap-4 sm:grid-cols-2">
          <label class="grid gap-1.5 text-sm font-medium">
            Tipo de benefício
            <UiNativeSelect v-model="type">
              <option
                v-for="choice in options?.types ?? []"
                :key="choice.value"
                :value="choice.value"
              >
                {{ choice.label }}
              </option>
            </UiNativeSelect>
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
            />
            <span class="text-xs font-normal text-muted-foreground">{{
              valueHint
            }}</span>
          </label>
        </div>

        <div class="grid gap-4 sm:grid-cols-2">
          <label class="grid gap-1.5 text-sm font-medium">
            Começa em
            <UiInput v-model="validFrom" type="datetime-local" required />
          </label>
          <label class="grid gap-1.5 text-sm font-medium">
            Termina em
            <UiInput v-model="validUntil" type="datetime-local" required />
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
        <label class="flex min-h-11 items-center gap-2 text-sm font-medium">
          <input
            v-model="birthdayOnly"
            type="checkbox"
            class="rounded border-input text-primary"
          />
          Somente aniversariantes
        </label>
        <label class="flex min-h-11 items-center gap-2 text-sm font-medium">
          <input
            v-model="isActive"
            type="checkbox"
            class="rounded border-input text-primary"
          />
          Ativar ao salvar
        </label>
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
