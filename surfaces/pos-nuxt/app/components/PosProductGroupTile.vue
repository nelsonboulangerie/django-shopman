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
  /** Toque: a faixa mais alta, igual ao tile do produto. */
  touch?: boolean;
}>();

const emit = defineEmits<{ add: [POSProductProjection] }>();

const open = ref(false);
const qty = computed(() => props.group.options.reduce((total, option) => total + cartQtyForSku(props.cartItems, option.sku), 0));
const cover = computed(() => props.group.cover);
const hasImage = computed(() => Boolean(cover.value.image_url?.trim()));
const imageBroken = ref(false);
const showImage = computed(() => hasImage.value && !imageBroken.value);
const fallbackStyle = computed(() => productFallbackStyle(cover.value));
const fallbackIcon = computed(() => productFallbackIcon(cover.value));

function choose(product: POSProductProjection) {
  open.value = false;
  emit("add", product);
}
</script>

<template>
  <!-- Cartão de escolha no desenho do tile da v4: a mesma faixa de 92 px, a pílula
       "N opções" e a sombra de pilha que diz "tem mais de um aqui". -->
  <NuxtButton
    color="neutral"
    variant="ghost"
    class="group relative flex flex-col overflow-hidden rounded-lg border bg-card text-left text-card-foreground shadow-[4px_4px_0_-1px_var(--card),4px_4px_0_0_var(--border)] transition hover:border-primary/50 active:translate-y-px disabled:cursor-not-allowed disabled:hover:border-border disabled:active:translate-y-0 items-stretch gap-0 p-0 font-normal"
    :class="qty > 0 ? 'border-primary' : 'border-border'"
    :disabled="group.allBlocked"
    :aria-label="`${group.name}: escolher entre ${group.options.length} opções`"
    data-pos-choice-group
    @click="open = true"
  >
    <div class="relative w-full shrink-0 overflow-hidden" :class="[touch ? 'h-[108px]' : 'h-[92px]', group.allBlocked ? 'opacity-55' : '']">
      <img v-if="showImage" :src="cover.image_url" :alt="group.name" loading="lazy" class="size-full object-cover" @error="imageBroken = true" />
      <div v-else class="pos-tile-fallback grid size-full place-items-center" :style="fallbackStyle" aria-hidden="true">
        <Icon :name="fallbackIcon" class="size-9" />
      </div>

      <span
        class="absolute top-2 inline-flex h-6 items-center gap-1 rounded-full bg-card/90 px-2 op-micro font-semibold"
        :class="qty > 0 ? 'left-2' : 'right-2'"
      >
        <Icon name="lucide:layers" class="size-3.5" />
        {{ group.options.length }} opções
      </span>
      <span
        v-if="qty > 0"
        class="absolute right-2 top-2 grid h-7 min-w-7 place-items-center rounded-full bg-primary px-1.5 op-label font-bold tabular-nums text-primary-foreground shadow-sm"
        :aria-label="`${qty} no pedido`"
      >{{ qty }}</span>
    </div>

    <div class="flex min-w-0 flex-col gap-0.5 px-3 py-2">
      <p class="truncate op-label font-semibold" :class="group.allBlocked ? 'text-muted-foreground' : ''" :title="group.name">{{ group.name }}</p>
      <span class="flex min-w-0 items-center justify-between gap-1.5">
        <strong class="op-title tnum whitespace-nowrap" :class="group.allBlocked ? 'text-muted-foreground' : ''">{{ group.priceLabel }}</strong>
        <span
          v-if="group.allBlocked"
          class="inline-flex h-6 shrink-0 items-center gap-1 rounded-full bg-muted px-1.5 op-micro font-semibold text-muted-foreground"
        >
          <span class="size-1.5 rounded-full bg-muted-foreground" aria-hidden="true" />
          Esgotado
        </span>
      </span>
    </div>
  </NuxtButton>

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
