import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { installPlan, readInstallEnvironment, type InstallEnvironment, type InstallPlan } from '../utils/installGuide'

const DISMISS_STORAGE_KEY = 'storefront-pwa-install-dismissed-until'
const DISMISS_DAYS = 7
/** "Já adicionei" é resposta definitiva; o convite não volta a interromper por um ano. */
const DONE_DISMISS_DAYS = 365

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

export function usePwaInstall (options: { now?: () => number, environment?: InstallEnvironment } = {}) {
  const now = options.now || Date.now
  const deferredPrompt = ref<BeforeInstallPromptEvent | null>(null)
  const isStandalone = ref(false)
  const dismissedUntil = ref<number | null>(null)
  const environment = ref<InstallEnvironment | null>(options.environment || null)

  const isDismissed = computed(() => (dismissedUntil.value || 0) > now())

  // O caminho real DESTE navegador. Antes de o ambiente ser lido (servidor, antes do
  // mount) o plano é `none`: nada de convite piscando com instrução provisória.
  const plan = computed<InstallPlan>(() => {
    const env = environment.value
    if (!env) return { kind: 'none', invite: false, steps: [], os: 'unknown', browser: 'unknown' }
    return installPlan({ ...env, canPrompt: Boolean(deferredPrompt.value) })
  })

  function readEnvironment () {
    environment.value = options.environment || readInstallEnvironment(Boolean(deferredPrompt.value))
    isStandalone.value = window.matchMedia('(display-mode: standalone)').matches
      || Boolean((navigator as NavigatorWithStandalone).standalone)
    try {
      const stored = Number.parseInt(localStorage.getItem(DISMISS_STORAGE_KEY) || '', 10)
      dismissedUntil.value = Number.isFinite(stored) ? stored : null
    } catch {
      // Storage can be denied by browser/privacy policy. The invite stays usable
      // with in-memory state for the lifetime of this page.
      dismissedUntil.value = null
    }
  }

  function suppressFor (days: number) {
    const until = now() + days * 24 * 60 * 60 * 1000
    dismissedUntil.value = until
    try {
      localStorage.setItem(DISMISS_STORAGE_KEY, String(until))
    } catch {
      // Keep the in-memory suppression even when persistence is unavailable.
    }
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
    plan,
    install,
    isStandalone,
    dismissedUntil,
    isDismissed,
    markShown: () => suppressFor(DISMISS_DAYS),
    dismiss: () => suppressFor(DISMISS_DAYS),
    dismissAsDone: () => suppressFor(DONE_DISMISS_DAYS)
  }
}
