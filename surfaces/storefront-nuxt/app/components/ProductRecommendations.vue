<script setup lang="ts">
import { useIntersectionObserver } from '@vueuse/core'
import { crossSellItems } from '~/presentation/product'
import type { ProductRecommendationsResponse } from '~/types/shopman'

const props = defineProps<{ sku: string }>()
const apiPath = useShopmanApiPath()
const target = ref<HTMLElement | null>(null)
const visible = ref(false)
const { data, status, error, execute, clear } = useFetch<ProductRecommendationsResponse>(
  () => apiPath(`/api/v1/storefront/products/${encodeURIComponent(props.sku)}/recommendations/`),
  { server: false, immediate: false, watch: false, credentials: 'include' }
)
const items = computed(() => data.value ? crossSellItems(data.value.recommendations) : [])
useIntersectionObserver(target, ([entry]) => {
  visible.value = !!entry?.isIntersecting
  if (visible.value && status.value === 'idle') void execute()
}, { rootMargin: '240px' })
watch(() => props.sku, () => {
  clear()
  if (visible.value) void execute()
})
</script>

<template>
  <div ref="target" class="mt-8 min-h-px" data-product-recommendations>
    <section v-if="items.length" data-product-cross-sell>
      <h2 class="shop-heading">{{ data?.recommendations.heading }}</h2>
      <div class="mt-1 grid grid-cols-1 gap-x-8 md:grid-cols-2">
        <ProductListItem
          v-for="item in items" :key="item.sku" :item="item" framed
          class="border-b last:border-b-0 md:[&:nth-last-child(2)]:border-b-0"
        />
      </div>
    </section>
    <div v-else-if="error" class="shop-muted">
      <p>Não foi possível carregar as sugestões.</p>
      <UiButton variant="link" @click="execute()">Tentar novamente</UiButton>
    </div>
  </div>
</template>
