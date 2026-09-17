<script setup lang="ts">
import type { HomeResponse } from '~/types/shopman'
import { absoluteImage } from '~/presentation/seo'
import { NELSON_FALLBACK_SHOP } from '~/utils/nelsonFallback'

const apiPath = useShopmanApiPath()
const session = useShopSession()
const { setFromServer, refreshCart } = useCartState()
const { watchConnectivity } = useConnectivity()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined
const route = useRoute()
const requestUrl = useRequestURL()
const AUTH_SHELL_ROUTES = new Set(['/entrar', '/a'])
const authShellRoute = computed(() => AUTH_SHELL_ROUTES.has(route.path))

function focusMainContent () {
  if (!import.meta.client) return
  requestAnimationFrame(() => document.getElementById('main-content')?.focus())
}

// Reconexão / retorno de foco reconcilia o carrinho (a fonte de verdade que muda
// fora da aba). Falha silenciosa aqui é aceitável: é reconciliação de fundo.
watchConnectivity(() => { void refreshCart().catch(() => null) })

const { data: shellHome, refresh: refreshShellHome } = await useFetch<HomeResponse>(apiPath('/api/v1/storefront/home/'), {
  credentials: 'include',
  headers: requestHeaders,
  key: 'shopman-shell-home',
  immediate: true,
  server: true
})

watch(() => shellHome.value, value => {
  const authRoute = authShellRoute.value
  session.setFromHome(value?.home, { preserveAuthenticated: authRoute })
  if (!authRoute) setFromServer(value?.cart)
}, { immediate: true })

watch(authShellRoute, (isAuthRoute, wasAuthRoute) => {
  if (!isAuthRoute && wasAuthRoute) void refreshShellHome()
})

// O Nuxt restaura a rolagem do document, mas no PWA iOS o viewport rolável é
// interno para manter a bottom-nav fora do bug de position:fixed do WebKit.
// Mudança real de página começa no topo; query local (filtros) não é zerada.
watch(() => [route.path, route.hash] as const, async ([path, hash], [oldPath, oldHash]) => {
  if (!import.meta.client || (path === oldPath && hash === oldHash)) return
  await nextTick()
  const viewport = shopScrollViewport()
  if (!viewport || getComputedStyle(viewport).overflowY !== 'auto') return
  if (hash) {
    const id = decodeURIComponent(hash.slice(1))
    document.getElementById(id)?.scrollIntoView({ behavior: 'auto', block: 'start' })
    return
  }
  viewport.scrollTo({ top: 0, behavior: 'auto' })
})

useShopTheme(session.shop)

// theme-color também pinta a área nativa de pull-to-refresh no Safari. Usa o mesmo
// Dark Burgundy (ink) da barra superior, não o Burgundy 500 mais claro da marca.
// ?theme=neutral mantém o preview neutro.
const themeColor = computed(() => {
  const value = route.query.theme
  const previewNeutral = (Array.isArray(value) ? value[0] : value) === 'neutral'
  if (previewNeutral) return '#85786c'
  return '#531D22'
})

// Footer global (âncora de contato/info) em todas as páginas, EXCETO o checkout —
// ali um rodapé grande compete com a conclusão do pedido. Mantém o fluxo focado.
const hideFooter = computed(() => route.path.startsWith('/finalizar'))

// SEO global: nome do site = marca server-driven (tenant-neutral, não theming).
// titleTemplate evita duplicar a marca na home (onde o título JÁ é a marca).
const brandName = computed(() => session.shop.value?.brand_name || NELSON_FALLBACK_SHOP.brand_name)
const shortName = computed(() => session.shop.value?.short_name || NELSON_FALLBACK_SHOP.short_name)
useHead(() => ({
  titleTemplate: title => (title && title !== brandName.value ? `${title} · ${brandName.value}` : brandName.value),
  meta: [{ name: 'apple-mobile-web-app-title', content: shortName.value }]
}))
// PREVIEW DO LINK — todo link que a casa manda vira CARTÃO, não URL crua.
//
// Só a home declarava og:title/description/image. Todo o resto — o `/a` do login,
// o `/menu`, o acompanhamento do pedido — saía sem nada, e o WhatsApp, sem ter o
// que desenhar, mostrava a URL inteira, longa e feia. Justamente as páginas que a
// gente MANDA por mensagem eram as sem preview; a única que ninguém manda era a
// que tinha.
//
// O padrão mora aqui, no shell, porque assim vale para a página que ainda não
// existe. Página com algo melhor a dizer (produto, pedido) sobrescreve: o
// `useSeoMeta` da página resolve depois e vence.
const brandDescription = computed(
  () => session.shop.value?.description || NELSON_FALLBACK_SHOP.description
)
// A mesma imagem que a home usa: o primeiro destaque, que é foto de produto de
// verdade. Logo em cartão de link vira quadradinho sem graça; pão, não.
const brandOgImage = computed(() => absoluteImage(
  requestUrl.origin,
  shellHome.value?.home?.featured_items?.[0]?.image_url || session.shop.value?.logo_url
))

useSeoMeta({
  ogSiteName: () => brandName.value,
  ogLocale: 'pt_BR',
  themeColor: () => themeColor.value,
  ogTitle: () => brandName.value,
  ogDescription: () => brandDescription.value,
  ogType: 'website',
  ogImage: () => brandOgImage.value || undefined,
  twitterCard: 'summary_large_image',
  twitterTitle: () => brandName.value,
  twitterDescription: () => brandDescription.value,
  twitterImage: () => brandOgImage.value || undefined
})

</script>

<template>
  <div class="shop-shell flex min-h-dvh flex-col">
    <!-- No PWA instalado este é o único viewport rolável. A bottom-nav fica fora
         dele, em fluxo normal, para não depender do position:fixed que deriva no
         WebKit/iOS 26. No navegador comum o wrapper continua transparente ao layout. -->
    <div data-shop-scroll-viewport class="shop-scroll-viewport flex min-h-0 flex-1 flex-col">
      <NuxtRouteAnnouncer />
      <a
        href="#main-content"
        class="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-primary-foreground"
        @click="focusMainContent"
      >
        Pular para o conteúdo
      </a>
      <ShopHeader />
      <div id="main-content" tabindex="-1" class="flex-1 min-h-[calc(100svh-4rem)]">
        <NuxtPage />
      </div>
      <ShopFooter v-if="!hideFooter" />
    </div>
    <AppBottomNav />
    <ClientOnly>
      <SearchOverlay />
      <SubstituteSheet />
      <OfflineBanner />
      <PwaInstallInvite :copy="shellHome?.home?.pwa_copy" />
      <PwaUpdateToast :copy="shellHome?.home?.pwa_copy" />
      <!-- O convite de novidades: sobe na página em que a pessoa cai depois de
           entrar, uma vez, dirigido pela sessão (welcomeAsksMarketing). Nunca em
           /entrar, /a, no checkout ou no pedido. -->
      <MarketingPromptSheet />
    </ClientOnly>
    <!-- Fita de ambiente: FLUTUA no canto (fixed), então mora aqui com os
         overlays e não no fluxo. Some sozinha em produção — o servidor devolve
         a frase vazia. Fora do ClientOnly de propósito: quem abre a loja de
         teste tem que ver o aviso no primeiro pixel, não depois da hidratação. -->
    <EnvironmentRibbon />
    <UiSonner />
  </div>
</template>
