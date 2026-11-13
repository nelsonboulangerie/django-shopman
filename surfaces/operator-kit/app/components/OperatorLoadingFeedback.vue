<script setup lang="ts">
// Aviso de carregamento das superfícies de operador: a irmã do `NavigationFeedback`
// da loja, com a aparência do balcão. Quando uma navegação demora, um modal diz que
// está carregando, para o operador não confundir espera com travamento.
//
// Mesmíssimo esquema da loja:
//   - só aparece depois de um limiar curto (navegação rápida não pisca o aviso);
//   - quando aparece, fica ao menos um instante (não some num clarão);
//   - um watchdog solta sozinho se a navegação não terminar (15 s);
//   - `page:start` começa a espera, `page:finish` encerra, erro/cancelamento força a
//     soltura. Nada aqui engole a navegação: é estritamente observacional.
const WAIT_THRESHOLD_MS = 200
const MINIMUM_VISIBLE_MS = 320
const WATCHDOG_MS = 15_000

const nuxtApp = useNuxtApp()
const router = useRouter()

const active = ref(false)
const visible = ref(false)
const announcement = ref("")

// A frase é única e neutra: o aviso informa a espera em si, não o destino (as
// superfícies de operador navegam entre seções com rótulo próprio, fora da camada).
const copy = { title: "Carregando…", detail: "Só um instante." }

let revealTimer: ReturnType<typeof setTimeout> | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null
let watchdogTimer: ReturnType<typeof setTimeout> | null = null
let revealFrame: number | null = null
let visibleSince = 0

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
  announcement.value = ""
  visibleSince = 0
  clearHideSchedule()
}

function reveal () {
  if (!active.value) return
  visible.value = true
  visibleSince = performance.now()
  announcement.value = `${copy.title} ${copy.detail}`
}

function begin () {
  if (active.value) return
  active.value = true
  clearRevealSchedule()
  clearHideSchedule()
  clearWatchdog()

  announcement.value = ""
  revealTimer = setTimeout(() => {
    revealTimer = null
    // Se a resposta chegar entre o limiar e o próximo paint, finish() cancela
    // este frame e o operador não vê um clarão de carregando numa navegação rápida.
    revealFrame = requestAnimationFrame(() => {
      revealFrame = null
      reveal()
    })
  }, WAIT_THRESHOLD_MS)

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

const removePageStart = nuxtApp.hook("page:start", () => begin())
const removePageFinish = nuxtApp.hook("page:finish", finish)
const removeAppError = nuxtApp.hook("app:error", forceFinish)
const removeRouterError = router.onError(forceFinish)
const removeRouterAfterEach = router.afterEach((_to, _from, failure) => {
  // Navegações canceladas/duplicadas não disparam necessariamente page:finish.
  if (failure) forceFinish()
})

onMounted(() => {
  window.addEventListener("pageshow", forceFinish)
})

onBeforeUnmount(() => {
  window.removeEventListener("pageshow", forceFinish)
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
      class="pointer-events-none fixed inset-0 z-[100] grid touch-none place-items-center bg-background/40 backdrop-blur-sm px-6"
      data-operator-loading-overlay
      aria-hidden="true"
    >
      <div
        class="w-full max-w-[19rem] rounded-xl border border-border bg-card px-6 py-8 text-center text-card-foreground shadow-2xl"
        data-operator-loading-card
      >
        <div class="operator-loading-spinner mx-auto mb-4 size-10" />
        <p class="text-base font-semibold">
          {{ copy.title }}
        </p>
        <p class="mt-2 text-sm text-muted-foreground">
          {{ copy.detail }}
        </p>
      </div>
    </div>
  </Transition>

  <p class="sr-only" role="status" aria-live="polite" aria-atomic="true">
    {{ announcement }}
  </p>
</template>

<style scoped>
.operator-loading-spinner {
  border: 3px solid color-mix(in srgb, var(--foreground) 18%, transparent);
  border-top-color: var(--primary);
  border-radius: 9999px;
  animation: operator-loading-spin .82s linear infinite;
}

@keyframes operator-loading-spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .operator-loading-spinner {
    animation: none;
  }
}
</style>
