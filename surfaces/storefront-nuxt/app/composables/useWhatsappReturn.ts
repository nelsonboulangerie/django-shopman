import type { AuthSessionResponse } from '~/types/shopman'

export interface WhatsappClaimResponse extends Partial<AuthSessionResponse> {
  status: 'pending' | 'done'
  redirect?: string
  device_trusted?: boolean
}

// A aba onde a pessoa apertou "Entrar com WhatsApp" é onde ela termina.
//
// A queixa dos testadores era a volta: ir ao WhatsApp, enviar a mensagem e depois
// "sair do WhatsApp de novo por um link" — que abria no navegador embutido do
// WhatsApp, enquanto esta aba seguia em "Vamos entrar?". Agora a mensagem libera
// ESTE navegador no servidor (impressão digital da sessão; ver
// `WhatsAppVerifyClaimView`), e basta perguntar ao voltar.
//
// Perguntamos quando a aba volta a ficar visível — é o momento em que a pessoa volta
// do WhatsApp ("◀ Safari" no iPhone, voltar no Android) — e devagar enquanto ela está
// na tela (WhatsApp Web ao lado, no computador). Nada de SSE: a pergunta é barata e a
// resposta muda uma vez só.
//
// O "estou esperando" mora no sessionStorage da aba, não na memória: o Safari descarta
// abas em segundo plano, e a página recarregada precisa saber que ainda espera.

const STORAGE_KEY = 'shopman:wa-return-until'
const WAIT_MS = 10 * 60 * 1000 // o código vale 10 min (DOORMAN.LINK_STATE_TTL_SECONDS)
const POLL_MS = 3000

function readUntil (): number {
  try {
    return Number(window.sessionStorage.getItem(STORAGE_KEY) || 0)
  } catch {
    return 0
  }
}

function writeUntil (value: number) {
  try {
    if (value) window.sessionStorage.setItem(STORAGE_KEY, String(value))
    else window.sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // Sem storage (aba privada restrita): a espera vale enquanto a página viver.
  }
}

export function useWhatsappReturn (onDone: (response: WhatsappClaimResponse) => void | Promise<void>) {
  const apiPath = useShopmanApiPath()
  const csrfHeaders = useShopmanCsrfHeaders()

  const waiting = ref(false)
  let until = 0
  let timer: ReturnType<typeof setInterval> | null = null
  let inFlight = false

  async function check () {
    if (!waiting.value || inFlight) return
    if (Date.now() > until) {
      stop()
      return
    }
    if (document.visibilityState !== 'visible') return
    inFlight = true
    try {
      const response = await $fetch<WhatsappClaimResponse>(apiPath('/api/v1/auth/whatsapp/claim/'), {
        method: 'POST',
        headers: await csrfHeaders(),
        credentials: 'include'
      })
      if (response?.status === 'done') {
        stop()
        await onDone(response)
      }
    } catch {
      // Rede instável ou limite de tentativas: a próxima volta pergunta de novo.
    } finally {
      inFlight = false
    }
  }

  function listen () {
    if (timer) return
    document.addEventListener('visibilitychange', check)
    window.addEventListener('focus', check)
    window.addEventListener('pageshow', check)
    timer = setInterval(check, POLL_MS)
  }

  function stop () {
    waiting.value = false
    until = 0
    writeUntil(0)
    if (timer) clearInterval(timer)
    timer = null
    if (import.meta.client) {
      document.removeEventListener('visibilitychange', check)
      window.removeEventListener('focus', check)
      window.removeEventListener('pageshow', check)
    }
  }

  /** A pessoa tocou no botão: a partir de agora, esta aba espera a mensagem. */
  function arm () {
    if (!import.meta.client) return
    until = Date.now() + WAIT_MS
    writeUntil(until)
    waiting.value = true
    listen()
  }

  onMounted(() => {
    const stored = readUntil()
    if (stored > Date.now()) {
      until = stored
      waiting.value = true
      listen()
      void check()
    } else if (stored) {
      writeUntil(0)
    }
  })

  onBeforeUnmount(() => {
    if (timer) clearInterval(timer)
    timer = null
    document.removeEventListener('visibilitychange', check)
    window.removeEventListener('focus', check)
    window.removeEventListener('pageshow', check)
  })

  return { waiting, arm, stop, check }
}
