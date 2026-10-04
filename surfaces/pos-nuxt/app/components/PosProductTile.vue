<script setup lang="ts">
import type { POSProductProjection } from "~/types/pos";
import { productFallbackIcon, productFallbackStyle } from "~/presentation/catalog";
import { productBlockedLabel } from "~/presentation/weighed";
import { hasOptionGroups } from "~/presentation/productOptions";

const props = defineProps<{
  product: POSProductProjection;
  qty: number;
  disabled?: boolean;
}>();

defineEmits<{
  add: [POSProductProjection];
}>();

// Inerte com selo: esgotado, ou sem preço no catálogo (nenhum canal vende preço zero).
const blockedLabel = computed(() => productBlockedLabel(props.product) || (props.disabled ? "Esgotado" : ""));
const inert = computed(() => Boolean(blockedLabel.value));
// Com escolhas (sabor, adicionais), o toque abre o diálogo em vez de somar 1.
const opensChoice = computed(() => hasOptionGroups(props.product));

const hasImage = computed(() => Boolean(props.product.image_url?.trim()));
// Foto que não carrega (arquivo sumiu, mídia fora do ar) volta ao desenho da coleção.
const imageBroken = ref(false);
watch(() => props.product.image_url, () => { imageBroken.value = false; });
const showImage = computed(() => hasImage.value && !imageBroken.value);

// Fallback de produto sem foto: fundo na cor da coleção primária + ícone
// Lucide genérico da categoria + SKU (presentation/catalog).
const fallbackStyle = computed(() => productFallbackStyle(props.product));
const fallbackIcon = computed(() => productFallbackIcon(props.product));
</script>

<template>
  <!-- Tile da v4 (`pos-sale4.html`): faixa de 92 px na cor da coleção com o ícone e o
       SKU, nome e preço embaixo. Com foto, a foto ocupa a faixa; se ela não carregar,
       volta o desenho da coleção (antes ficava o texto alternativo quebrado). -->
  <button
    type="button"
    class="group relative flex flex-col overflow-hidden rounded-lg border bg-card text-left text-card-foreground transition hover:border-primary/50 active:translate-y-px disabled:cursor-not-allowed disabled:hover:border-border disabled:active:translate-y-0"
    :class="[
      qty > 0 ? 'border-primary' : 'border-border',
      opensChoice ? 'shadow-[4px_4px_0_-1px_var(--card),4px_4px_0_0_var(--border)]' : '',
    ]"
    :disabled="inert"
    :aria-label="opensChoice ? `${product.name}: abre as escolhas` : undefined"
    :data-pos-product-options="opensChoice ? '' : undefined"
    data-pos-product
    @click="$emit('add', product)"
  >
    <div class="relative h-[92px] w-full shrink-0 overflow-hidden" :class="inert ? 'opacity-55' : ''">
      <img
        v-if="showImage"
        :src="product.image_url"
        :alt="product.name"
        loading="lazy"
        class="size-full object-cover"
        @error="imageBroken = true"
      />
      <div
        v-else
        class="pos-tile-fallback grid size-full place-items-center"
        :style="fallbackStyle"
        aria-hidden="true"
      >
        <Icon :name="fallbackIcon" class="size-9" />
        <span class="absolute bottom-1.5 left-2 max-w-[calc(100%-1rem)] truncate font-mono op-eyebrow font-normal tracking-wide">{{ product.sku }}</span>
      </div>

      <span
        v-if="opensChoice"
        class="absolute top-2 inline-flex h-6 items-center gap-1 rounded-full bg-card/90 px-2 op-micro font-semibold"
        :class="qty > 0 ? 'left-2' : 'right-2'"
      >
        <Icon name="lucide:layers" class="size-3.5" />
        Escolhas
      </span>
      <span
        v-if="qty > 0"
        class="absolute right-2 top-2 grid h-7 min-w-7 place-items-center rounded-full bg-primary px-1.5 op-label font-bold tabular-nums text-primary-foreground shadow-sm"
        :aria-label="`${qty} no pedido`"
      >
        {{ qty }}
      </span>
    </div>

    <div class="flex min-w-0 flex-col gap-0.5 px-3 py-2">
      <!-- Nome longo (a mercearia: "Creme de Parmesão Kraeuterkaese Pomerode
           90g") corta numa linha; o nome inteiro fica no `title`. -->
      <p class="truncate op-label font-semibold" :class="inert ? 'text-muted-foreground' : ''" :title="product.name">{{ product.name }}</p>
      <span class="flex min-w-0 items-center justify-between gap-1.5">
        <strong class="op-title tnum whitespace-nowrap" :class="inert ? 'text-muted-foreground' : ''">{{ product.price_display }}</strong>
        <!-- Esgotado: a pílula ao lado do preço; o tile fica visível porém inerte
             (sumir da grade faria o operador procurar um botão que "sumiu"). Sem
             preço, quem diz é a linha do preço ("Sem preço"). -->
        <span
          v-if="blockedLabel === 'Esgotado'"
          class="inline-flex h-6 shrink-0 items-center gap-1 rounded-full bg-muted px-1.5 op-micro font-semibold text-muted-foreground"
        >
          <span class="size-1.5 rounded-full bg-muted-foreground" aria-hidden="true" />
          Esgotado
        </span>
      </span>
    </div>
  </button>
</template>
