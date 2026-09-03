<script setup lang="ts">
import { tileBadge } from '~/presentation/menu'
import { crossSellItems, detailDescription, galleryImages, nutritionTable } from '~/presentation/product'
import { absoluteImage, breadcrumbJsonLd, metaDescription, priceFromQ, productJsonLd } from '~/presentation/seo'
import type { ProductMutationMeta, ProductResponse } from '~/types/shopman'
import { compactUnitWeightLabel } from '~/utils/display'

const route = useRoute()
const apiPath = useShopmanApiPath()
const requestUrl = useRequestURL()
const session = useShopSession()
const sku = computed(() => String(route.params.sku || ''))
const { setFromServer, qtyForSku } = useCartState()

const { data, pending, error, refresh } = await useFetch<ProductResponse>(
  () => apiPath(`/api/v1/storefront/products/${encodeURIComponent(sku.value)}/`),
  { credentials: 'include' }
)

// SKU inexistente: 404 de verdade (SSR responde 404 + noindex via error.vue),
// não uma página-fantasma 200 indexável. Falhas de rede seguem no retry inline.
if (error.value?.statusCode === 404) {
  throw createError({ statusCode: 404, statusMessage: 'Produto não encontrado', fatal: true })
}

watch(() => data.value?.cart, cart => {
  setFromServer(cart)
}, { immediate: true })

const product = computed(() => data.value?.product || null)
const meta = computed<ProductMutationMeta | null>(() => product.value
  ? {
      sku: product.value.sku,
      name: product.value.name,
      price_q: product.value.base_price_q,
      price_display: product.value.price_display,
      image_url: product.value.image_url
    }
  : null)
const currentQty = computed(() => product.value ? qtyForSku(product.value.sku) : 0)
const badge = computed(() => product.value ? tileBadge(product.value) : null)
// O cliente lê o ESTADO, nunca o motivo: esgotado, pausado pela casa ou fora do
// canal chegam à tela como o mesmo "Indisponível". O porquê é assunto da casa
// (AVAILABILITY-PLAN §2) e vive nas superfícies de operador.
const unavailableReason = computed(() => {
  if (!product.value || product.value.can_add_to_cart) return ''
  return product.value.availability_label || 'Este item não está disponível agora.'
})
const longDescription = computed(() => product.value ? detailDescription(product.value) : '')
// Carrossel: lista vazia = foto única (moldura estática de sempre). A principal
// (image_url) abre o carrossel; o índice segue o scroll real do slider.
const carouselImages = computed(() => product.value ? galleryImages(product.value) : [])
const sliderEl = ref<HTMLElement | null>(null)
const slideIndex = ref(0)
watch(sku, () => {
  slideIndex.value = 0
  sliderEl.value?.scrollTo({ left: 0, behavior: 'instant' })
})
function onSliderScroll () {
  const el = sliderEl.value
  if (!el || !el.clientWidth) return
  slideIndex.value = Math.min(carouselImages.value.length - 1, Math.max(0, Math.round(el.scrollLeft / el.clientWidth)))
}
function goToSlide (index: number) {
  // Otimista: o ponto acende já no clique; o evento de scroll (a verdade do
  // gesto) corrige se a animação parar no meio. O scroll-smooth do container
  // anima — smooth é pedido, não garantia.
  slideIndex.value = Math.min(carouselImages.value.length - 1, Math.max(0, index))
  sliderEl.value?.scrollTo({ left: slideIndex.value * (sliderEl.value?.clientWidth || 0) })
}
const nutrition = computed(() => nutritionTable(product.value?.nutrition || null))
const crossSell = computed(() => product.value ? crossSellItems(product.value) : [])

const canonicalUrl = computed(() => `${requestUrl.origin}${route.path}`)
const ogImage = computed(() => absoluteImage(requestUrl.origin, product.value?.image_url))
const pageDescription = computed(() => metaDescription(product.value) || 'Produto')

useSeoMeta({
  title: () => product.value?.name || 'Produto',
  description: () => pageDescription.value,
  ogTitle: () => product.value?.name || 'Produto',
  ogDescription: () => pageDescription.value,
  ogUrl: () => canonicalUrl.value,
  ogImage: () => ogImage.value || undefined,
  twitterCard: 'summary_large_image',
  twitterTitle: () => product.value?.name || 'Produto',
  twitterDescription: () => pageDescription.value,
  twitterImage: () => ogImage.value || undefined
})

// og:type=product + product:price (cards do WhatsApp/Facebook) e canonical —
// via meta crua (TS-safe). JSON-LD Product/Offer + BreadcrumbList p/ rich results.
useHead({
  link: [{ rel: 'canonical', href: () => canonicalUrl.value }],
  meta: [
    { property: 'og:type', content: 'product' },
    { property: 'product:price:amount', content: () => priceFromQ(product.value?.base_price_q) },
    { property: 'product:price:currency', content: 'BRL' }
  ],
  script: () => product.value
    ? [
        {
          type: 'application/ld+json',
          innerHTML: JSON.stringify(productJsonLd({
            product: product.value,
            origin: requestUrl.origin,
            url: canonicalUrl.value,
            brandName: session.shop.value?.brand_name || ''
          }))
        },
        {
          type: 'application/ld+json',
          innerHTML: JSON.stringify(breadcrumbJsonLd([
            { name: 'Início', url: `${requestUrl.origin}/` },
            { name: 'Cardápio', url: `${requestUrl.origin}/menu` },
            { name: product.value.name, url: canonicalUrl.value }
          ]))
        }
      ]
    : []
})
</script>

<template>
  <main class="pb-6 pt-0 lg:pb-8">
    <!-- Breadcrumb full-width encostando na navbar. Mobile: sem respiro (a barra
         dourada encosta direto na foto full-bleed). Desktop: respiro (lg:mb-6)
         antes do card contido, no mesmo ritmo da tela de conta. -->
    <div v-if="product" class="shop-breadcrumb-bar lg:mb-6">
      <div class="shop-container py-2">
        <UiBreadcrumbs
          :items="[
            { label: 'Início', link: '/' },
            { label: 'Cardápio', link: '/menu' },
            { label: product.name }
          ]"
        />
      </div>
    </div>
    <div class="shop-container">
      <div v-if="pending" class="space-y-4">
        <UiSkeleton class="-mx-4 aspect-[4/3] rounded-none sm:-mx-6 lg:mx-0 lg:h-96 lg:w-1/2 lg:rounded-lg" />
        <UiSkeleton class="h-8 w-2/3" />
        <UiSkeleton class="h-4 w-full" />
        <UiSkeleton class="h-10 w-1/3" />
      </div>

      <UiAlert v-else-if="error" variant="destructive" class="mt-4">
        <UiAlertTitle>Não foi possível abrir este produto</UiAlertTitle>
        <UiAlertDescription>
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>Tivemos um percalço ao carregar. Tente de novo em instantes.</span>
            <UiButton size="sm" variant="outline" @click="refresh">Tentar de novo</UiButton>
          </div>
        </UiAlertDescription>
      </UiAlert>

      <template v-else-if="product && meta">
        <!-- Imagem emoldurada + informações num único card claro. -->
        <article class="-mx-4 overflow-hidden border-b bg-card sm:-mx-6 lg:mx-0 lg:grid lg:grid-cols-[minmax(0,1fr)_420px] lg:items-stretch lg:rounded-lg lg:border">
          <section class="shop-pdp-media-panel min-w-0 p-4 sm:p-6">
            <div class="drop-shadow-md transition-transform duration-200 hover:-rotate-1 motion-reduce:hover:rotate-0">
              <div class="shop-photo-frame">
                <div class="shop-photo-mat relative block bg-white">
                  <UiAspectRatio :ratio="4 / 3" class="overflow-hidden bg-muted">
                    <!-- Mais de uma foto: carrossel com swipe (scroll-snap); o
                         estado segue o scroll REAL, então gesto e setas nunca
                         divergem do que está na tela. -->
                    <div
                      v-if="carouselImages.length"
                      ref="sliderEl"
                      class="flex size-full snap-x snap-mandatory overflow-x-auto scroll-smooth [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
                      @scroll.passive="onSliderScroll"
                    >
                      <img
                        v-for="(image, index) in carouselImages"
                        :key="image"
                        :src="image"
                        :alt="`${product.name} — foto ${index + 1} de ${carouselImages.length}`"
                        class="size-full shrink-0 snap-center object-cover"
                        :class="product.availability === 'unavailable' ? 'shop-photo-unavailable' : ''"
                        :fetchpriority="index === 0 ? 'high' : undefined"
                        :loading="index === 0 ? undefined : 'lazy'"
                      >
                    </div>
                    <img
                      v-else-if="product.image_url"
                      :src="product.image_url"
                      :alt="product.name"
                      class="size-full object-cover"
                      :class="product.availability === 'unavailable' ? 'shop-photo-unavailable' : ''"
                      fetchpriority="high"
                    >
                    <ProductImageFallback
                      v-else
                      :color="product.category_color"
                      :icon="product.category_icon"
                      :sku="product.sku"
                      fallback-icon="lucide:croissant"
                      icon-class="size-10"
                    />
                    <!-- Indisponível: etiqueta de VIDRO translúcida em tokens da marca (cream +
                         marrom), harmonizando com a sépia, consistente com os cards. -->
                    <div v-if="product.availability === 'unavailable'" class="absolute bottom-3 left-3 z-10">
                      <UiBadge class="border-transparent bg-background/75 font-normal text-foreground shadow-sm backdrop-blur-sm">Indisponível</UiBadge>
                    </div>
                  </UiAspectRatio>
                  <template v-if="carouselImages.length">
                    <!-- Pontos SOBRE a foto, sem fundo (pedido do dono): brancos
                         com sombra para ler em qualquer foto. Zero altura no
                         fluxo — o vão foto→nome é o da PDP sem carrossel. -->
                    <div class="absolute inset-x-0 bottom-3 z-10 flex items-center justify-center gap-2">
                      <UiButton
                        v-for="(image, index) in carouselImages"
                        :key="image"
                        variant="ghost"
                        class="h-2 w-2 min-w-0 rounded-full p-0 shadow-[0_0_2px_rgba(0,0,0,0.6)]"
                        :class="index === slideIndex ? 'bg-white hover:bg-white' : 'bg-white/50 hover:bg-white/75'"
                        :aria-label="`Ir para a foto ${index + 1}`"
                        :aria-current="index === slideIndex"
                        @click="goToSlide(index)"
                      />
                    </div>
                    <UiButton
                      variant="ghost"
                      size="icon-sm"
                      icon="lucide:chevron-left"
                      class="absolute top-1/2 left-2 z-10 hidden -translate-y-1/2 rounded-full bg-background/75 shadow-sm backdrop-blur-sm hover:bg-background/90 lg:inline-flex"
                      :disabled="slideIndex === 0"
                      aria-label="Foto anterior"
                      @click="goToSlide(slideIndex - 1)"
                    />
                    <UiButton
                      variant="ghost"
                      size="icon-sm"
                      icon="lucide:chevron-right"
                      class="absolute top-1/2 right-2 z-10 hidden -translate-y-1/2 rounded-full bg-background/75 shadow-sm backdrop-blur-sm hover:bg-background/90 lg:inline-flex"
                      :disabled="slideIndex === carouselImages.length - 1"
                      aria-label="Próxima foto"
                      @click="goToSlide(slideIndex + 1)"
                    />
                  </template>
                </div>
              </div>
            </div>

          </section>

          <div class="min-w-0 p-4 sm:p-6">

            <div v-if="(badge && product.availability !== 'unavailable') || product.promotion_label" class="mb-2 flex flex-wrap gap-2">
              <UiBadge v-if="badge && product.availability !== 'unavailable'" :variant="badge.variant" class="font-normal">{{ badge.label }}</UiBadge>
              <UiBadge v-if="product.promotion_label" variant="default" class="font-normal">{{ product.promotion_label }}</UiBadge>
            </div>

            <div class="flex items-start justify-between gap-3">
              <h1 class="shop-title line-clamp-2">{{ product.name }}</h1>
              <FavoriteHeart :sku="product.sku" :name="product.name" :initial="product.is_favorite" class="-mr-1 shrink-0" />
            </div>
            <p class="mt-2 line-clamp-2 shop-muted">{{ product.short_description }}</p>
            <p v-if="longDescription" class="mt-2 shop-muted">{{ longDescription }}</p>
            <DietaryWarningBadges :warnings="product.dietary_warnings" class="mt-3" />

            <div class="mt-2 flex flex-wrap items-end justify-between gap-4">
              <div>
                <p v-if="product.original_price_display" class="shop-meta line-through">
                  {{ product.original_price_display }}
                </p>
                <div class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <p class="shop-price-strong">{{ product.price_display }}</p>
                  <p v-if="product.unit_weight_label" class="shop-meta">
                    {{ product.unit_weight_label }}
                  </p>
                </div>
              </div>
              <div class="hidden md:block">
                <StockNotifyButton v-if="product.is_notifiable" :sku="product.sku" :name="product.name" :subscribed="product.is_notify_subscribed" />
                <CartQuantityAction
                  v-else
                  :meta="meta"
                  :qty="currentQty"
                  :disabled="!product.can_add_to_cart"
                  :max-qty="product.available_qty ?? product.max_qty"
                  :add-label="product.can_add_to_cart ? 'Adicionar' : 'Indisponível'"
                />
                <p v-if="unavailableReason" class="mt-2 max-w-48 text-right shop-meta">{{ unavailableReason }}</p>
              </div>
            </div>

            <UiAccordion type="multiple" class="-mx-4 mt-6 border-t sm:-mx-6 lg:mx-0 [&_[data-slot=accordion-trigger]]:font-semibold sm:[&_[data-slot=accordion-trigger]]:px-6 lg:[&_[data-slot=accordion-trigger]]:px-4 [&_[data-slot=accordion-content]>div]:px-8 [&_[data-slot=accordion-content]>div]:pt-3 [&_[data-slot=accordion-content]>div]:pb-6 sm:[&_[data-slot=accordion-content]>div]:px-10 lg:[&_[data-slot=accordion-content]>div]:px-4 lg:[&_[data-slot=accordion-content]>div]:pt-2 lg:[&_[data-slot=accordion-content]>div]:pb-4">
              <UiAccordionItem v-if="product.components.length" value="components">
                <UiAccordionTrigger>Itens do combo</UiAccordionTrigger>
                <UiAccordionContent>
                  <div v-for="component in product.components" :key="component.sku" class="flex justify-between gap-3 py-1 shop-body">
                    <span>{{ component.name }}</span>
                    <span>{{ component.qty_display }}</span>
                  </div>
                </UiAccordionContent>
              </UiAccordionItem>
              <UiAccordionItem v-if="product.allergen?.has_any || product.ingredients_text || product.trace_notice" value="ingredients">
                <UiAccordionTrigger>Ingredientes e restrições</UiAccordionTrigger>
                <UiAccordionContent>
                  <div class="space-y-2 shop-muted">
                    <p v-if="product.ingredients_text">{{ product.ingredients_text }}</p>
                    <p v-if="product.allergen?.allergens.length">Alérgenos: {{ product.allergen.allergens.join(', ') }}</p>
                    <p v-if="product.allergen?.dietary_info.length">Dieta: {{ product.allergen.dietary_info.join(', ') }}</p>
                    <p v-if="product.trace_notice">{{ product.trace_notice }}</p>
                  </div>
                </UiAccordionContent>
              </UiAccordionItem>
              <UiAccordionItem v-if="nutrition" value="nutrition">
                <UiAccordionTrigger>Nutricional</UiAccordionTrigger>
                <UiAccordionContent>
                  <div class="space-y-1 shop-body">
                    <p v-if="nutrition.serving" class="pb-1 shop-meta">Porção: {{ nutrition.serving }}</p>
                    <div
                      v-for="row in nutrition.rows"
                      :key="row.label"
                      class="flex items-baseline justify-between gap-3 border-b border-border/60 py-1.5 last:border-b-0"
                    >
                      <span class="text-muted-foreground">{{ row.label }}</span>
                      <span class="text-right">
                        <span class="shop-price">{{ row.value }}</span>
                        <span v-if="row.pdv != null" class="ml-2 shop-meta tabular-nums">{{ row.pdv }}% VD</span>
                      </span>
                    </div>
                  </div>
                </UiAccordionContent>
              </UiAccordionItem>
              <UiAccordionItem v-if="product.conservation?.has_any || product.unit_weight_label || product.approx_dimensions_label" value="care">
                <UiAccordionTrigger>Conservação</UiAccordionTrigger>
                <UiAccordionContent>
                  <div class="space-y-2 shop-muted">
                    <p v-if="product.conservation?.shelf_life_label">{{ product.conservation.shelf_life_label }}</p>
                    <p v-if="product.conservation?.storage_tip">{{ product.conservation.storage_tip }}</p>
                    <p v-if="product.unit_weight_label">Peso: {{ product.unit_weight_label }}</p>
                    <p v-if="product.approx_dimensions_label">Dimensões: {{ product.approx_dimensions_label }}</p>
                  </div>
                </UiAccordionContent>
              </UiAccordionItem>
            </UiAccordion>
          </div>
        </article>

        <section v-if="crossSell.length" class="mt-8" data-product-cross-sell>
          <h2 class="shop-heading">{{ product?.cross_sell_heading || 'Você também pode gostar' }}</h2>
          <div class="mt-1 grid grid-cols-1 gap-x-8 md:grid-cols-2">
            <ProductListItem
              v-for="item in crossSell"
              :key="item.sku"
              :item="item"
              framed
              class="border-b last:border-b-0 md:[&:nth-last-child(2)]:border-b-0"
            />
          </div>
        </section>

        <div
          class="sticky bottom-20 z-30 mt-4 rounded-lg border border-ink bg-ink p-3 text-ink-foreground shadow-lg md:hidden"
        >
          <div class="flex items-center justify-between gap-3">
            <div class="min-w-0">
              <p class="truncate shop-body">{{ product.name }}</p>
              <p class="shop-price-strong text-ink-foreground">{{ product.price_display }}</p>
              <p v-if="product.unit_weight_label" class="text-xs text-ink-foreground/70">
                {{ compactUnitWeightLabel(product.unit_weight_label) }}
              </p>
              <p v-if="unavailableReason" class="mt-1 text-xs text-ink-foreground/70">{{ unavailableReason }}</p>
            </div>
            <StockNotifyButton v-if="product.is_notifiable" :sku="product.sku" :name="product.name" :subscribed="product.is_notify_subscribed" compact inverted />
            <CartQuantityAction
              v-else
              :meta="meta"
              :qty="currentQty"
              :disabled="!product.can_add_to_cart"
              :max-qty="product.available_qty ?? product.max_qty"
              :add-label="product.can_add_to_cart ? 'Adicionar' : 'Indisponível'"
              tone="inverted"
            />
          </div>
        </div>
      </template>
    </div>
  </main>
</template>
