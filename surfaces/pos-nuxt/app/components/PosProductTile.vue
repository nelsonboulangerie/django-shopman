<script setup lang="ts">
import type { POSProductProjection } from "~/types/pos";
import { productFallbackIcon, productFallbackStyle } from "~/presentation/catalog";

const props = defineProps<{
  product: POSProductProjection;
  qty: number;
  disabled?: boolean;
}>();

defineEmits<{
  add: [POSProductProjection];
}>();

const hasImage = computed(() => Boolean(props.product.image_url?.trim()));

// Fallback de produto sem foto: fundo na cor da coleção primária + ícone
// Lucide genérico da categoria + SKU (presentation/catalog).
const fallbackStyle = computed(() => productFallbackStyle(props.product));
const fallbackIcon = computed(() => productFallbackIcon(props.product));
</script>

<template>
  <UiCard
    as="button"
    type="button"
    class="group relative overflow-hidden rounded-md p-0 text-left shadow-none transition hover:border-primary/50 active:translate-y-px"
    :class="[
      qty > 0 ? 'border-primary' : '',
      disabled ? 'cursor-not-allowed opacity-50 hover:border-border hover:shadow-none active:translate-y-0' : '',
    ]"
    :disabled="disabled"
    @click="$emit('add', product)"
  >
    <div class="relative aspect-[4/3] w-full overflow-hidden">
      <img
        v-if="hasImage"
        :src="product.image_url"
        :alt="product.name"
        loading="lazy"
        class="size-full object-cover"
      />
      <div
        v-else
        class="pos-tile-fallback grid size-full place-items-center"
        :style="fallbackStyle"
        aria-hidden="true"
      >
        <div class="flex flex-col items-center gap-1">
          <Icon :name="fallbackIcon" class="size-8" />
          <span class="font-mono text-xs uppercase tracking-widest opacity-80">{{ product.sku }}</span>
        </div>
      </div>

      <UiBadge
        v-if="qty > 0"
        class="absolute right-1.5 top-1.5 tabular-nums shadow-sm"
      >
        {{ qty }}x
      </UiBadge>
      <!-- Esgotado: selo por cima da imagem; o tile fica visível porém inerte
           (sumir da grade faria o operador procurar um botão que "sumiu"). -->
      <span
        v-if="disabled"
        class="absolute inset-x-0 bottom-0 bg-foreground/70 py-0.5 text-center text-xs font-semibold uppercase tracking-wide text-background"
      >
        Esgotado
      </span>
    </div>

    <div class="grid gap-0.5 px-2.5 py-1.5">
      <p class="line-clamp-2 text-sm font-semibold leading-tight">{{ product.name }}</p>
      <strong class="text-base tabular-nums">{{ product.price_display }}</strong>
    </div>
  </UiCard>
</template>
