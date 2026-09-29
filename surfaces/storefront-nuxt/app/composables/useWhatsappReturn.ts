import type { AuthSessionResponse } from '~/types/shopman'

export interface WhatsappClaimResponse extends Partial<AuthSessionResponse> {
  status: 'pending' | 'done'
  redirect?: string
  device_trusted?: boolean
}

export type WhatsappReturnState = 'idle' | 'waiting' | 'slow' | 'offline-or-error' | 'expired'

interface StoredWait {
  version: 1
  startedAt: number
  expiresAt: number
}

// A espera pertence à aba onde o cliente começou. O registro completo (início +
// expiração), e não apenas um booleano, sobrevive ao descarte da aba pelo Safari e
// permite restaurar inclusive o estado "demorando" ou "expirou" sem inventar prazo.
const STORAGE_KEY = 'shopman:wa-return'
const WAIT_MS = 10 * 60 * 1000 // DOORMAN.LINK_STATE_TTL_SECONDS
const SLOW_AFTER_MS = 45 * 1000

function readWait (): StoredWait | null {
  try {
    const value = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) || 'null') as Partial<StoredWait> | null
    if (value?.version !== 1 || !Number.isFinite(value.startedAt) || !Number.isFinite(value.expiresAt)) return null
    return { version: 1, startedAt: Number(value.startedAt), expiresAt: Number(value.expiresAt) }
  } catch {
    return null
  }
}

function writeWait (value: StoredWait | null) {
  try {
    if (value) window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value))
    else window.sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // Aba privada restrita: a espera continua válida enquanto a página viver.
  }
}

function pollDelay (elapsed: number, failures: number): number {
  // Resposta rápida no começo; depois desacelera. Erros de rede também abrem o
  // intervalo, em vez de martelar um celular que já está sem conexão.
  const healthy = elapsed < 30_000 ? 4_000 : elapsed < 120_000 ? 7_000 : 15_000
  return Math.min(20_000, healthy + failures * 3_000)
}

export function useWhatsappReturn (onDone: (response: WhatsappClaimResponse) => void | Promise<void>) {
  const apiPath = useShopmanApiPath()
  const csrfHeaders = useShopmanCsrfHeaders()

  const state = ref<WhatsappReturnState>('idle')
  const checking = ref(false)
  const waiting = computed(() => state.value === 'waiting' || state.value === 'slow' || state.value === 'offline-or-error')
  let active: StoredWait | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  let failures = 0

  function clearTimer () {
    if (timer) clearTimeout(timer)
    timer = null
  }

  function setExpired () {
    clearTimer()
    state.value = 'expired'
    // Mantemos o registro expirado: se a aba for descartada/recarregada, a pessoa
    // vê a explicação e as saídas, em vez de voltar silenciosamente ao começo.
    if (active) writeWait(active)
  }

  function schedule () {
    clearTimer()
    if (!active || state.value === 'idle' || state.value === 'expired') return
    const remaining = active.expiresAt - Date.now()
    if (remaining <= 0) {
      setExpired()
      return
    }
    const elapsed = Date.now() - active.startedAt
    timer = setTimeout(() => { void check() }, Math.min(remaining, pollDelay(elapsed, failures)))
  }

  async function check (manual = false) {
    if (!active || checking.value || state.value === 'idle' || state.value === 'expired') return
    if (Date.now() >= active.expiresAt) {
      setExpired()
      return
    }
    if (!manual && document.visibilityState !== 'visible') {
      schedule()
      return
    }
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      failures += 1
      state.value = 'offline-or-error'
      schedule()
      return
    }

    checking.value = true
    try {
      const response = await $fetch<WhatsappClaimResponse>(apiPath('/api/v1/auth/whatsapp/claim/'), {
        method: 'POST',
        headers: await csrfHeaders(),
        credentials: 'include'
      })
      failures = 0
      if (response?.status === 'done') {
        stop()
        await onDone(response)
        return
      }
      state.value = Date.now() - active.startedAt >= SLOW_AFTER_MS ? 'slow' : 'waiting'
    } catch {
      failures += 1
      state.value = 'offline-or-error'
    } finally {
      checking.value = false
      schedule()
    }
  }

  function onReturn () {
    // ``visibilitychange`` também dispara ao SAIR para o WhatsApp. Não force uma
    // consulta justamente quando a aba ficou escondida; foco/pageshow/online seguem
    // a mesma regra para não furar o backoff em background.
    if (document.visibilityState !== 'visible') {
      schedule()
      return
    }
    void check(true)
  }

  function listen () {
    document.addEventListener('visibilitychange', onReturn)
    window.addEventListener('focus', onReturn)
    window.addEventListener('pageshow', onReturn)
    window.addEventListener('online', onReturn)
    schedule()
  }

  function unlisten () {
    document.removeEventListener('visibilitychange', onReturn)
    window.removeEventListener('focus', onReturn)
    window.removeEventListener('pageshow', onReturn)
    window.removeEventListener('online', onReturn)
  }

  function stop () {
    clearTimer()
    active = null
    failures = 0
    checking.value = false
    state.value = 'idle'
    if (import.meta.client) {
      writeWait(null)
      unlisten()
    }
  }

  /** A pessoa abriu o WhatsApp: esta aba passa a esperar a mesma mensagem. */
  function arm () {
    if (!import.meta.client) return
    clearTimer()
    unlisten()
    active = { version: 1, startedAt: Date.now(), expiresAt: Date.now() + WAIT_MS }
    writeWait(active)
    failures = 0
    state.value = 'waiting'
    listen()
  }

  onMounted(() => {
    const stored = readWait()
    if (!stored) return
    active = stored
    if (stored.expiresAt <= Date.now()) {
      state.value = 'expired'
      return
    }
    state.value = Date.now() - stored.startedAt >= SLOW_AFTER_MS ? 'slow' : 'waiting'
    listen()
    void check()
  })

  onBeforeUnmount(() => {
    clearTimer()
    unlisten()
  })

  return {
    state,
    waiting,
    checking,
    arm,
    stop,
    checkNow: () => check(true)
  }
}
