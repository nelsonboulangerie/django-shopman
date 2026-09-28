<script setup lang="ts">
const WAIT_THRESHOLD_MS = 200
const MINIMUM_VISIBLE_MS = 320
const WATCHDOG_MS = 15_000

interface WaitCopy {
  title: string
  detail: string
}

const nuxtApp = useNuxtApp()
const router = useRouter()
const active = ref(false)
const visible = ref(false)
const announcement = ref('')
const waitCopy = ref<WaitCopy>({
  title: 'Atualizando a tela…',
  detail: 'Só um instante.'
})

let revealTimer: ReturnType<typeof setTimeout> | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null
let watchdogTimer: ReturnType<typeof setTimeout> | null = null
let revealFrame: number | null = null
let visibleSince = 0

function copyForDestination (destination?: URL): WaitCopy {
  const path = destination?.pathname || ''
  if (path.startsWith('/sacola')) return { title: 'Abrindo sua sacola…', detail: 'Só um instante.' }
  if (path.startsWith('/menu') || path.startsWith('/colecao')) {
    return { title: 'Abrindo o cardápio…', detail: 'Confirmando o que está disponível agora.' }
  }
  if (path.startsWith('/produto')) return { title: 'Abrindo o produto…', detail: 'Só um instante.' }
  if (path.startsWith('/finalizar')) return { title: 'Preparando a finalização…', detail: 'Só um instante.' }
  if (path.startsWith('/pedido')) return { title: 'Abrindo seu pedido…', detail: 'Só um instante.' }
  if (path.startsWith('/conta') || path.startsWith('/entrar') || path.startsWith('/a')) {
    return { title: 'Abrindo sua conta…', detail: 'Só um instante.' }
  }
  if (path === '/') return { title: 'Abrindo o início…', detail: 'Só um instante.' }
  return { title: 'Atualizando a tela…', detail: 'Só um instante.' }
}

function clearRevealSchedule () {
  if (revealTimer) clearTimeout(revealTimer)
  if (revealFrame !== null) cancelAnimationFrame(revealFrame)
  revealTimer = null
  revealFrame = null
}

function clearHideSchedule () {
  if (hideTimer) clearTimeout(hideTimer)
  hideTimer = null
}

function clearWatchdog () {
  if (watchdogTimer) clearTimeout(watchdogTimer)
  watchdogTimer = null
}

function hide () {
  visible.value = false
  announcement.value = ''
  visibleSince = 0
  clearHideSchedule()
}

function reveal () {
  if (!active.value) return
  visible.value = true
  visibleSince = performance.now()
  announcement.value = `${waitCopy.value.title} ${waitCopy.value.detail}`
}

function begin (destination?: URL) {
  if (destination) waitCopy.value = copyForDestination(destination)
  else if (!active.value && !visible.value) waitCopy.value = copyForDestination()

  if (active.value) {
    if (visible.value) announcement.value = `${waitCopy.value.title} ${waitCopy.value.detail}`
    return
  }

  active.value = true
  clearRevealSchedule()
  clearHideSchedule()
  clearWatchdog()

  if (visible.value) {
    announcement.value = `${waitCopy.value.title} ${waitCopy.value.detail}`
  } else {
    announcement.value = ''
    revealTimer = setTimeout(() => {
      revealTimer = null
      // Se a resposta chegar entre o limiar e o próximo paint, finish() cancela
      // este frame e a pessoa não vê um clarão de loading para uma navegação rápida.
      revealFrame = requestAnimationFrame(() => {
        revealFrame = null
        reveal()
      })
    }, WAIT_THRESHOLD_MS)
  }

  // Defesa contra navegação cancelada sem page:finish ou erro observável.
  watchdogTimer = setTimeout(forceFinish, WATCHDOG_MS)
}

function finish () {
  active.value = false
  clearRevealSchedule()
  clearWatchdog()

  if (!visible.value) {
    hide()
    return
  }

  const remaining = MINIMUM_VISIBLE_MS - (performance.now() - visibleSince)
  if (remaining <= 0) hide()
  else hideTimer = setTimeout(hide, remaining)
}

function forceFinish () {
  active.value = false
  clearRevealSchedule()
  clearHideSchedule()
  clearWatchdog()
  hide()
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

  // Começa no gesto, antes do middleware que espera a sacola ficar durável.
  // É estritamente observacional: nunca cancela nem engole o clique. Se uma
  // navegação anterior abortar, o segundo gesto ainda precisa chegar ao Nuxt.
  begin(destination)
}

const removePageStart = nuxtApp.hook('page:start', () => begin())
const removePageFinish = nuxtApp.hook('page:finish', finish)
const removeAppError = nuxtApp.hook('app:error', forceFinish)
const removeRouterError = router.onError(forceFinish)
const removeRouterAfterEach = router.afterEach((_to, _from, failure) => {
  // Navegações canceladas/duplicadas não disparam necessariamente page:finish.
  // Sem isto o feedback podia ficar ativo até o watchdog de 15 segundos.
  if (failure) forceFinish()
})

onMounted(() => {
  document.addEventListener('click', navigationIntent, true)
  window.addEventListener('pageshow', forceFinish)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', navigationIntent, true)
  window.removeEventListener('pageshow', forceFinish)
  removePageStart()
  removePageFinish()
  removeAppError()
  removeRouterError()
  removeRouterAfterEach()
  forceFinish()
})
</script>

<template>
  <Transition
    enter-active-class="transition-opacity duration-150 ease-out"
    enter-from-class="opacity-0"
    leave-active-class="transition-opacity duration-100 ease-in"
    leave-to-class="opacity-0"
  >
    <div
      v-if="visible"
      class="navigation-wait-scrim pointer-events-none fixed inset-0 z-[100] grid touch-none place-items-center overscroll-none px-6"
      data-navigation-wait-overlay
      aria-hidden="true"
    >
      <div
        class="w-full max-w-[19rem] rounded-3xl border border-border bg-card px-6 py-8 text-center text-card-foreground shadow-2xl"
        data-navigation-wait-card
      >
        <div class="navigation-wait-spinner mx-auto mb-4 size-10" />
        <p class="shop-title">
          {{ waitCopy.title }}
        </p>
        <p class="mt-2 text-sm leading-relaxed text-muted-foreground">
          {{ waitCopy.detail }}
        </p>
      </div>
    </div>
  </Transition>

  <p class="sr-only" role="status" aria-live="polite" aria-atomic="true">
    {{ announcement }}
  </p>
</template>

<style scoped>
.navigation-wait-scrim {
  background-color: color-mix(in oklab, var(--background) 26%, transparent);
  -webkit-backdrop-filter: blur(4px) saturate(.78) brightness(.96);
  backdrop-filter: blur(4px) saturate(.78) brightness(.96);
  animation: navigation-wait-breathe 1.8s ease-in-out infinite;
  will-change: backdrop-filter, background-color;
}

.navigation-wait-spinner {
  border: 3px solid color-mix(in oklab, var(--card-foreground) 18%, transparent);
  border-top-color: var(--card-foreground);
  border-radius: 9999px;
  animation: navigation-wait-spin .82s linear infinite;
}

@keyframes navigation-wait-breathe {
  0%, 100% {
    background-color: color-mix(in oklab, var(--background) 22%, transparent);
    -webkit-backdrop-filter: blur(4px) saturate(.78) brightness(.96);
    backdrop-filter: blur(4px) saturate(.78) brightness(.96);
  }
  50% {
    background-color: color-mix(in oklab, var(--background) 36%, transparent);
    -webkit-backdrop-filter: blur(24px) saturate(.74) brightness(.92);
    backdrop-filter: blur(24px) saturate(.74) brightness(.92);
  }
}

@keyframes navigation-wait-spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .navigation-wait-scrim {
    animation: none;
    -webkit-backdrop-filter: blur(14px) saturate(.76) brightness(.94);
    backdrop-filter: blur(14px) saturate(.76) brightness(.94);
  }

  .navigation-wait-spinner {
    animation: none;
  }
}
</style>
