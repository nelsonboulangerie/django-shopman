<script setup lang="ts">
import {
  availableOnlyHint,
  choiceGroupsByName,
  dynamicCollectionMenuTarget,
  hiddenUnavailableCount,
  orderableItems,
  resolveCatalogSections,
  sectionEntries
} from '~/presentation/menu'
import {
  absoluteImage,
  breadcrumbJsonLd,
  collectionJsonLd,
  jsonLdText,
  listingDescription,
  truncateClean
} from '~/presentation/seo'
import type { CatalogResponse } from '~/types/shopman'

// Página de coleção indexável (rota própria, self-canonical) — diferente das
// variantes de filtro do /menu (que canonicalizam para /menu). Alimentada pelo
// endpoint Django de menu filtrado por coleção (build_catalog com collection_ref).
const route = useRoute()
const apiPath = useShopmanApiPath()
const requestUrl = useRequestURL()
const session = useShopSession()
const { openSearch } = useSearchOverlay()

const collectionRef = computed(() => String(route.params.ref || ''))
const dynamicRedirectTarget = computed(() => dynamicCollectionMenuTarget(collectionRef.value))

if (dynamicRedirectTarget.value) {
  await navigateTo(dynamicRedirectTarget.value, { redirectCode: 301, replace: true })
}

const { data, pending, error, refresh } = await useFetch<CatalogResponse>(
  () => apiPath(`/api/v1/storefront/catalog/${encodeURIComponent(collectionRef.value)}/`),
  { credentials: 'include', immediate: !dynamicRedirectTarget.value, lazy: true }
)
usePageContentPending(pending)

// Coleção inexistente: 404 de verdade — o endpoint levanta Http404 via
// ensure_active_collection(); a SSR responde 404 + noindex (error.vue).
if (import.meta.server && !dynamicRedirectTarget.value && error.value?.statusCode === 404) {
  throw createError({ statusCode: 404, statusMessage: 'Coleção não encontrada', fatal: true })
}

if (import.meta.client) {
  watch(error, (failure) => {
    if (!dynamicRedirectTarget.value && failure?.statusCode === 404) {
      showError(createError({ statusCode: 404, statusMessage: 'Coleção não encontrada', fatal: true }))
    }
  })
}

if (!dynamicRedirectTarget.value) requireContentOnSsr(error.value, !!data.value?.catalog, 'Coleção')

const catalog = computed(() => data.value?.catalog || null)
const section = computed(() => {
  const sections = resolveCatalogSections(catalog.value)
  return sections.find(s => s.ref === collectionRef.value) || sections[0] || null
})
const items = computed(() => section.value?.items || catalog.value?.items || [])
// "Mostrar só disponíveis": a mesma chave do cardápio (padrão da casa, escolha
// do cliente vence). SEO e JSON-LD seguem lendo a coleção inteira (`items`).
const { availableOnly, setAvailableOnly } = useAvailableOnly()
const unavailableInCollection = computed(() => hiddenUnavailableCount(items.value))
const visibleItems = computed(() => availableOnly.value ? orderableItems(items.value) : items.value)
const hiddenUnavailable = computed(() => availableOnly.value ? unavailableInCollection.value : 0)
const showAvailableOnlyToggle = computed(() => availableOnly.value || unavailableInCollection.value > 0)
const availableOnlyFilterHint = computed(() => availableOnlyHint(availableOnly.value, hiddenUnavailable.value))
// Cartões de escolha (mesmo `choice_group`) entre os itens desta coleção.
const entries = computed(() => sectionEntries(visibleItems.value, choiceGroupsByName(visibleItems.value)))
const title = computed(() => section.value?.label || 'Coleção')
const description = computed(() => section.value?.description || '')

const canonicalUrl = computed(() => `${requestUrl.origin}${route.path}`)
// A descrição da coleção escrita no Admin vence. Sem ela, "12 itens em Rústicos."
// não dizia de onde nem o quê: a frase padrão nomeia a casa, a cidade e os
// primeiros itens de verdade da coleção.
const pageDescription = computed(() => truncateClean(description.value, 160) || listingDescription({
  subject: title.value,
  brandName: session.shop.value?.brand_name || '',
  tagline: session.shop.value?.tagline,
  city: session.shop.value?.default_city,
  names: items.value.map(item => item.name)
}))
// Cartão de link com foto do que a coleção tem, não com o padrão genérico do shell.
const ogImage = computed(() => absoluteImage(requestUrl.origin, items.value.find(item => item.image_url)?.image_url))

useSeoMeta({
  title: () => title.value,
  description: () => pageDescription.value,
  ogTitle: () => title.value,
  ogDescription: () => pageDescription.value,
  ogUrl: () => canonicalUrl.value,
  ogImage: () => ogImage.value || undefined,
  twitterTitle: () => title.value,
  twitterDescription: () => pageDescription.value,
  twitterImage: () => ogImage.value || undefined
})
useCanonical()

// JSON-LD CollectionPage (ItemList) + BreadcrumbList — a coleção para o Google.
useHead({
  script: () => catalog.value && items.value.length
    ? [
        {
          type: 'application/ld+json',
          innerHTML: jsonLdText(collectionJsonLd({
            name: title.value,
            url: canonicalUrl.value,
            origin: requestUrl.origin,
            items: items.value
          }))
        },
        {
          type: 'application/ld+json',
          innerHTML: jsonLdText(breadcrumbJsonLd([
            { name: 'Início', url: `${requestUrl.origin}/` },
            { name: 'Cardápio', url: `${requestUrl.origin}/menu` },
            { name: title.value, url: canonicalUrl.value }
          ]))
        }
      ]
    : []
})
</script>

<template>
  <main class="min-w-0">
    <div class="shop-section">
      <div class="shop-container shop-stack-block">
        <nav aria-label="Trilha de navegação" class="shop-meta">
          <NuxtLink to="/menu" class="hover:underline">Cardápio</NuxtLink>
          <span aria-hidden="true"> / </span>
          <span class="text-foreground">{{ title }}</span>
        </nav>

        <div class="shop-stack-micro">
          <h1 class="shop-title">{{ title }}</h1>
          <p v-if="description" class="shop-muted">{{ description }}</p>
        </div>

        <div v-if="pending" class="grid grid-cols-1 gap-x-8 md:grid-cols-2 xl:grid-cols-3">
          <div v-for="n in 6" :key="n" class="flex gap-3 border-b py-3">
            <div class="min-w-0 flex-1 space-y-2 self-center">
              <UiSkeleton class="h-4 w-3/4" />
              <UiSkeleton class="h-3 w-full" />
              <UiSkeleton class="h-4 w-1/4" />
            </div>
            <UiSkeleton class="size-28 shrink-0 rounded-lg" />
          </div>
        </div>

        <UiAlert v-else-if="error" variant="destructive">
          <UiAlertTitle>Não conseguimos abrir a coleção agora</UiAlertTitle>
          <UiAlertDescription>
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <span>Foi uma falha nossa. Tente de novo em instantes.</span>
              <UiButton size="sm" variant="outline" @click="refresh">Tentar de novo</UiButton>
            </div>
          </UiAlertDescription>
        </UiAlert>

        <template v-else-if="items.length">
          <div
            v-if="showAvailableOnlyToggle"
            class="flex items-center justify-between gap-3 rounded-lg border bg-card p-3"
            data-collection-available-only
          >
            <div class="min-w-0">
              <p class="shop-body font-semibold">Mostrar só disponíveis</p>
              <p class="shop-meta">{{ availableOnlyFilterHint }}</p>
            </div>
            <UiSwitch
              :model-value="availableOnly"
              aria-label="Mostrar só disponíveis"
              @update:model-value="setAvailableOnly(Boolean($event))"
            />
          </div>

          <UiEmpty v-if="!visibleItems.length" class="border" data-collection-all-hidden>
            <UiEmptyMedia variant="icon">
              <Icon name="lucide:eye-off" />
            </UiEmptyMedia>
            <UiEmptyHeader>
              <UiEmptyTitle>Nada disponível nesta coleção agora</UiEmptyTitle>
              <UiEmptyDescription>
                {{ hiddenUnavailable === 1 ? '1 item indisponível está escondido.' : `${hiddenUnavailable} itens indisponíveis estão escondidos.` }}
              </UiEmptyDescription>
            </UiEmptyHeader>
            <div class="flex justify-center">
              <UiButton @click="setAvailableOnly(false)">Mostrar indisponíveis</UiButton>
            </div>
          </UiEmpty>

          <div v-else class="grid grid-cols-1 gap-x-8 md:grid-cols-2 xl:grid-cols-3">
            <template v-for="entry in entries" :key="entry.key">
              <ProductChoiceGroupItem
                v-if="entry.kind === 'group'"
                :group="entry.group"
                framed
                class="border-b"
              />
              <ProductListItem
                v-else
                :item="entry.item"
                framed
                class="border-b"
              />
            </template>
          </div>

          <div data-collection-end-actions class="pt-4">
            <div class="flex flex-col gap-3 rounded-lg border bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
              <p class="shop-body font-semibold">Ainda procurando algo?</p>
              <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
                <UiButton to="/menu" icon="lucide:utensils" class="min-h-11 justify-center">
                  Ver cardápio completo
                </UiButton>
                <UiButton type="button" variant="outline" icon="lucide:search" class="min-h-11 justify-center" @click="openSearch()">
                  Buscar no cardápio
                </UiButton>
              </div>
            </div>
          </div>
        </template>

        <UiEmpty v-else class="border">
          <UiEmptyMedia variant="icon">
            <Icon name="lucide:croissant" />
          </UiEmptyMedia>
          <UiEmptyHeader>
            <UiEmptyTitle>Coleção em preparo</UiEmptyTitle>
            <UiEmptyDescription>
              Em breve novidades por aqui. Veja o
              <NuxtLink to="/menu" class="underline">cardápio completo</NuxtLink>.
            </UiEmptyDescription>
          </UiEmptyHeader>
        </UiEmpty>
      </div>
    </div>
  </main>
</template>
