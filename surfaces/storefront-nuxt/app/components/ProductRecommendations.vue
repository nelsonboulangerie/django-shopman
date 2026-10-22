<script setup lang="ts">
import { useIntersectionObserver } from '@vueuse/core'
import { CROSS_SELL_LIMIT, RECOMMENDATIONS_ROOT_MARGIN, crossSellItems } from '~/presentation/product'
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
// Só depois que o servidor respondeu (ou falhou) o placeholder sai de cena.
const settled = computed(() => status.value === 'success' || status.value === 'error')
const loading = computed(() => status.value === 'pending')

// A altura que o placeholder ocupava fica no contêiner para sempre.
//
// Reservar e depois devolver a altura não resolve: a reserva tem o TAMANHO DO
// TETO do rail (CROSS_SELL_LIMIT cards), e a resposta pode trazer menos. Com 1
// card, a seção encolhia ~590 px e PUXAVA para cima (para dentro da viewport)
// tudo o que estava abaixo dela, footer incluído. O CLS conta os dois sentidos,
// então o critério não é "não crescer": é "nada abaixo se mover". O contêiner
// mantém a altura reservada enquanto existir, mesmo vazio.
//
// Medido antes de trocar o DOM: o watcher roda com flush 'pre', então o
// placeholder ainda está montado e a altura é a real do breakpoint atual.
const reservedHeight = ref<number | null>(null)
watch(settled, (isSettled, wasSettled) => {
  if (!isSettled || wasSettled) return
  const measured = Math.round(target.value?.getBoundingClientRect().height ?? 0)
  if (measured > 0) reservedHeight.value = measured
})
useIntersectionObserver(target, ([entry]) => {
  visible.value = !!entry?.isIntersecting
  if (visible.value && status.value === 'idle') void execute()
}, { rootMargin: RECOMMENDATIONS_ROOT_MARGIN })
watch(() => props.sku, () => {
  clear()
  if (visible.value) void execute()
})
</script>

<template>
  <div
    ref="target"
    class="mt-8"
    :style="reservedHeight ? { minHeight: `${reservedHeight}px` } : undefined"
    data-product-recommendations
  >
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
    <!-- A reserva. Desenha o TETO do rail: mesma grade, mesma moldura, mesmas
         linhas de texto que um card cheio, com CROSS_SELL_LIMIT cards. Existe
         desde o SSR (não a partir da resposta), senão a reserva chegaria tarde
         demais e moveria a página na cara do usuário. -->
    <div
      v-else-if="!settled"
      data-product-recommendations-skeleton
      :role="loading ? 'status' : undefined"
      :aria-live="loading ? 'polite' : undefined"
      :aria-busy="loading ? 'true' : undefined"
      :aria-hidden="loading ? undefined : 'true'"
    >
      <p v-if="loading" class="sr-only">Carregando sugestões.</p>
      <UiSkeleton class="h-6 w-40" />
      <div class="mt-1 grid grid-cols-1 gap-x-8 md:grid-cols-2">
        <div
          v-for="slot in CROSS_SELL_LIMIT" :key="slot"
          class="flex min-w-0 items-stretch gap-3 border-b py-3 last:border-b-0 md:[&:nth-last-child(2)]:border-b-0"
          data-product-recommendations-skeleton-card
        >
          <div class="min-w-0 flex-1 self-center">
            <UiSkeleton class="h-6 w-3/4" />
            <UiSkeleton class="mt-2 h-5 w-2/3" />
            <UiSkeleton class="mt-2 h-4 w-full" />
            <UiSkeleton class="mt-2 h-4 w-3/4" />
            <UiSkeleton class="mt-2 h-5 w-20" />
            <UiSkeleton class="mt-2 h-5 w-24" />
          </div>
          <UiSkeleton class="size-28 shrink-0 rounded-lg" />
        </div>
      </div>
    </div>
  </div>
</template>
