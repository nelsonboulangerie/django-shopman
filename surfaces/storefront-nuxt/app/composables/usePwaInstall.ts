import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const DISMISS_STORAGE_KEY = 'storefront-pwa-install-dismissed-until'
const DISMISS_DAYS = 7

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed', platform: string }>
}

interface NavigatorWithStandalone extends Navigator {
  standalone?: boolean
}

export function isPwaInviteRouteExcluded (path: string): boolean {
  return path === '/finalizar' || path.startsWith('/finalizar/') || path.startsWith('/pedido/')
}

export function usePwaInstall (options: { now?: () => number } = {}) {
  const now = options.now || Date.now
  const deferredPrompt = ref<BeforeInstallPromptEvent | null>(null)
  const isStandalone = ref(false)
  const isIos = ref(false)
  const dismissedUntil = ref<number | null>(null)

  const isDismissed = computed(() => (dismissedUntil.value || 0) > now())
  const canInstall = computed(() => Boolean(deferredPrompt.value) && !isStandalone.value)

  function readEnvironment () {
    const ua = navigator.userAgent
    isIos.value = /iPad|iPhone|iPod/.test(ua)
      || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
    isStandalone.value = window.matchMedia('(display-mode: standalone)').matches
      || Boolean((navigator as NavigatorWithStandalone).standalone)
    const stored = Number.parseInt(localStorage.getItem(DISMISS_STORAGE_KEY) || '', 10)
    dismissedUntil.value = Number.isFinite(stored) ? stored : null
  }

  function suppressForSevenDays () {
    const until = now() + DISMISS_DAYS * 24 * 60 * 60 * 1000
    dismissedUntil.value = until
    localStorage.setItem(DISMISS_STORAGE_KEY, String(until))
  }

  function onBeforeInstallPrompt (event: Event) {
    event.preventDefault()
    deferredPrompt.value = event as BeforeInstallPromptEvent
  }

  function onAppInstalled () {
    deferredPrompt.value = null
    isStandalone.value = true
  }

  async function install () {
    const prompt = deferredPrompt.value
    if (!prompt) return false
    await prompt.prompt()
    const choice = await prompt.userChoice
    deferredPrompt.value = null
    if (choice.outcome === 'accepted') isStandalone.value = true
    return choice.outcome === 'accepted'
  }

  onMounted(() => {
    readEnvironment()
    window.addEventListener('beforeinstallprompt', onBeforeInstallPrompt)
    window.addEventListener('appinstalled', onAppInstalled)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('beforeinstallprompt', onBeforeInstallPrompt)
    window.removeEventListener('appinstalled', onAppInstalled)
  })

  return {
    canInstall,
    install,
    isStandalone,
    isIos,
    dismissedUntil,
    isDismissed,
    markShown: suppressForSevenDays,
    dismiss: suppressForSevenDays
  }
}
