<script setup lang="ts">
// Venda por peso, em dois passos (decisão do dono, 24/09/2026):
//
// 1. DIGITAR — o campo do valor da etiqueta vem zerado e o "Continuar" fica
//    bloqueado até haver um valor. Com a balança ligada na loja
//    (`weightEntryEnabled`), o operador pode trocar para o PESO; desligada, a
//    opção nem aparece.
// 2. CONFERIR — foto e nome do item, preço do quilo, o peso aproximado e o valor
//    digitado, lado a lado com a etiqueta na mão. [Confirmar] lança; [Voltar]
//    devolve ao campo com o que foi digitado. Enter confirma, Esc volta, e o foco
//    abre no botão primário.
//
// O teclado físico e o numérico da tela escrevem no MESMO buffer, pela mesma
// regra (`editWeighedBuffer`): vírgula uma vez, 2 casas no valor e 3 no peso.
import type { POSProductProjection, POSWeighedEntry } from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";
import { productFallbackIcon, productFallbackStyle } from "~/presentation/catalog";
import {
  bufferDisplay,
  editWeighedBuffer,
  kgDisplay,
  weighedEntryFor,
  weighedPreview,
  type WeighedEntryKind,
} from "~/presentation/weighed";

const props = defineProps<{
  product: POSProductProjection | null;
  /** A loja tem balança: o operador pode digitar o peso em vez do valor. */
  weightEntryEnabled?: boolean;
}>();

const emit = defineEmits<{
  confirm: [POSProductProjection, POSWeighedEntry];
  cancel: [];
}>();

type Step = "entry" | "confirm";

const step = ref<Step>("entry");
const kind = ref<WeighedEntryKind>("label");
const buffer = ref("");

const open = computed(() => props.product !== null);
const field = computed<"money" | "kg">(() => (kind.value === "label" ? "money" : "kg"));
const pricePerKgDisplay = computed(() => (props.product ? `${formatBRL(props.product.price_q)}/kg` : ""));
const preview = computed(() => weighedPreview({
  kind: kind.value,
  buffer: buffer.value,
  pricePerKgQ: props.product?.price_q ?? 0,
}));
const hasImage = computed(() => Boolean(props.product?.image_url?.trim()));
const fallbackStyle = computed(() => (props.product ? productFallbackStyle(props.product) : {}));
const fallbackIcon = computed(() => (props.product ? productFallbackIcon(props.product) : ""));

// Próximo foco: no passo de digitar, o campo; no de conferir, o [Confirmar].
const focusKey = computed(() => (open.value ? `weighed-${step.value}` : null));
useNextFocus(focusKey);

watch(() => props.product, (product) => {
  if (!product) return;
  step.value = "entry";
  kind.value = "label";
  buffer.value = "";
});

function setKind(next: WeighedEntryKind) {
  if (next === kind.value) return;
  kind.value = next;
  buffer.value = "";
}

function press(key: string) {
  buffer.value = editWeighedBuffer(buffer.value, key, field.value);
}

function toConfirm() {
  if (!preview.value.ok) return;
  step.value = "confirm";
}

function back() {
  step.value = "entry";
}

function commit() {
  const product = props.product;
  if (!product || !preview.value.ok) return;
  emit("confirm", product, weighedEntryFor(kind.value, preview.value));
}

function onEntryKeydown(event: KeyboardEvent) {
  if (event.altKey || event.ctrlKey || event.metaKey) return;
  if (event.key === "Enter") {
    event.preventDefault();
    toConfirm();
    return;
  }
  if (/^[0-9]$/.test(event.key) || event.key === "," || event.key === "." || event.key === "Backspace") {
    event.preventDefault();
    press(event.key);
  }
}

// Colar, ditado e teclado virtual chegam por `input`: o texto passa pela MESMA
// regra, tecla a tecla, e o campo mostra o que ficou valendo.
function onEntryInput(event: Event) {
  const target = event.target as HTMLInputElement;
  let next = "";
  for (const char of target.value) next = editWeighedBuffer(next, char, field.value);
  buffer.value = next;
  target.value = next;
}

// Enter no passo de conferir confirma — salvo se o foco está no [Voltar], que
// então faz o que diz.
function onConfirmKeydown(event: KeyboardEvent) {
  if (event.key !== "Enter") return;
  if ((event.target as HTMLElement | null)?.dataset?.role === "back") return;
  event.preventDefault();
  commit();
}

// Esc: no conferir, volta ao campo; no digitar, fecha sem lançar nada.
function onEscape(event: KeyboardEvent) {
  if (step.value === "confirm") {
    event.preventDefault();
    back();
  }
}

const keypad = ["1", "2", "3", "4", "5", "6", "7", "8", "9", ",", "0", "Backspace"];
const segmentClass = (active: boolean) => (active ? "border-primary bg-primary/5 text-foreground" : "text-muted-foreground");
</script>

<template>
  <UiDialog :open="open" @update:open="(value) => { if (!value) emit('cancel') }">
    <UiDialogContent
      class="sm:max-w-md"
      data-testid="weighed-entry-dialog"
      @escape-key-down="onEscape"
    >
      <!-- 1. DIGITAR -->
      <template v-if="step === 'entry'">
        <UiDialogHeader>
          <UiDialogTitle>{{ product?.name }}</UiDialogTitle>
          <UiDialogDescription>
            {{ pricePerKgDisplay }} · {{ weightEntryEnabled ? "digite o valor da etiqueta ou o peso." : "digite o valor da etiqueta." }}
          </UiDialogDescription>
        </UiDialogHeader>

        <div
          v-if="weightEntryEnabled"
          class="grid grid-cols-2 gap-2"
          role="radiogroup"
          aria-label="O que digitar"
        >
          <button
            type="button"
            role="radio"
            :aria-checked="kind === 'label'"
            class="h-11 rounded-md border text-sm font-medium"
            :class="segmentClass(kind === 'label')"
            @mousedown.prevent
            @click="setKind('label')"
          >
            Valor da etiqueta
          </button>
          <button
            type="button"
            role="radio"
            :aria-checked="kind === 'weight'"
            class="h-11 rounded-md border text-sm font-medium"
            :class="segmentClass(kind === 'weight')"
            @mousedown.prevent
            @click="setKind('weight')"
          >
            Peso
          </button>
        </div>

        <label data-focus-target="weighed-entry" class="grid gap-1 text-sm">
          <span class="font-medium text-muted-foreground">{{ kind === "label" ? "Valor da etiqueta" : "Peso" }}</span>
          <span class="flex h-14 items-center gap-2 rounded-md border border-primary bg-card px-3">
            <span v-if="kind === 'label'" class="text-lg text-muted-foreground">R$</span>
            <input
              data-focus-control
              :value="buffer"
              :placeholder="bufferDisplay('', field)"
              inputmode="decimal"
              autocomplete="off"
              :aria-label="kind === 'label' ? 'Valor da etiqueta, em reais' : 'Peso, em quilos'"
              class="min-w-0 flex-1 bg-transparent text-3xl font-semibold tabular-nums outline-none placeholder:text-muted-foreground/60"
              @keydown="onEntryKeydown"
              @input="onEntryInput"
            />
            <span v-if="kind === 'weight'" class="text-lg text-muted-foreground">kg</span>
          </span>
        </label>

        <p class="min-h-5 text-sm" aria-live="polite">
          <span v-if="preview.error" class="text-destructive">{{ preview.error }}</span>
          <span v-else-if="preview.ok && kind === 'label'" class="text-muted-foreground">
            ≈ {{ kgDisplay(preview.weightG) }}
          </span>
          <span v-else-if="preview.ok" class="text-muted-foreground">{{ formatBRL(preview.totalQ) }}</span>
        </p>

        <div class="grid grid-cols-3 gap-1.5" aria-label="Teclado numérico">
          <UiButton
            v-for="key in keypad"
            :key="key"
            variant="outline"
            class="h-14 text-xl tabular-nums"
            :class="key === 'Backspace' ? 'text-destructive' : ''"
            :aria-label="key === 'Backspace' ? 'Apagar' : key === ',' ? 'Vírgula' : key"
            @mousedown.prevent
            @click="press(key)"
          >
            <Icon v-if="key === 'Backspace'" name="lucide:delete" class="size-5" />
            <template v-else>{{ key }}</template>
          </UiButton>
        </div>

        <UiDialogFooter>
          <UiButton variant="outline" size="lg" @click="emit('cancel')">Cancelar</UiButton>
          <UiButton size="lg" :disabled="!preview.ok" @click="toConfirm">Continuar</UiButton>
        </UiDialogFooter>
      </template>

      <!-- 2. CONFERIR -->
      <template v-else>
        <UiDialogHeader>
          <UiDialogTitle>Confira com a etiqueta</UiDialogTitle>
          <UiDialogDescription>Confirmar lança o item no pedido.</UiDialogDescription>
        </UiDialogHeader>

        <div class="flex items-center gap-4">
          <div class="size-24 shrink-0 overflow-hidden rounded-md border">
            <img v-if="hasImage" :src="product?.image_url" :alt="product?.name" class="size-full object-cover" />
            <div v-else class="pos-tile-fallback grid size-full place-items-center" :style="fallbackStyle" aria-hidden="true">
              <Icon :name="fallbackIcon" class="size-8" />
            </div>
          </div>
          <div class="grid min-w-0 gap-0.5">
            <p class="text-lg font-semibold leading-tight">{{ product?.name }}</p>
            <p class="text-sm tabular-nums text-muted-foreground">{{ pricePerKgDisplay }}</p>
          </div>
        </div>

        <dl class="grid gap-2 rounded-md border bg-muted/30 p-4">
          <template v-if="kind === 'label'">
            <div class="flex items-baseline justify-between gap-4">
              <dt class="text-sm text-muted-foreground">Valor da etiqueta</dt>
              <dd class="text-3xl font-semibold tabular-nums">{{ formatBRL(preview.labelQ ?? 0) }}</dd>
            </div>
            <div class="flex items-baseline justify-between gap-4">
              <dt class="text-sm text-muted-foreground">Peso aproximado</dt>
              <dd class="text-lg font-medium tabular-nums">≈ {{ kgDisplay(preview.weightG) }}</dd>
            </div>
            <div v-if="preview.gapQ > 0" class="flex items-baseline justify-between gap-4">
              <dt class="text-sm text-muted-foreground">Cobrado</dt>
              <dd class="text-lg font-medium tabular-nums">{{ formatBRL(preview.totalQ) }}</dd>
            </div>
          </template>
          <template v-else>
            <div class="flex items-baseline justify-between gap-4">
              <dt class="text-sm text-muted-foreground">Peso</dt>
              <dd class="text-lg font-medium tabular-nums">{{ kgDisplay(preview.weightG) }}</dd>
            </div>
            <div class="flex items-baseline justify-between gap-4">
              <dt class="text-sm text-muted-foreground">Valor</dt>
              <dd class="text-3xl font-semibold tabular-nums">{{ formatBRL(preview.totalQ) }}</dd>
            </div>
          </template>
        </dl>

        <p v-if="preview.gapNote" class="rounded-md bg-warning/10 px-3 py-2 text-sm text-warning">{{ preview.gapNote }}</p>

        <UiDialogFooter data-focus-target="weighed-confirm" @keydown="onConfirmKeydown">
          <UiButton variant="outline" size="lg" data-role="back" @click="back">Voltar</UiButton>
          <UiButton size="lg" data-focus-control @click="commit">Confirmar</UiButton>
        </UiDialogFooter>
      </template>
    </UiDialogContent>
  </UiDialog>
</template>
