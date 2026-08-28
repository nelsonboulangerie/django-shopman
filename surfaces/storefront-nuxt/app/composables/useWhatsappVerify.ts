interface StartResponse {
  code: string
  message?: string
  deep_link: string
  wa_number: string
  has_context?: boolean
  has_cart_context?: boolean
}

export type WhatsappStartStatus = 'idle' | 'loading' | 'ready' | 'error'

/**
 * Login por WhatsApp (fluxo access-link): o `start` leve guarda o contexto do site
 * (sacola + destino) sob um código NB-XxXx e devolve o deep link pré-preenchido. Sem
 * polling/SSE/bind — a identidade é o número que envia a mensagem, e o login acontece
 * pelo access link que o ManyChat devolve. A aba original só mostra a instrução.
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

  async function start (next = '') {
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
    } catch {
      status.value = 'error'
    }
  }

  return { code, message, deepLink, waNumber, hasCartContext, status, start }
}
