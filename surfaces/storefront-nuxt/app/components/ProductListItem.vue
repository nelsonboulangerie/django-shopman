<script setup lang="ts">
import { tileBadge } from '~/presentation/menu'
import type { CatalogItemProjection, ProductMutationMeta } from '~/types/shopman'
import { compactUnitWeightLabel } from '~/utils/display'

const props = withDefaults(defineProps<{
  item: CatalogItemProjection
  // Moldura vintage na miniatura. Chamadores podem desligar explicitamente quando
  // a foto não for tratada como foto de produto.
  framed?: boolean
}>(), {
  framed: true
})

const { qtyForSku } = useCartState()
const meta = computed<ProductMutationMeta>(() => ({
  sku: props.item.sku,
  name: props.item.name,
  price_q: props.item.base_price_q,
  price_display: props.item.price_display,
  image_url: props.item.image_url
}))
const currentQty = computed(() => qtyForSku(props.item.sku))
const badge = computed(() => tileBadge(props.item))
</script>

<template>
  <article class="group/product-list relative flex min-w-0 items-stretch gap-3 py-3" data-product-list-item>
    <NuxtLink
      :to="`/produto/${encodeURIComponent(item.sku)}`"
      class="absolute inset-0 z-0 rounded-md"
      :aria-label="`Ver detalhes de ${item.name}`"
    />

    <div class="min-w-0 flex-1 self-center">
      <h3 class="shop-item-title line-clamp-2">{{ item.name }}</h3>
      <p v-if="item.short_description" class="mt-2 line-clamp-2 shop-meta">
        {{ item.short_description }}
      </p>
      <UiBadge v-if="badge && item.availability !== 'unavailable'" :variant="badge.variant" class="mt-2 font-normal">{{ badge.label }}</UiBadge>
      <DietaryWarningBadges :warnings="item.dietary_warnings" class="mt-2" />
      <p class="mt-2 flex flex-wrap items-baseline gap-x-2">
        <span v-if="item.original_price_display" class="shop-meta line-through">{{ item.original_price_display }}</span>
        <span class="shop-price">{{ item.price_display }}</span>
        <span v-if="item.unit_weight_label" class="shop-meta">{{ compactUnitWeightLabel(item.unit_weight_label) }}</span>
      </p>
    </div>

    <div class="pointer-events-none relative shrink-0 self-start" :class="framed ? 'shop-photo-outset-sm' : ''">
      <div :class="framed ? 'drop-shadow-md transition-transform duration-200 group-hover/product-list:-rotate-1 motion-reduce:group-hover/product-list:rotate-0' : ''">
        <div :class="framed ? 'shop-photo-frame shop-photo-frame-sm' : ''">
          <div :class="framed ? 'shop-photo-outset-mat-sm' : ''">
            <div
              class="size-28 overflow-hidden bg-muted"
              :class="framed ? '' : 'rounded-lg'"
            >
              <!-- A sépia (indisponível) vai SÓ na foto, nunca no <div> com a moldura —
                   senão o filtro amarela a borda branca. -->
              <img
                v-if="item.image_url"
                :src="item.image_url"
                :alt="item.name"
                loading="lazy"
                decoding="async"
                class="size-full object-cover"
                :class="item.availability === 'unavailable' ? 'shop-photo-unavailable' : ''"
              >
              <ProductImageFallback
                v-else
                :color="item.category_color"
                :icon="item.category_icon"
                :sku="item.sku"
                fallback-icon="lucide:croissant"
                icon-class="size-6"
              />
            </div>
          </div>
        </div>
      </div>
      <!-- Indisponível: etiqueta de VIDRO translúcida em tokens da marca (cream + marrom),
           harmonizando com a foto em sépia. Centralizada no topo, descolada da borda. -->
      <div
        v-if="item.availability === 'unavailable'"
        class="absolute z-10 flex justify-center"
        :class="framed ? 'shop-photo-control-top-sm' : 'inset-x-0 top-3'"
      >
        <UiBadge class="max-w-full border-transparent bg-background/75 font-normal text-foreground shadow-sm backdrop-blur-sm">Indisponível</UiBadge>
      </div>
      <!-- Notificável: pill "Me avise"/"Anotado" ocupa TODA a largura da foto (centrado),
           no rodapé — sem extravasar. -->
      <div
        v-if="item.is_notifiable"
        class="pointer-events-auto absolute z-10"
        :class="framed ? 'shop-photo-control-pill-sm' : 'inset-x-1 bottom-1'"
      >
        <StockNotifyButton
          :sku="item.sku"
          :name="item.name"
          :subscribed="item.is_notify_subscribed"
          pill
        />
      </div>
      <!-- Disponível: "+"/pílula de quantidade na quina. -->
      <div
        v-else-if="item.availability !== 'unavailable'"
        class="pointer-events-auto absolute z-10"
        :class="framed ? 'shop-photo-control-bottom-sm' : 'bottom-1 right-1'"
      >
        <CartQuantityAction
          :meta="meta"
          :qty="currentQty"
          :disabled="!item.can_add_to_cart"
          :max-qty="item.available_qty"
          compact
          add-icon-only
        />
      </div>
    </div>
  </article>
</template>
