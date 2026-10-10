<script setup lang="ts">
// Escolhas no produto (Fase 1), na mesma moldura do diálogo de peso: cabeçalho
// com foto, nome e preço; um bloco por grupo ("Sabor", "Adicionais") com a
// regra legível; total ao vivo; [Voltar] à esquerda e [Lançar] à direita.
//
// O [Lançar] só age com os mínimos cumpridos. Enter lança (salvo com o foco no
// [Voltar], que faz o que diz); Espaço marca a opção em foco; Esc fecha sem
// lançar nada. O foco abre na primeira opção disponível do primeiro grupo.
import type { POSCartItemOption, POSProductProjection } from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";
import { productFallbackIcon, productFallbackStyle } from "~/presentation/catalog";
import {
  groupMissing,
  groupRuleLabel,
  isSingleChoice,
  lineUnitPriceQ,
  optionPriceLabel,
  selectedCartOptions,
  selectionValid,
  toggleOption,
  type OptionSelection,
} from "~/presentation/productOptions";

const props = defineProps<{
  product: POSProductProjection | null;
}>();

const emit = defineEmits<{
  confirm: [POSProductProjection, POSCartItemOption[]];
  cancel: [];
}>();

const selection = ref<OptionSelection>({});

const open = computed(() => props.product !== null);
const groups = computed(() => props.product?.option_groups || []);
const chosen = computed(() => selectedCartOptions(groups.value, selection.value));
const valid = computed(() => selectionValid(groups.value, selection.value));
const totalQ = computed(() => lineUnitPriceQ(props.product?.price_q ?? 0, chosen.value));
const hasImage = computed(() => Boolean(props.product?.image_url?.trim()));
const fallbackStyle = computed(() => (props.product ? productFallbackStyle(props.product) : {}));
const fallbackIcon = computed(() => (props.product ? productFallbackIcon(props.product) : ""));
// A primeira opção que dá para tocar: é nela que o foco abre.
const firstFocus = computed(() => {
  for (const group of groups.value) {
    const option = group.options.find((entry) => entry.available);
    if (option) return `${group.ref}:${option.ref}`;
  }
  return "";
});

const focusKey = computed(() => (open.value ? "product-options" : null));
useNextFocus(focusKey);

watch(() => props.product, (product) => {
  if (product) selection.value = {};
});

function isChosen(groupRef: string, optionRef: string): boolean {
  return (selection.value[groupRef] || []).includes(optionRef);
}

function toggle(groupRef: string, optionRef: string) {
  const group = groups.value.find((entry) => entry.ref === groupRef);
  if (!group) return;
  selection.value = toggleOption(group, selection.value, optionRef);
}

function confirm() {
  const product = props.product;
  if (!product || !valid.value) return;
  emit("confirm", product, chosen.value);
}

function onKeydown(event: KeyboardEvent) {
  if (event.key !== "Enter" || event.altKey || event.ctrlKey || event.metaKey) return;
  if ((event.target as HTMLElement | null)?.dataset?.role === "back") return;
  event.preventDefault();
  confirm();
}

function missingLabel(missing: number): string {
  return missing === 1 ? "Falta escolher 1" : `Faltam escolher ${missing}`;
}

const optionClass = (active: boolean, available: boolean) => {
  if (!available) return "cursor-not-allowed border-dashed text-muted-foreground opacity-60";
  return active ? "border-primary bg-primary/5 text-foreground" : "hover:border-primary/50";
};
</script>

<template>
  <UiDialog :open="open" @update:open="(value) => { if (!value) emit('cancel') }">
    <UiDialogContent
      class="grid-cols-[minmax(0,1fr)] sm:max-w-md"
      data-testid="product-options-dialog"
      @keydown="onKeydown"
    >
      <UiDialogHeader class="min-w-0">
        <div class="flex min-w-0 items-center gap-4 pr-6">
          <div class="size-16 shrink-0 overflow-hidden rounded-md border">
            <img v-if="hasImage" :src="product?.image_url" :alt="product?.name" class="size-full object-cover" />
            <div v-else class="pos-tile-fallback grid size-full place-items-center" :style="fallbackStyle" aria-hidden="true">
              <Icon :name="fallbackIcon" class="size-6" />
            </div>
          </div>
          <div class="grid min-w-0 gap-0.5 text-left">
            <UiDialogTitle class="leading-tight">{{ product?.name }}</UiDialogTitle>
            <UiDialogDescription class="tabular-nums">{{ product?.price_display }}</UiDialogDescription>
          </div>
        </div>
      </UiDialogHeader>

      <div class="grid max-h-[60vh] min-w-0 content-start gap-4 overflow-y-auto" data-focus-target="product-options">
        <fieldset
          v-for="group in groups"
          :key="group.ref"
          class="grid min-w-0 gap-2"
          :data-testid="`options-group-${group.ref}`"
        >
          <legend class="mb-2 flex w-full items-baseline justify-between gap-2">
            <span class="text-sm font-semibold">{{ group.label }}</span>
            <span
              class="text-xs"
              :class="groupMissing(group, selection) > 0 ? 'font-medium text-warning' : 'text-muted-foreground'"
            >
              {{ groupRuleLabel(group) }}<template v-if="groupMissing(group, selection) > 0"> · {{ missingLabel(groupMissing(group, selection)) }}</template>
            </span>
          </legend>
          <div
            class="grid min-w-0 grid-cols-2 gap-2"
            :role="isSingleChoice(group) ? 'radiogroup' : 'group'"
            :aria-label="group.label"
          >
            <NuxtButton
              v-for="option in group.options"
              :key="option.ref"
              color="neutral"
              variant="ghost"
              :role="isSingleChoice(group) ? 'radio' : 'checkbox'"
              :aria-checked="isChosen(group.ref, option.ref)"
              :disabled="!option.available"
              :data-focus-control="firstFocus === `${group.ref}:${option.ref}` ? '' : undefined"
              :data-option="`${group.ref}:${option.ref}`"
              class="flex min-h-14 min-w-0 flex-col items-start justify-center gap-0.5 rounded-md border px-3 py-2 text-left text-sm font-medium transition"
              :class="optionClass(isChosen(group.ref, option.ref), option.available)"
              @click="toggle(group.ref, option.ref)"
            >
              <span class="flex w-full min-w-0 items-center gap-1.5">
                <Icon
                  v-if="isChosen(group.ref, option.ref)"
                  name="lucide:check"
                  class="size-4 shrink-0 text-primary"
                  aria-hidden="true"
                />
                <span class="min-w-0 break-words">{{ option.label }}</span>
              </span>
              <span v-if="!option.available" class="text-xs">Indisponível</span>
              <span v-else-if="option.price_q > 0" class="text-xs tabular-nums text-muted-foreground">
                {{ optionPriceLabel(option.price_q) }}
              </span>
            </NuxtButton>
          </div>
        </fieldset>
      </div>

      <div class="flex min-w-0 items-baseline justify-between gap-2 border-t pt-3">
        <span class="text-sm text-muted-foreground">Total</span>
        <strong class="text-3xl tabular-nums" data-testid="product-options-total">{{ formatBRL(totalQ) }}</strong>
      </div>

      <div class="grid min-w-0 grid-cols-2 gap-2">
        <UiButton variant="outline" size="lg" class="h-14 min-w-0" data-role="back" @click="emit('cancel')">Voltar</UiButton>
        <UiButton size="lg" class="h-14 min-w-0" :disabled="!valid" data-role="confirm" @click="confirm">Lançar</UiButton>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
