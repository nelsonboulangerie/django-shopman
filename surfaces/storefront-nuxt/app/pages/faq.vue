<script setup lang="ts">
// Perguntas frequentes — página própria, indexável.
//
// As perguntas moravam só num acordeão da home, e o FAQPage (JSON-LD) ia junto.
// Acordeão fechado não põe a resposta no HTML, e a home não é a página que
// responde "vocês entregam?": quem busca isso no Google tem que cair AQUI, com a
// resposta já no DOM servido. Por isso <details>/<summary>: fechado para quem lê,
// inteiro para quem indexa.
import { faqContactLinks, faqItems } from '~/presentation/faq'
import { breadcrumbJsonLd, faqJsonLd, jsonLdText, listingDescription, sitePageSeo } from '~/presentation/seo'
import type { HomeResponse } from '~/types/shopman'
import { NELSON_FALLBACK_SHOP } from '~/utils/nelsonFallback'

const session = useShopSession()
const requestUrl = useRequestURL()
const { site: siteSeo, ready: siteSeoReady } = useSiteSeo()
await siteSeoReady

// A home do shell (app.vue) já está no payload: é dela que vêm as perguntas
// enquanto o cadastro do site não tiver as próprias.
const { data: shellHome } = useNuxtData<HomeResponse>('shopman-shell-home')

const brandName = computed(() => session.shop.value?.brand_name || NELSON_FALLBACK_SHOP.brand_name)
const pageSeo = computed(() => sitePageSeo(siteSeo.value, 'faq'))
const title = computed(() => pageSeo.value.title || 'Perguntas frequentes')
const description = computed(() => pageSeo.value.description || listingDescription({
  subject: 'Perguntas frequentes',
  brandName: brandName.value,
  tagline: session.shop.value?.tagline,
  city: session.shop.value?.default_city
}))
const items = computed(() => faqItems(siteSeo.value?.faq, shellHome.value?.home?.faq))
const contactLinks = computed(() => faqContactLinks({
  business: siteSeo.value?.business,
  shop: session.shop.value,
  whatsappUrl: session.publicConfig.value?.whatsapp_url
}))

const canonicalUrl = computed(() => `${requestUrl.origin}/faq`)

useSeoMeta({
  title: () => title.value,
  description: () => description.value,
  ogTitle: () => title.value,
  ogDescription: () => description.value,
  ogUrl: () => canonicalUrl.value,
  ogType: 'website',
  twitterTitle: () => title.value,
  twitterDescription: () => description.value
})
useCanonical()

useHead({
  script: () => [
    ...(items.value.length
      ? [{ type: 'application/ld+json' as const, innerHTML: jsonLdText(faqJsonLd(items.value)) }]
      : []),
    {
      type: 'application/ld+json' as const,
      innerHTML: jsonLdText(breadcrumbJsonLd([
        { name: 'Início', url: `${requestUrl.origin}/` },
        { name: title.value, url: canonicalUrl.value }
      ]))
    }
  ]
})
</script>

<template>
  <main class="shop-section pt-0">
    <div class="shop-breadcrumb-bar mb-4">
      <div class="shop-container py-2">
        <UiBreadcrumbs :items="[{ label: 'Início', link: '/' }, { label: title }]" />
      </div>
    </div>

    <div class="shop-container shop-stack-block max-w-3xl">
      <div>
        <h1 class="shop-title">{{ title }}</h1>
        <p v-if="pageSeo.description" class="shop-muted">{{ pageSeo.description }}</p>
      </div>

      <div v-if="items.length" class="divide-y border-y" data-faq-list>
        <details
          v-for="item in items"
          :key="item.ref || item.question"
          class="group py-1"
          :data-faq-item="item.ref || undefined"
        >
          <summary class="flex cursor-pointer list-none items-center justify-between gap-4 py-3 text-left font-semibold [&::-webkit-details-marker]:hidden">
            <span>{{ item.question }}</span>
            <Icon name="lucide:chevron-down" class="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
          </summary>
          <p class="whitespace-pre-line pb-4 text-sm leading-6 text-muted-foreground">{{ item.answer }}</p>
        </details>
      </div>

      <div v-else class="rounded-lg border bg-card p-6 text-center" data-faq-empty>
        <Icon name="lucide:message-circle-question-mark" class="mx-auto size-8 text-muted-foreground" />
        <p class="mt-3 font-semibold">Ainda não publicamos as perguntas frequentes.</p>
        <p class="mt-1 shop-muted">Se ficou alguma dúvida, fale com a gente por um dos canais abaixo.</p>
      </div>

      <section v-if="contactLinks.length" class="space-y-4 rounded-lg border bg-card p-4 sm:p-6" data-faq-contact>
        <div>
          <h2 class="shop-heading">Não achou a sua resposta?</h2>
          <p class="shop-muted">Pergunte direto para a gente.</p>
        </div>
        <ul class="flex flex-col gap-2">
          <li v-for="link in contactLinks" :key="link.kind">
            <NuxtLink
              :to="link.href"
              :target="link.kind === 'whatsapp' ? '_blank' : undefined"
              :rel="link.kind === 'whatsapp' ? 'noopener' : undefined"
              class="inline-flex items-center gap-2 text-sm underline-offset-2 hover:underline"
              :data-faq-contact-link="link.kind"
            >
              <Icon :name="link.icon" class="size-4 shrink-0 text-muted-foreground" />
              <span class="text-muted-foreground">{{ link.label }}:</span>
              <span class="font-semibold">{{ link.value }}</span>
            </NuxtLink>
          </li>
        </ul>
      </section>

      <div>
        <UiButton to="/menu" variant="ghost" icon="lucide:arrow-right" icon-placement="right" class="shop-gold-hover">
          Ver o cardápio
        </UiButton>
      </div>
    </div>
  </main>
</template>
