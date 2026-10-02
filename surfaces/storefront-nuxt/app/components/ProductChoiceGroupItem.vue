<script setup lang="ts">
// Cartão de escolha do cardápio: produtos parecidos (mesmo `choice_group`, dado do
// Admin) num cartão só, que abre a escolha numa folha. Cada opção da folha é o card
// do próprio SKU (ProductListItem): preço, disponibilidade, "Me avise" e sacola são
// os de sempre. O cartão só resume, e diz "Indisponível" apenas quando nenhuma
// opção pode ser pedida.
import type { ChoiceGroupCard } from '~/presentation/menu'

const props = withDefaults(defineProps<{
  group: ChoiceGroupCard
  pending?: boolean
  framed?: boolean
}>(), {
  framed: true,
  pending: false
})

const open = ref(false)
const { qtyForSku } = useCartState()
const qtyInCart = computed(() => props.group.options.reduce((total, option) => total + qtyForSku(option.sku), 0))
const cover = computed(() => props.group.cover)
</script>

<template>
  <article class="group/product-list relative flex min-w-0 items-stretch gap-3 py-3" data-product-choice-group>
    <UiButton
      variant="ghost"
      class="absolute inset-0 z-0 h-auto rounded-md p-0 hover:bg-transparent"
      :aria-label="`Escolher entre ${group.summary}`"
      data-product-choice-group-open
      @click="open = true"
    />

    <div class="pointer-events-none min-w-0 flex-1 self-center">
      <h3 class="shop-item-title line-clamp-2">{{ group.name }}</h3>
      <p class="mt-2 line-clamp-2 shop-meta">{{ group.summary }}</p>
      <div v-if="pending" class="mt-2" aria-label="Confirmando preço e disponibilidade">
        <UiSkeleton class="h-5 w-24" />
      </div>
      <p v-else class="mt-2 flex flex-wrap items-baseline gap-x-2">
        <span class="shop-price">{{ group.priceLabel }}</span>
        <span v-if="qtyInCart" class="shop-meta">{{ formatCount(qtyInCart, 'na sacola', 'na sacola') }}</span>
      </p>
    </div>

    <div class="pointer-events-none relative shrink-0 self-start" :class="framed ? 'shop-photo-outset-sm' : ''">
      <div :class="framed ? 'drop-shadow-md transition-transform duration-200 group-hover/product-list:-rotate-1 motion-reduce:group-hover/product-list:rotate-0' : ''">
        <div :class="framed ? 'shop-photo-frame shop-photo-frame-sm' : ''">
          <div :class="framed ? 'shop-photo-outset-mat-sm' : ''">
            <div class="size-28 overflow-hidden bg-muted" :class="framed ? '' : 'rounded-lg'">
              <img
                v-if="cover.image_url"
                :src="cover.image_url"
                :alt="group.name"
                loading="lazy"
                decoding="async"
                class="size-full object-cover"
                :class="!pending && group.allUnavailable ? 'shop-photo-unavailable' : ''"
              >
              <ProductImageFallback
                v-else
                :color="cover.category_color"
                :icon="cover.category_icon"
                :sku="cover.sku"
                fallback-icon="lucide:croissant"
                icon-class="size-6"
              />
            </div>
          </div>
        </div>
      </div>
      <div
        v-if="!pending && group.allUnavailable"
        class="absolute z-10 flex justify-center"
        :class="framed ? 'shop-photo-control-top-sm' : 'inset-x-0 top-3'"
      >
        <UiBadge class="max-w-full border-transparent bg-background/75 font-normal text-foreground shadow-sm backdrop-blur-sm">Indisponível</UiBadge>
      </div>
      <div
        v-else-if="!pending"
        class="absolute z-10"
        :class="framed ? 'shop-photo-control-bottom-sm' : 'bottom-1 right-1'"
      >
        <span class="inline-flex h-8 items-center gap-1 rounded-full bg-cta px-3 text-sm font-semibold text-cta-foreground shadow-sm">
          Escolher
          <Icon name="lucide:chevron-down" class="size-4" />
        </span>
      </div>
    </div>

    <BottomSheet
      v-model:open="open"
      max-width="md"
      :title="group.name"
      description="Toque no + para pôr na sacola, ou no nome para ver os detalhes."
      data-product-choice-group-sheet
    >
      <div class="grid grid-cols-1 px-4 pb-4">
        <ProductListItem
          v-for="option in group.options"
          :key="option.sku"
          :item="option"
          :pending="pending"
          :framed="framed"
          class="border-b last:border-b-0"
        />
      </div>
    </BottomSheet>
  </article>
</template>
