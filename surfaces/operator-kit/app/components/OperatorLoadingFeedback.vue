<script setup lang="ts">
// Aviso de carregamento das superfícies de operador: a irmã do `NavigationFeedback`
// da loja, com a aparência do balcão. Quando uma navegação demora, um modal diz que
// está carregando, para o operador não confundir espera com travamento.
//
// Mesmíssimo esquema da loja:
//   - só aparece depois de um limiar curto (navegação rápida não pisca o aviso);
//   - quando aparece, fica ao menos um instante (não some num clarão);
//   - um watchdog solta sozinho se a navegação não terminar (15 s);
//   - a espera começa no início da navegação (`page:loading:start`, que o roteador do
//     Nuxt chama ANTES do middleware; o middleware que lê a sessão não fica mudo) e
//     no `page:start`; `page:finish`/`page:loading:end` encerram, erro/cancelamento
//     força a soltura. Nada aqui engole a navegação: é estritamente observacional.
//
// Clique nunca inerte (DEV-2026-094): o LINK tocado fica marcado no mesmo instante
// (`aria-busy` + `data-navigation-pending`, que a suíte desenha esmaecido e com cursor
// de progresso) até a página chegar, e a barra de rota corre no topo desde o toque.
// Abaixo dos 200 ms, a marca e a barra são o sinal; acima, o modal. A barra é
// indeterminada e anda só por `transform`: o compositor a mantém andando mesmo
// quando a troca de página prende a thread principal (medido: ~380 ms numa troca de
// seção do Compras), e ela não tem fade de entrada. O `NuxtLoadingIndicator` não
// serve: entra com fade de 0,4 s e nasce com largura zero. O atalho para OUTRO app (a Central abre o PDV, o Gestor abre a Cozinha) é
// navegação de documento: o PWA não tem barra do navegador, então a marca, a barra e
// o modal são o único sinal de que o toque chegou.
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
let pendingLink: HTMLAnchorElement | null = null

function markLink (link: HTMLAnchorElement) {
  clearLink()
  pendingLink = link
  link.setAttribute("aria-busy", "true")
  link.setAttribute("data-navigation-pending", "")
}

function clearLink () {
  if (!pendingLink) return
  pendingLink.removeAttribute("aria-busy")
  pendingLink.removeAttribute("data-navigation-pending")
  pendingLink = null
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
  clearLink()
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
  clearLink()
  active.value = false
  clearRevealSchedule()
  clearHideSchedule()
  clearWatchdog()
  hide()
}

// Toque num link: marca o link e, se for outro app (outra origem), começa a espera
// aqui mesmo, porque o roteador do Nuxt nunca vai saber dessa navegação.
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
  const link = target?.closest<HTMLAnchorElement>("a[href]")
  if (
    !link
    || link.hasAttribute("download")
    || (link.getAttribute("target") && link.getAttribute("target") !== "_self")
    || link.getAttribute("aria-disabled") === "true"
  ) return

  let destination: URL
  try {
    destination = new URL(link.href, window.location.href)
  } catch {
    return
  }
  if (!/^https?:$/.test(destination.protocol)) return

  const current = new URL(window.location.href)
  if (
    destination.origin === current.origin
    && destination.pathname === current.pathname
    && destination.search === current.search
  ) return

  markLink(link)
  if (destination.origin !== current.origin) begin()
}

// Na hidratação o roteador também chama o hook; ali não há toque a responder.
const removeLoadingStart = nuxtApp.hook("page:loading:start", () => {
  if (!nuxtApp.isHydrating) begin()
})
const removeLoadingEnd = nuxtApp.hook("page:loading:end", finish)
const removePageStart = nuxtApp.hook("page:start", () => begin())
const removePageFinish = nuxtApp.hook("page:finish", finish)
const removeAppError = nuxtApp.hook("app:error", forceFinish)
const removeRouterError = router.onError(forceFinish)
const removeRouterAfterEach = router.afterEach((_to, _from, failure) => {
  // Navegações canceladas/duplicadas não disparam necessariamente page:finish.
  if (failure) forceFinish()
})

// Voltando do bfcache (o operador abriu outro app e voltou), nada fica marcado.
function pageShown () {
  forceFinish()
}

onMounted(() => {
  document.addEventListener("click", navigationIntent, true)
  window.addEventListener("pageshow", pageShown)
})

onBeforeUnmount(() => {
  document.removeEventListener("click", navigationIntent, true)
  window.removeEventListener("pageshow", pageShown)
  removeLoadingStart()
  removeLoadingEnd()
  removePageStart()
  removePageFinish()
  removeAppError()
  removeRouterError()
  removeRouterAfterEach()
  forceFinish()
})
</script>

<template>
  <div v-if="active" class="operator-route-bar" data-operator-route-bar aria-hidden="true">
    <span />
  </div>

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

/* Barra de rota: segmento que corre da esquerda para a direita, sem fade de entrada.
   Só `transform` anima, para o compositor seguir com ela durante tarefa longa. */
.operator-route-bar {
  position: fixed;
  inset: 0 0 auto 0;
  z-index: 101;
  height: 3px;
  overflow: hidden;
  pointer-events: none;
  background: color-mix(in srgb, var(--ui-primary) 22%, transparent);
}

.operator-route-bar > span {
  position: absolute;
  inset: 0 auto 0 0;
  width: 40%;
  background: var(--ui-primary);
  animation: operator-route-bar 1.1s ease-in-out infinite;
  will-change: transform;
}

/* Nasce já visível (um terço do segmento dentro da tela): o primeiro quadro depois do
   toque precisa mostrar a barra, não um trilho vazio. */
@keyframes operator-route-bar {
  from { transform: translateX(-20%); }
  to { transform: translateX(250%); }
}

@keyframes operator-loading-spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .operator-loading-spinner {
    animation: none;
  }

  /* Sem movimento, a barra fica cheia e parada: continua dizendo "carregando". */
  .operator-route-bar > span {
    width: 100%;
    animation: none;
  }
}
</style>
