<script setup lang="ts">
import type { CopyEntryProjection, HomeProjection, Action } from '~/types/shopman'

interface HeroSlide {
  ref: string
  eyebrow?: string
  titleLines: string[]
  description?: string
  image: { phone: string, wide: string } | null
  imageAlt: string
  primaryLabel: string
  primaryIcon: string
  primaryTo?: string
  primaryAction?: Action | null
  secondaryLabel?: string
  secondaryTo?: string
}

const props = defineProps<{
  home: HomeProjection
  primaryAction: Action | null
  reorderAction: Action | null
  reorderLoading?: boolean
  statusOpen: boolean
  statusLabel?: string
  closedCtaLabel?: string
}>()

const emit = defineEmits<{
  reorder: [action: Action | null]
}>()

// Fotos DA CASA (o dono escolheu uma a uma em 23/09/2026, vendo cada
// candidata neste enquadramento). Eram de banco de imagem — padaria de outra
// gente na vitrine da nossa.
//
// Duas por slide, e não é capricho: o herói é uma faixa larga no computador e
// quase a tela inteira, em pé, no celular. Uma foto só perde metade do assunto
// num dos dois. O `<picture>` deixa o navegador baixar SÓ a que couber, então
// a segunda não custa peso.
const HERO_IMAGES = {
  greeting: { phone: '/img/home/facade6.webp', wide: '/img/home/facade2.webp' },
  order: { phone: '/img/home/selfservice.webp', wide: '/img/home/selfservice.webp' },
  reorder: { phone: '/img/home/facade4.webp', wide: '/img/home/interior.webp' },
  handmade: { phone: '/img/home/baguette.webp', wide: '/img/home/baguette.webp' }
} as const

const menuTo = computed(() => props.primaryAction?.href || '/menu')
const activeIndex = ref(0)
const paused = ref(false)
const touchStartX = ref(0)
let autoplayTimer: ReturnType<typeof setInterval> | null = null

function titleOf (entry: CopyEntryProjection, fallback: string) {
  return entry.title?.trim() || fallback
}

function messageOf (entry: CopyEntryProjection, fallback: string) {
  return entry.message?.trim() || fallback
}

function shopDescription () {
  const shop = props.home.shop
  return shop.description?.trim() || shop.tagline?.trim() || shop.brand_name
}

function sentence (value: string) {
  const trimmed = value.trim()
  if (!trimmed) return ''
  return /[.!?]$/.test(trimmed) ? trimmed : `${trimmed}.`
}

function activatePreviousSlide () {
  const total = slides.value.length
  if (!total) return
  activeIndex.value = activeIndex.value === 0 ? total - 1 : activeIndex.value - 1
}

function activateNextSlide () {
  const total = slides.value.length
  if (!total) return
  activeIndex.value = activeIndex.value === total - 1 ? 0 : activeIndex.value + 1
}

function activateSlide (index: number) {
  activeIndex.value = index
}

// Toda navegação manual reinicia o autoplay, senão o avanço automático (8s)
// pode trocar o slide logo após o toque do usuário — parecendo que a seta
// "não funcionou".
function restartAutoplay () {
  if (autoplayTimer) {
    clearInterval(autoplayTimer)
    autoplayTimer = null
  }
  if (!paused.value && slides.value.length > 1) {
    autoplayTimer = setInterval(activateNextSlide, 8000)
  }
}

function goToPreviousSlide () {
  activatePreviousSlide()
  restartAutoplay()
}

function goToNextSlide () {
  activateNextSlide()
  restartAutoplay()
}

function goToSlide (index: number) {
  activateSlide(index)
  restartAutoplay()
}

function handleTouchEnd (event: TouchEvent) {
  const endX = event.changedTouches[0]?.screenX
  if (endX === undefined) return
  const dx = endX - touchStartX.value
  if (Math.abs(dx) < 50) return
  if (dx < 0) goToNextSlide()
  else goToPreviousSlide()
}

function handlePrimaryAction (slide: HeroSlide) {
  if (slide.primaryAction) emit('reorder', slide.primaryAction)
}

const slides = computed<HeroSlide[]>(() => {
  const copy = props.home.hero_copy
  const shop = props.home.shop
  const omo = props.home.omotenashi
  const customerName = omo.customer_name?.trim()
  const description = shopDescription()
  const menuLabel = (!props.statusOpen && props.closedCtaLabel) || titleOf(copy.menu_cta, 'Ver cardápio')
  // Loja fechada: o rótulo do hero era a ÚNICA pista do estado, e convidava a montar
  // pedido sem dizer que a loja estava fechada — o cliente só descobria no checkout,
  // com a sacola pronta. O selo de estado existe, mas vive lá embaixo, no card
  // "visite a loja". Aqui ele sobe para o topo, que é o que a pessoa lê.
  const closedEyebrow = props.statusOpen
    ? undefined
    : `${props.statusLabel ? `${props.statusLabel}. ` : ''}Você monta agora e finaliza quando abrirmos.`
  const handmadeTitle = `${titleOf(copy.handmade_title_prefix, 'Feito à mão,')} ${titleOf(copy.handmade_title_suffix, 'todo dia')}`
  const greetingTitle = sentence(omo.greeting_with_name || handmadeTitle)
  const list: HeroSlide[] = []

  if (omo.is_birthday) {
    list.push({
      ref: 'birthday',
      // "Um cuidado especial hoje" anunciava um cuidado e não dizia qual — e o botão
      // abaixo leva ao cardápio de sempre. Calor sem promessa vazia é o que vale aqui.
      // O "!" final é do TEMPLATE: o registro já traz "Feliz aniversário!", e concatenar
      // produzia "Feliz aniversário!, Nome!".
      titleLines: [`${titleOf(copy.birthday_heading, 'Feliz aniversário').replace(/!+$/, '')}${customerName ? `, ${customerName}` : ''}!`],
      description: messageOf(copy.birthday_sub, description),
      image: HERO_IMAGES.greeting,
      imageAlt: shop.brand_name,
      primaryLabel: titleOf(copy.birthday_cta, titleOf(copy.menu_cta, 'Ver cardápio')),
      primaryIcon: 'lucide:gift',
      primaryTo: menuTo.value
    })
  } else {
    list.push({
      ref: 'greeting',
      titleLines: [greetingTitle],
      image: HERO_IMAGES.greeting,
      imageAlt: shop.brand_name,
      primaryLabel: menuLabel,
      primaryIcon: 'lucide:utensils',
      primaryTo: menuTo.value
    })
  }

  list.push({
    ref: 'order',
    titleLines: [
      titleOf(copy.order_title_prefix, shop.brand_name),
      titleOf(copy.order_title_suffix, shop.tagline)
    ],
    description: messageOf(copy.order_subtitle, description),
    image: HERO_IMAGES.order,
    imageAlt: shop.brand_name,
    primaryLabel: (!props.statusOpen && props.closedCtaLabel) || props.primaryAction?.label || menuLabel,
    primaryIcon: 'lucide:utensils',
    primaryTo: menuTo.value
  })

  if (props.home.last_order_ref && props.reorderAction) {
    list.push({
      ref: 'reorder',
      titleLines: [
        titleOf(copy.reorder_title_prefix, 'Quer repetir seu'),
        `${titleOf(copy.reorder_title_suffix, 'último pedido')}${customerName ? `, ${customerName}` : ''}?`
      ],
      // "favorito" é conceito próprio da loja (o coração, a seção "Seus favoritos"):
      // usá-lo para o último pedido faz o cliente procurar onde ele marcou.
      description: messageOf(copy.reorder_subtitle, 'Os itens do seu último pedido voltam para a sacola.'),
      image: HERO_IMAGES.reorder,
      imageAlt: shop.brand_name,
      primaryLabel: 'Repetir pedido',
      primaryIcon: 'lucide:rotate-ccw',
      primaryAction: props.reorderAction
    })
  } else {
    list.push({
      ref: 'greeting-return',
      titleLines: [greetingTitle],
      image: HERO_IMAGES.reorder,
      imageAlt: shop.brand_name,
      primaryLabel: menuLabel,
      primaryIcon: 'lucide:utensils',
      primaryTo: menuTo.value
    })
  }

  list.push({
    ref: 'handmade',
    titleLines: [
      titleOf(copy.handmade_title_prefix, 'Feito à mão,'),
      titleOf(copy.handmade_title_suffix, 'todo dia')
    ],
    description: messageOf(copy.handmade_subtitle, 'Do forno para a sua mesa.'),
    image: HERO_IMAGES.handmade,
    imageAlt: shop.brand_name,
    primaryLabel: menuLabel,
    primaryIcon: 'lucide:utensils',
    primaryTo: menuTo.value
  })

  return closedEyebrow ? list.map(slide => ({ ...slide, eyebrow: slide.eyebrow || closedEyebrow })) : list
})
const activeSlide = computed(() => slides.value[activeIndex.value] || slides.value[0])
const heroTitleLabel = computed(() => activeSlide.value?.titleLines.join(' ') || '')

watch(slides, value => {
  if (activeIndex.value >= value.length) activeIndex.value = 0
})

watch(paused, value => {
  if (value && autoplayTimer) {
    clearInterval(autoplayTimer)
    autoplayTimer = null
  } else if (!value && !autoplayTimer && slides.value.length > 1) {
    autoplayTimer = setInterval(activateNextSlide, 8000)
  }
})

onMounted(() => {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (!reduceMotion && slides.value.length > 1) {
    autoplayTimer = setInterval(activateNextSlide, 8000)
  }
})

onBeforeUnmount(() => {
  if (autoplayTimer) clearInterval(autoplayTimer)
})
</script>

<template>
  <section
    v-if="activeSlide"
    class="-mx-4 overflow-hidden rounded-none border-b bg-card text-card-foreground shadow-sm sm:mx-0 sm:rounded-lg sm:border"
    data-home-hero-carousel
    aria-roledescription="carousel"
    aria-label="Destaques da loja"
    @mouseenter="paused = true"
    @mouseleave="paused = false"
    @focusin="paused = true"
    @focusout="paused = false"
    @touchstart.passive="touchStartX = $event.changedTouches[0]?.screenX || 0"
    @touchend.passive="handleTouchEnd"
  >
    <div class="relative h-[calc(100svh-15.25rem-env(safe-area-inset-bottom,0px))] select-none sm:h-[440px] lg:h-[480px]">
      <!-- Camada de imagens empilhada: crossfade por opacity (robusto — sem
           enter/leave do Vue a orfanar elementos durante autoplay/HMR). -->
      <div class="absolute inset-0 bg-muted">
        <template v-for="(slide, index) in slides" :key="slide.ref">
          <picture v-if="slide.image">
            <source media="(min-width: 640px)" :srcset="slide.image.wide">
            <img
              :src="slide.image.phone"
              :alt="index === activeIndex ? slide.imageAlt : ''"
              :fetchpriority="index === 0 ? 'high' : undefined"
              :loading="index === 0 ? 'eager' : 'lazy'"
              decoding="async"
              aria-hidden="true"
              class="absolute inset-0 size-full object-cover transition-opacity duration-[900ms] ease-out motion-reduce:transition-none"
              :class="index === activeIndex ? 'opacity-100' : 'opacity-0'"
            >
          </picture>
        </template>
      </div>
      <div class="absolute inset-0 bg-[linear-gradient(0deg,rgba(0,0,0,.78),rgba(0,0,0,.42),rgba(0,0,0,.14))]" />

      <!-- Layout pôster: conteúdo ancorado embaixo (foto respira no topo). Sem
           flex-1 a empurrar — o bloco cresce pelo conteúdo, nunca sobrepõe. -->
      <div class="relative z-10 flex h-full flex-col justify-end px-6 pb-10 pt-8 text-center text-white sm:px-8 sm:pb-14 sm:pt-12 lg:px-10">
        <Transition name="hero-text" mode="out-in">
          <div :key="activeSlide.ref" class="mx-auto flex w-full max-w-3xl flex-col items-center justify-center">
            <p
              v-if="activeSlide.eyebrow"
              class="text-sm font-semibold text-white/80"
              :class="statusOpen ? 'uppercase tracking-wide' : ''"
            >{{ activeSlide.eyebrow }}</p>
            <h1 class="shop-display mt-2 [text-shadow:0_2px_18px_rgba(0,0,0,0.45)]" :aria-label="heroTitleLabel">
              <span v-for="line in activeSlide.titleLines" :key="line" class="block" aria-hidden="true">
                {{ line }}
              </span>
            </h1>
            <p v-if="activeSlide.description" class="mt-4 max-w-xl shop-body text-white/85 [text-shadow:0_1px_10px_rgba(0,0,0,0.4)] sm:text-base">
              {{ activeSlide.description }}
            </p>
            <div class="mt-8 flex flex-wrap justify-center gap-3">
              <UiButton
                v-if="activeSlide.primaryTo"
                :to="activeSlide.primaryTo"
                size="lg"
                :icon="activeSlide.primaryIcon"
                class="shop-hero-cta bg-white text-neutral-900 shadow-lg hover:bg-white/90"
              >
                {{ activeSlide.primaryLabel }}
              </UiButton>
              <UiButton
                v-else
                size="lg"
                :icon="activeSlide.primaryIcon"
                :loading="props.reorderLoading"
                class="shop-hero-cta bg-white text-neutral-900 shadow-lg hover:bg-white/90"
                @click="handlePrimaryAction(activeSlide)"
              >
                {{ activeSlide.primaryLabel }}
              </UiButton>
              <UiButton
                v-if="activeSlide.secondaryTo"
                :to="activeSlide.secondaryTo"
                size="lg"
                variant="outline"
                class="shop-hero-cta-ghost border-white/40 bg-white/10 text-white backdrop-blur-sm hover:bg-white/20 hover:text-white"
              >
                {{ activeSlide.secondaryLabel }}
              </UiButton>
            </div>
          </div>
        </Transition>
      </div>

      <template v-if="slides.length > 1">
        <UiButton
          variant="ghost"
          size="icon-lg"
          icon="lucide:chevron-left"
          class="absolute left-2.5 top-1/2 z-20 hidden size-11 -translate-y-1/2 rounded-full bg-black/35 text-white backdrop-blur-sm hover:bg-black/55 hover:text-white sm:left-3 sm:inline-flex"
          aria-label="Slide anterior"
          @click="goToPreviousSlide"
        />
        <UiButton
          variant="ghost"
          size="icon-lg"
          icon="lucide:chevron-right"
          class="absolute right-2.5 top-1/2 z-20 hidden size-11 -translate-y-1/2 rounded-full bg-black/35 text-white backdrop-blur-sm hover:bg-black/55 hover:text-white sm:right-3 sm:inline-flex"
          aria-label="Próximo slide"
          @click="goToNextSlide"
        />
        <div class="absolute inset-x-0 bottom-0 z-20 flex items-center justify-center sm:bottom-1" role="tablist" aria-label="Slides">
          <!-- Alvo de toque ≥44px (h-11 + px-1.5): a pílula visível é pequena (h-2),
               mas a área clicável é generosa — antes o dot de 8px era quase impossível
               de acertar, dando a sensação de "botão que não funciona". -->
          <UiButton
            v-for="(slide, index) in slides"
            :key="slide.ref"
            variant="ghost"
            size="icon-xs"
            class="h-11 min-h-0 w-auto rounded-full px-1.5 hover:bg-transparent"
            :aria-label="`Slide ${index + 1}`"
            :aria-selected="index === activeIndex"
            role="tab"
            @click="goToSlide(index)"
          >
            <span
              class="block h-2 rounded-full transition-all duration-300"
              :class="index === activeIndex ? 'w-6 bg-white' : 'w-2 bg-white/45'"
            />
          </UiButton>
        </div>
      </template>
    </div>
  </section>
</template>
