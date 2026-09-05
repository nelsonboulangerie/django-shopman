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

useShopTheme(session.shop)

// theme-color (tint da barra do iOS/Safari no topo) = burgundy escuro (tom do header e
// da status bar), pra o topo ficar consistente. A BASE é preta (canvas do <html>).
// ?theme=neutral mantém o preview neutro.
const themeColor = computed(() => {
  const value = route.query.theme
  const previewNeutral = (Array.isArray(value) ? value[0] : value) === 'neutral'
  if (previewNeutral) return '#85786c'
  return '#531d22'
})

// Footer global (âncora de contato/info) em todas as páginas, EXCETO o checkout —
// ali um rodapé grande compete com a conclusão do pedido. Mantém o fluxo focado.
const hideFooter = computed(() => route.path.startsWith('/finalizar'))

// SEO global: nome do site = marca server-driven (tenant-neutral, não theming).
// titleTemplate evita duplicar a marca na home (onde o título JÁ é a marca).
const brandName = computed(() => session.shop.value?.brand_name || NELSON_FALLBACK_SHOP.brand_name)
useHead({
  titleTemplate: title => (title && title !== brandName.value ? `${title} | ${brandName.value}` : brandName.value)
})
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
    <NuxtRouteAnnouncer />
    <a
      href="#main-content"
      class="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-primary-foreground"
    >
      Pular para o conteúdo
    </a>
    <ShopHeader />
    <div id="main-content" class="flex-1 min-h-[calc(100svh-4rem)]">
      <NuxtPage />
    </div>
    <ShopFooter v-if="!hideFooter" />
    <AppBottomNav />
    <ClientOnly>
      <SearchOverlay />
      <SubstituteSheet />
      <OfflineBanner />
    </ClientOnly>
    <!-- Fita de ambiente: FLUTUA no canto (fixed), então mora aqui com os
         overlays e não no fluxo. Some sozinha em produção — o servidor devolve
         a frase vazia. Fora do ClientOnly de propósito: quem abre a loja de
         teste tem que ver o aviso no primeiro pixel, não depois da hidratação. -->
    <EnvironmentRibbon />
    <UiSonner />
  </div>
</template>
