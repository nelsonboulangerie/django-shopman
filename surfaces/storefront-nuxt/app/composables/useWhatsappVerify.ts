import { httpError } from '~/utils/httpError'

interface StartResponse {
  code: string
  message?: string
  deep_link: string
  wa_number: string
  has_context?: boolean
  has_cart_context?: boolean
}

interface StoredStart extends StartResponse {
  saved_at: number
}

const START_STORAGE_KEY = 'shopman:wa-verify-start'
const START_TTL_MS = 10 * 60 * 1000

function readStoredStart (): StoredStart | null {
  try {
    const value = JSON.parse(window.sessionStorage.getItem(START_STORAGE_KEY) || 'null') as StoredStart | null
    if (!value?.code || !value.deep_link || !value.wa_number || Date.now() - Number(value.saved_at) >= START_TTL_MS) return null
    return value
  } catch {
    return null
  }
}

function writeStoredStart (value: StoredStart | null) {
  try {
    if (value) window.sessionStorage.setItem(START_STORAGE_KEY, JSON.stringify(value))
    else window.sessionStorage.removeItem(START_STORAGE_KEY)
  } catch {
    // Sem storage, o link continua disponível enquanto a página viver.
  }
}

export type WhatsappStartStatus = 'idle' | 'loading' | 'ready' | 'unavailable' | 'error'

/**
 * Login por WhatsApp (fluxo access-link): o `start` leve guarda o contexto do site
 * (sacola + destino) sob um código NB-XxXx e devolve o deep link pré-preenchido. Sem
 * SSE/bind — a identidade é o número que envia a mensagem. Ela libera a aba original,
 * consultada separadamente por `useWhatsappReturn`; o access link fica como reserva.
 */
export function useWhatsappVerify () {
  const apiPath = useShopmanApiPath()
  const csrfHeaders = useShopmanCsrfHeaders()
  const { settleCart } = useCartState()

  const code = ref('')
  const message = ref('')
  const deepLink = ref('')
  const waNumber = ref('')
  const hasCartContext = ref(false)
  const status = ref<WhatsappStartStatus>('idle')

  // Se o Safari descartou a aba durante a ida ao WhatsApp, restaura exatamente a
  // mensagem que a pessoa enviou. O relógio/estado da espera é restaurado pelo
  // useWhatsappReturn; aqui preservamos o contexto visível e o plano B manual.
  if (import.meta.client) {
    const stored = readStoredStart()
    if (stored) {
      code.value = stored.code
      message.value = stored.message || (stored.code ? `#menu ${stored.code}` : '')
      deepLink.value = stored.deep_link
      waNumber.value = stored.wa_number
      hasCartContext.value = Boolean(stored.has_cart_context || stored.has_context)
      status.value = 'ready'
    }
  }

  function clear () {
    code.value = ''
    message.value = ''
    deepLink.value = ''
    waNumber.value = ''
    hasCartContext.value = false
    status.value = 'idle'
    if (import.meta.client) writeStoredStart(null)
  }

  async function start (next = '') {
    clear()
    status.value = 'loading'
    try {
      const cart = await settleCart().catch(() => null)
      const res = await $fetch<StartResponse>(apiPath('/api/v1/auth/whatsapp/start/'), {
        method: 'POST',
        headers: await csrfHeaders(),
        credentials: 'include',
        body: { next }
      })
      const cartNeedsContext = Boolean(cart && cart.items_count > 0 && !cart.is_empty)
      hasCartContext.value = Boolean(res.has_cart_context || res.has_context)
      if (cartNeedsContext && !hasCartContext.value) {
        code.value = ''
        message.value = ''
        deepLink.value = ''
        waNumber.value = ''
        status.value = 'error'
        return
      }
      code.value = res.code
      message.value = res.message || (res.code ? `#menu ${res.code}` : '')
      deepLink.value = res.deep_link
      waNumber.value = res.wa_number
      status.value = 'ready'
      if (import.meta.client) {
        writeStoredStart({ ...res, message: message.value, saved_at: Date.now() })
      }
    } catch (error) {
      const { data } = httpError(error)
      status.value = data?.error_code === 'whatsapp_unavailable' ? 'unavailable' : 'error'
    }
  }

  return { code, message, deepLink, waNumber, hasCartContext, status, start, clear }
}
