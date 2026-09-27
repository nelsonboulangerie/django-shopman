<script setup lang="ts">
const nuxtApp = useNuxtApp()
const router = useRouter()
const active = ref(false)
const delayed = ref(false)
const announcement = ref('')

interface OriginFeedback {
  top: number
  left: number
  width: number
  height: number
  radius: string
  showLabel: boolean
}

const originFeedback = ref<OriginFeedback | null>(null)
const delayedMessage = ref('Só mais um instante…')

let delayedTimer: ReturnType<typeof setTimeout> | null = null
let watchdogTimer: ReturnType<typeof setTimeout> | null = null

function messageForDestination (destination?: URL) {
  const path = destination?.pathname || ''
  if (path.startsWith('/sacola')) return 'Ainda abrindo sua sacola…'
  if (path.startsWith('/menu') || path.startsWith('/colecao')) return 'Ainda abrindo o cardápio…'
  if (path.startsWith('/produto')) return 'Ainda abrindo o produto…'
  if (path.startsWith('/finalizar')) return 'Ainda abrindo a finalização…'
  if (path.startsWith('/pedido')) return 'Ainda abrindo seu pedido…'
  if (path.startsWith('/conta') || path.startsWith('/entrar') || path.startsWith('/a')) return 'Ainda abrindo sua conta…'
  if (path === '/') return 'Ainda abrindo o início…'
  return 'Só mais um instante…'
}

function feedbackForOrigin (link: HTMLAnchorElement): OriginFeedback | null {
  const rect = link.getBoundingClientRect()
  if (rect.width < 1 || rect.height < 1) return null

  const showLabel = rect.width >= 76 && rect.height >= 36
  const width = rect.width > 180 ? 116 : Math.max(40, rect.width)
  const height = rect.height > 72 ? 40 : Math.max(40, rect.height)
  const unclampedLeft = rect.left + (rect.width - width) / 2
  const unclampedTop = rect.top + (rect.height - height) / 2

  return {
    top: Math.max(6, Math.min(window.innerHeight - height - 6, unclampedTop)),
    left: Math.max(6, Math.min(window.innerWidth - width - 6, unclampedLeft)),
    width,
    height,
    radius: showLabel ? '9999px' : `${Math.min(width, height) / 2}px`,
    showLabel
  }
}

function clearTimers () {
  if (delayedTimer) clearTimeout(delayedTimer)
  if (watchdogTimer) clearTimeout(watchdogTimer)
  delayedTimer = null
  watchdogTimer = null
}

function begin (destination?: URL, origin?: HTMLAnchorElement) {
  if (destination) delayedMessage.value = messageForDestination(destination)
  else if (!active.value) delayedMessage.value = 'Só mais um instante…'
  if (origin) originFeedback.value = feedbackForOrigin(origin)
  if (active.value) return

  active.value = true
  delayed.value = false
  announcement.value = ''
  clearTimers()

  delayedTimer = setTimeout(() => {
    if (!active.value) return
    delayed.value = true
    announcement.value = delayedMessage.value
  }, 300)

  // Defesa contra uma navegação cancelada sem erro observável.
  watchdogTimer = setTimeout(finish, 15_000)
}

function finish () {
  active.value = false
  delayed.value = false
  announcement.value = ''
  originFeedback.value = null
  clearTimers()
}

function navigationIntent (event: MouseEvent) {
  if (
    event.defaultPrevented
    || event.button !== 0
    || event.metaKey
    || event.ctrlKey
    || event.shiftKey
    || event.altKey
  ) return

  const target = event.target instanceof Element ? event.target : null
  const link = target?.closest<HTMLAnchorElement>('a[href]')
  if (
    !link
    || link.hasAttribute('download')
    || link.getAttribute('target') === '_blank'
    || link.getAttribute('aria-disabled') === 'true'
  ) return

  let destination: URL
  try {
    destination = new URL(link.href, window.location.href)
  } catch {
    return
  }
  if (destination.origin !== window.location.origin) return

  const current = new URL(window.location.href)
  if (
    destination.pathname === current.pathname
    && destination.search === current.search
  ) return

  // Confirma o gesto antes do middleware que espera a sacola ficar durável.
  begin(destination, link)
}

const removePageStart = nuxtApp.hook('page:start', () => begin())
const removePageFinish = nuxtApp.hook('page:finish', finish)
const removeAppError = nuxtApp.hook('app:error', finish)
const removeRouterError = router.onError(finish)

onMounted(() => {
  document.addEventListener('click', navigationIntent, true)
  window.addEventListener('pageshow', finish)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', navigationIntent, true)
  window.removeEventListener('pageshow', finish)
  removePageStart()
  removePageFinish()
  removeAppError()
  removeRouterError()
  finish()
})
</script>

<template>
  <!-- Confirmação instantânea exatamente onde a pessoa tocou. É fixed e não
       participa do layout: não desloca header, pillbar ou conteúdo. -->
  <div
    v-if="active && originFeedback"
    class="pointer-events-none fixed z-[100] flex items-center justify-center gap-2 bg-cta px-2 text-xs font-semibold text-cta-foreground shadow-lg ring-2 ring-background"
    :style="{
      top: `${originFeedback.top}px`,
      left: `${originFeedback.left}px`,
      width: `${originFeedback.width}px`,
      height: `${originFeedback.height}px`,
      borderRadius: originFeedback.radius
    }"
    data-navigation-origin-feedback
    aria-hidden="true"
  >
    <Icon name="line-md:loading-loop" class="size-4 shrink-0" />
    <span v-if="originFeedback.showLabel">Abrindo…</span>
  </div>

  <!-- Reforço explícito apenas quando a espera deixa de ser instantânea. No
       mobile fica acima da bottom-nav; no desktop, no canto inferior direito. -->
  <Transition
    enter-active-class="transition duration-150 ease-out"
    enter-from-class="translate-y-2 opacity-0"
    leave-active-class="transition duration-100 ease-in"
    leave-to-class="translate-y-2 opacity-0"
  >
    <div
      v-if="active && delayed"
      class="pointer-events-none fixed bottom-[calc(5rem+env(safe-area-inset-bottom,0px))] left-1/2 z-[100] flex max-w-[calc(100vw-2rem)] -translate-x-1/2 items-center gap-2 rounded-full border border-ink-foreground/20 bg-ink px-4 py-3 text-sm font-semibold whitespace-nowrap text-ink-foreground shadow-xl md:bottom-6 md:left-auto md:right-6 md:translate-x-0"
      data-navigation-delayed-feedback
      aria-hidden="true"
    >
      <Icon name="line-md:loading-loop" class="size-4 shrink-0" />
      <span>{{ delayedMessage }}</span>
    </div>
  </Transition>

  <p class="sr-only" role="status" aria-live="polite" aria-atomic="true">
    {{ announcement }}
  </p>
</template>
