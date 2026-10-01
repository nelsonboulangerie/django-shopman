import type { Ref } from 'vue'
import {
  PWA_UPDATE_CHECK_MS,
  shouldCheckForUpdate
} from '~/presentation/pwaRuntime'

export interface PwaUpdateCheckOptions {
  enabled?: boolean
  checkIntervalMs?: number
}

/**
 * SONDAR a versão nova do app instalado. Porte da metade "sonda" do
 * `operator-kit/app/composables/usePwaAutoUpdate.ts`.
 *
 * `registration.update()` no boot, a cada 30 min e ao voltar do segundo plano,
 * ganhar foco ou reconectar. Sem isso o navegador só procura `sw.js` novo em
 * navegação de documento, e o app instalado que fica dias aberto (o iOS suspende em
 * vez de fechar) nunca faz uma.
 *
 * A metade "aplicar sozinho no ocioso" do kit NÃO foi portada: na loja quem aplica é
 * o toque do cliente no aviso (`PwaUpdatePrompt`). Ver `presentation/pwaRuntime.ts`.
 */
export function usePwaUpdateCheck (options: PwaUpdateCheckOptions = {}) {
  const enabled = options.enabled !== false
  const checkIntervalMs = Math.max(60_000, options.checkIntervalMs ?? PWA_UPDATE_CHECK_MS)

  const pwa = usePwaUpdate()
  const lastCheckAt = ref(0)

  let checkTimer: ReturnType<typeof setInterval> | null = null
  let cleanup: (() => void) | null = null

  function visible (): boolean {
    try {
      return typeof document === 'undefined' || document.visibilityState !== 'hidden'
    } catch {
      return true
    }
  }

  function online (): boolean {
    try {
      return typeof navigator === 'undefined' || navigator.onLine !== false
    } catch {
      return true
    }
  }

  /** Sonda o servidor, respeitando o piso entre chamadas. `force` pula o piso. */
  async function checkNow (force = false): Promise<boolean> {
    if (!enabled) return false
    const now = Date.now()
    if (!force && !shouldCheckForUpdate({ now, lastCheckAt: lastCheckAt.value, online: online(), visible: visible() })) {
      return false
    }
    lastCheckAt.value = now
    return pwa.checkForUpdate()
  }

  onMounted(() => {
    if (!enabled) return
    const onVisibility = () => { if (visible()) void checkNow() }
    const onFocus = () => void checkNow()
    const onOnline = () => void checkNow(true)
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('focus', onFocus)
    window.addEventListener('online', onOnline)
    checkTimer = setInterval(() => void checkNow(true), checkIntervalMs)
    // Sonda de boot: o app que acabou de abrir pergunta uma vez, sem esperar 30 min.
    void checkNow(true)

    cleanup = () => {
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('focus', onFocus)
      window.removeEventListener('online', onOnline)
      if (checkTimer) clearInterval(checkTimer)
      checkTimer = null
    }
  })

  onBeforeUnmount(() => cleanup?.())

  return {
    needRefresh: pwa.needRefresh,
    lastCheckAt: readonly(lastCheckAt) as Readonly<Ref<number>>,
    checkNow
  }
}
