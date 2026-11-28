// Push instantâneo (SSE) do acompanhamento — resolve o G1 ("saiu para entrega"
// só aparecia no refresh manual). Abre um EventSource same-origin no BFF
// (/sse/pedido/<ref>), que faz streaming do eventstream do Django (canal
// order-<ref>, autorizado só p/ o dono do pedido). No push, chama onPush() — a
// página refaz o fetch canônico, mantendo o backend como fonte da verdade.
//
// É camada de push por cima do poll da página, nunca substituta (ADR-016).
//
// Reconexão (laudo 23/10, U3). O EventSource do navegador só reconecta sozinho
// quando a conexão cai NO MEIO do stream. Se a reconexão recebe status diferente
// de 200 (o 502 do BFF/ingress em todo deploy), ele fica CLOSED para sempre: o
// cliente seguia só no poll até recarregar a página. Aqui o CLOSED vira espera
// com backoff (2 s, 4 s, 8 s… teto de 60 s) e um EventSource novo; o backoff só
// zera depois de um stream que ficou de pé por `STABLE_MS`. Cada REABERTURA chama
// onPush(): o que mudou enquanto o push estava fora vem no fetch canônico.
//
// O convidado sem login não é dono do canal: o Django devolve 404 e o stream
// nunca abre. Para ele, `MAX_ATTEMPTS_NEVER_OPENED` tentativas e desiste (o poll
// é o caminho dele). Quem já abriu uma vez é dono: tenta para sempre, no teto.
// A mesma ideia do `openResilientEventSource` do operator-kit, que a loja não
// estende (superfície de cliente, harness próprio).

/** `EventSource.CLOSED` — numérico para não depender do construtor global. */
const CLOSED = 2

/** Um stream aberto por este tempo conta como saudável e zera o backoff. */
export const STABLE_MS = 30_000
export const BASE_DELAY_MS = 2_000
export const CAP_MS = 60_000
/** Canal que nunca abriu (convidado, 404): desiste depois de tantas tentativas. */
export const MAX_ATTEMPTS_NEVER_OPENED = 5

export function useOrderTrackingStream (
  orderRef: MaybeRefOrGetter<string>,
  onPush: () => void
) {
  const apiPath = useShopmanApiPath()
  let source: EventSource | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  let attempt = 0
  let openedAt = 0
  let everOpened = false
  let stopped = true

  function drop () {
    if (!source) return
    source.onopen = null
    source.onerror = null
    source.close()
    source = null
  }

  function clearTimer () {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  }

  function scheduleReconnect () {
    drop()
    if (stopped || timer) return
    if (openedAt && Date.now() - openedAt >= STABLE_MS) attempt = 0
    openedAt = 0
    if (!everOpened && attempt >= MAX_ATTEMPTS_NEVER_OPENED) return
    const delay = Math.min(CAP_MS, BASE_DELAY_MS * 2 ** attempt)
    attempt += 1
    timer = setTimeout(() => {
      timer = null
      open()
    }, delay)
  }

  function open () {
    if (!import.meta.client || stopped || source) return
    const ref = toValue(orderRef)
    if (!ref) return
    // Same-origin: o BFF faz streaming do Django (sem CORS). withCredentials
    // envia o cookie de sessão `.boulangerie` p/ o Django autorizar o canal.
    const url = apiPath(`/sse/pedido/${encodeURIComponent(ref)}`)
    let created: EventSource
    try {
      created = new EventSource(url, { withCredentials: true })
    } catch {
      scheduleReconnect()
      return
    }
    source = created
    const handler = () => onPush()
    // 'order-update' é o event type que o backend emite (shop/handlers/
    // _sse_emitters.py); 'message' cobre o default.
    ;['message', 'order-update'].forEach(name => created.addEventListener(name, handler))
    // O Django recusou o canal com 200 + `stream-error`: deixar o navegador
    // reconectar sozinho vira laço de 3 s; aqui vira backoff.
    created.addEventListener('stream-error', () => {
      if (source === created) scheduleReconnect()
    })
    created.onopen = () => {
      openedAt = Date.now()
      // Reabertura: o que passou com o push fora vem do fetch canônico.
      if (everOpened) onPush()
      everOpened = true
    }
    created.onerror = () => {
      if (source !== created) return
      // CLOSED = o navegador desistiu (status não-200). Fora isso ele mesmo
      // reconecta, e o poll da página segura a tela no meio tempo.
      if (created.readyState === CLOSED) scheduleReconnect()
    }
  }

  function connect () {
    if (!import.meta.client || source) return
    stopped = false
    open()
  }

  /** Aba voltou ou a rede voltou: tenta agora, sem esperar o backoff. */
  function reconnectNow () {
    if (stopped) return
    if (source && source.readyState !== CLOSED) return
    clearTimer()
    drop()
    open()
  }

  function close () {
    stopped = true
    clearTimer()
    drop()
  }

  function onVisible () {
    if (document.visibilityState === 'visible') reconnectNow()
  }

  // Registra o ciclo de vida só dentro de um componente — assim o composable é
  // testável isoladamente (connect/close manuais) sem avisos de hook órfão.
  if (getCurrentInstance()) {
    onMounted(() => {
      connect()
      window.addEventListener('online', reconnectNow)
      document.addEventListener('visibilitychange', onVisible)
    })
    onBeforeUnmount(() => {
      close()
      window.removeEventListener('online', reconnectNow)
      document.removeEventListener('visibilitychange', onVisible)
    })
  }

  return { connect, close, reconnectNow }
}
