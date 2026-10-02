<script setup lang="ts">
// Tile do cartão de escolha: produtos com o mesmo `choice_group` (dado do Admin)
// num tile só, que abre a escolha. Cada opção é o tile do próprio produto
// (PosProductTile): tocar lança aquele SKU pelo mesmo `add` e fecha a escolha.
import type { POSCartItem, POSProductProjection } from "~/types/pos";
import type { POSChoiceGroup } from "~/presentation/catalog";
import { cartQtyForSku, productFallbackIcon, productFallbackStyle } from "~/presentation/catalog";

const props = defineProps<{
  group: POSChoiceGroup;
  cartItems: POSCartItem[];
}>();

const emit = defineEmits<{ add: [POSProductProjection] }>();

const open = ref(false);
const qty = computed(() => props.group.options.reduce((total, option) => total + cartQtyForSku(props.cartItems, option.sku), 0));
const cover = computed(() => props.group.cover);
const hasImage = computed(() => Boolean(cover.value.image_url?.trim()));
const fallbackStyle = computed(() => productFallbackStyle(cover.value));
const fallbackIcon = computed(() => productFallbackIcon(cover.value));

function choose(product: POSProductProjection) {
  open.value = false;
  emit("add", product);
}
</script>

<template>
  <UiCard
    as="button"
    type="button"
    class="group relative overflow-hidden rounded-md p-0 text-left shadow-none transition hover:border-primary/50 active:translate-y-px"
    :class="[
      qty > 0 ? 'border-primary' : '',
      group.allBlocked ? 'cursor-not-allowed opacity-50 hover:border-border hover:shadow-none active:translate-y-0' : '',
    ]"
    :disabled="group.allBlocked"
    :aria-label="`${group.name}: escolher entre ${group.options.length} opções`"
    data-pos-choice-group
    @click="open = true"
  >
    <div class="relative aspect-[4/3] w-full overflow-hidden">
      <img v-if="hasImage" :src="cover.image_url" :alt="group.name" loading="lazy" class="size-full object-cover" />
      <div v-else class="pos-tile-fallback grid size-full place-items-center" :style="fallbackStyle" aria-hidden="true">
        <Icon :name="fallbackIcon" class="size-8" />
      </div>

      <UiBadge v-if="qty > 0" class="absolute right-1.5 top-1.5 tabular-nums shadow-sm">{{ qty }}x</UiBadge>
      <span
        class="absolute left-1.5 top-1.5 inline-flex items-center gap-1 rounded-full bg-background/85 px-2 py-0.5 text-xs font-semibold shadow-sm"
      >
        <Icon name="lucide:layers" class="size-3.5" />
        {{ group.options.length }} opções
      </span>
      <span
        v-if="group.allBlocked"
        class="absolute inset-x-0 bottom-0 bg-foreground/70 py-0.5 text-center text-xs font-semibold uppercase tracking-wide text-background"
      >
        Esgotado
      </span>
    </div>

    <div class="grid gap-0.5 px-2.5 py-1.5">
      <p class="line-clamp-2 text-sm font-semibold leading-tight" :title="group.name">{{ group.name }}</p>
      <strong class="text-base tabular-nums">{{ group.priceLabel }}</strong>
    </div>
  </UiCard>

  <UiDialog v-model:open="open">
    <UiDialogContent class="sm:max-w-2xl" data-pos-choice-group-dialog>
      <UiDialogHeader>
        <UiDialogTitle>{{ group.name }}</UiDialogTitle>
        <UiDialogDescription>Toque no produto para lançar no pedido.</UiDialogDescription>
      </UiDialogHeader>
      <p v-if="group.label" class="text-sm font-semibold" data-pos-choice-group-label>{{ group.label }}</p>
      <div class="grid grid-cols-2 gap-2.5 sm:grid-cols-3" :aria-label="group.label || undefined">
        <PosProductTile
          v-for="option in group.options"
          :key="option.sku"
          :product="option"
          :qty="cartQtyForSku(cartItems, option.sku)"
          :disabled="option.sold_out"
          @add="choose"
        />
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
