// Loja viva (WP-L04): o que a cliente lê sobre disponibilidade muda sozinho.
//
// Uma conexão só por aba, same-origin no BFF (/sse/loja), que faz streaming do
// aviso público da vitrine (`shelf-update`). O shop só publica quando muda o que
// qualquer visitante vê de um SKU, e o aviso leva esse SKU (#2784): a página que
// declara os SKUs que mostra (`skus`) só relê quando o aviso é de um deles. Aviso
// sem SKU (a lista do canal mudou) vale para todas. O aviso só diz QUANDO reler;
// cada página refaz a própria leitura canônica, que continua sendo a fonte da
// verdade (ADR-016).
//
// Cinco motivos fazem a página reler, e todos passam por aqui:
// - `push`: o aviso chegou.
// - `reopen`: o stream caiu e voltou; o que mudou nesse meio vem na releitura.
// - `visible`: a aba ficou escondida tempo bastante para o stream ser fechado.
// - `poll`: consulta de reserva, em cadência calma, só enquanto o push está fora.
// - `refusal`: o servidor recusou um gesto (409). A recusa é a verdade mais nova
//   que existe: a página relê na hora, sem esperar janela.
//
// Cada ouvinte tem a própria janela mínima entre releituras, e o `push` ganha um
// atraso aleatório curto: quando a fornada fica pronta, todas as abas abertas
// recebem o aviso no mesmo instante, e sem isso pediriam o cardápio juntas.
//
// A reconexão é a mesma do acompanhamento (`useOrderTrackingStream`): o
// EventSource que recebe status diferente de 200 fica CLOSED para sempre, então
// o CLOSED vira espera com backoff e um EventSource novo.

// A régua de reconexão é a do acompanhamento: uma só para os dois streams da loja.
// Stream que nunca abriu (SSE bloqueado no caminho) desiste e fica na reserva.
import { BASE_DELAY_MS, CAP_MS, MAX_ATTEMPTS_NEVER_OPENED, STABLE_MS } from './useOrderTrackingStream'

export type LiveStoreCause = 'push' | 'reopen' | 'visible' | 'poll' | 'refusal'

export const LIVE_STORE_EVENT = 'shelf-update'
/** Consulta de reserva: só roda com o push fora do ar. */
export const LIVE_STORE_FALLBACK_POLL_MS = 60_000
/** Janela mínima padrão entre duas releituras do mesmo ouvinte. */
export const LIVE_STORE_MIN_INTERVAL_MS = 5_000
/** Listas (cardápio, busca, coleção) releem o catálogo inteiro: janela mais larga. */
export const LIVE_CATALOG_MIN_INTERVAL_MS = 15_000
/** A home é a projeção mais pesada da loja. */
export const LIVE_HOME_MIN_INTERVAL_MS = 30_000
/** Espalha as releituras de um mesmo aviso entre as abas abertas. */
export const LIVE_STORE_PUSH_JITTER_MS = 1_500
/** Aba escondida por este tempo: o stream fecha, e a volta relê a página. */
export const LIVE_STORE_HIDDEN_CLOSE_MS = 30_000
/** Sem ninguém ouvindo por este tempo, a conexão cai (troca de página não a derruba). */
export const LIVE_STORE_IDLE_CLOSE_MS = 5_000

/** `EventSource.CLOSED`, numérico para não depender do construtor global. */
const CLOSED = 2

interface Listener {
  run: (cause: LiveStoreCause) => void | Promise<void>
  minIntervalMs: number
  causes: ReadonlySet<LiveStoreCause> | null
  skus: (() => readonly string[] | null | undefined) | null
  lastRunAt: number
  timer: ReturnType<typeof setTimeout> | null
}

export interface LiveStoreOptions {
  /** Janela mínima entre duas releituras deste ouvinte. */
  minIntervalMs?: number
  /** Só estes motivos fazem este ouvinte reler; sem a lista, todos. */
  causes?: LiveStoreCause[]
  /**
   * Os SKUs que a página mostra agora. O `push` de outro SKU não faz esta página
   * reler; sem a lista (ou com ela vazia de propósito, `null`), todo aviso vale.
   */
  skus?: () => readonly string[] | null | undefined
}

const listeners = new Set<Listener>()
let streamUrl = ''
let source: EventSource | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null
let hiddenTimer: ReturnType<typeof setTimeout> | null = null
let attempt = 0
let openedAt = 0
let everOpened = false
let streamOpen = false
let closedWhileHidden = false
let resumingFromHidden = false
let idleTimer: ReturnType<typeof setTimeout> | null = null
let wired = false

function fire (listener: Listener, cause: LiveStoreCause) {
  listener.lastRunAt = Date.now()
  try {
    // A releitura que falha fica calada: a tela mantém o que tinha, e o próximo
    // aviso (ou a reserva) tenta de novo.
    void Promise.resolve(listener.run(cause)).catch(() => undefined)
  } catch {
    // idem
  }
}

/** O aviso é de um SKU que esta página não mostra? Então ela não relê. */
function unrelated (listener: Listener, cause: LiveStoreCause, sku: string | null): boolean {
  if (cause !== 'push' || !sku || !listener.skus) return false
  const shown = listener.skus()
  return Array.isArray(shown) && !shown.includes(sku)
}

function schedule (listener: Listener, cause: LiveStoreCause, sku: string | null = null) {
  if (listener.causes && !listener.causes.has(cause)) return
  if (unrelated(listener, cause, sku)) return
  if (cause === 'refusal') {
    if (listener.timer) {
      clearTimeout(listener.timer)
      listener.timer = null
    }
    fire(listener, cause)
    return
  }
  // Já há uma releitura marcada: ela cobre este aviso também.
  if (listener.timer) return
  const sinceLast = Date.now() - listener.lastRunAt
  const wait = Math.max(0, listener.minIntervalMs - sinceLast) + (cause === 'push' ? Math.random() * LIVE_STORE_PUSH_JITTER_MS : 0)
  listener.timer = setTimeout(() => {
    listener.timer = null
    fire(listener, cause)
  }, wait)
}

function notify (cause: LiveStoreCause, sku: string | null = null) {
  listeners.forEach(listener => schedule(listener, cause, sku))
}

/** O SKU do aviso (`{"sku": "CRO"}`); `null` quando o aviso vale para a vitrine inteira. */
export function liveStoreEventSku (data: unknown): string | null {
  if (typeof data !== 'string' || !data) return null
  try {
    const parsed = JSON.parse(data) as { sku?: unknown }
    return typeof parsed?.sku === 'string' && parsed.sku ? parsed.sku : null
  } catch {
    return null
  }
}

function drop () {
  streamOpen = false
  if (!source) return
  source.onopen = null
  source.onerror = null
  source.close()
  source = null
}

function clearReconnect () {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

/** Só quem relê por `push` segura a conexão; quem ouve só a volta da aba, não. */
function wantsPush () {
  for (const listener of listeners) {
    if (!listener.causes || listener.causes.has('push')) return true
  }
  return false
}

function wanted () {
  return !closedWhileHidden && wantsPush()
}

function scheduleReconnect () {
  drop()
  if (!wanted() || reconnectTimer) return
  if (openedAt && Date.now() - openedAt >= STABLE_MS) attempt = 0
  openedAt = 0
  if (!everOpened && attempt >= MAX_ATTEMPTS_NEVER_OPENED) return
  const delay = Math.min(CAP_MS, BASE_DELAY_MS * 2 ** attempt)
  attempt += 1
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    open()
  }, delay)
}

function open () {
  if (!import.meta.client || !wanted() || source || !streamUrl) return
  let created: EventSource
  try {
    created = new EventSource(streamUrl)
  } catch {
    scheduleReconnect()
    return
  }
  source = created
  const onPush = (event?: Event) => notify('push', liveStoreEventSku((event as MessageEvent | undefined)?.data))
  ;['message', LIVE_STORE_EVENT].forEach(name => created.addEventListener(name, onPush))
  // O Django recusou o stream com 200 + `stream-error`: deixar o navegador
  // reconectar sozinho vira laço de 3 s; aqui vira backoff.
  created.addEventListener('stream-error', () => {
    if (source === created) scheduleReconnect()
  })
  created.onopen = () => {
    openedAt = Date.now()
    streamOpen = true
    // Reabertura: o que passou com o push fora vem na releitura. A volta da aba
    // escondida já relê por conta própria (`visible`), não duas vezes.
    if (everOpened && !resumingFromHidden) notify('reopen')
    resumingFromHidden = false
    everOpened = true
  }
  created.onerror = () => {
    if (source !== created) return
    streamOpen = false
    // CLOSED = o navegador desistiu (status não-200). Fora isso ele mesmo
    // reconecta, e a reserva segura a tela no meio tempo.
    //
    // Stream que abre e cai em seguida (um proxy que responde 200 e fecha) faria o
    // navegador reabrir a cada 3 s para sempre, e cada reabertura é uma releitura
    // da página. Queda antes de o stream se firmar entra no backoff daqui, que só
    // zera depois de um stream estável: o laço vira uma tentativa por minuto.
    const shortLived = openedAt > 0 && Date.now() - openedAt < STABLE_MS
    if (created.readyState === CLOSED || shortLived) scheduleReconnect()
  }
}

function reconnectNow () {
  if (!wanted()) return
  if (source && source.readyState !== CLOSED) return
  clearReconnect()
  drop()
  open()
}

function onVisibility () {
  if (document.visibilityState === 'hidden') {
    if (hiddenTimer || closedWhileHidden) return
    // Troca rápida de aba não derruba nada. Aba esquecida solta a conexão: a
    // loja não segura um stream para quem não está olhando.
    hiddenTimer = setTimeout(() => {
      hiddenTimer = null
      closedWhileHidden = true
      clearReconnect()
      drop()
    }, LIVE_STORE_HIDDEN_CLOSE_MS)
    return
  }
  if (hiddenTimer) {
    clearTimeout(hiddenTimer)
    hiddenTimer = null
  }
  if (closedWhileHidden) {
    closedWhileHidden = false
    resumingFromHidden = true
    attempt = 0
    open()
    notify('visible')
    return
  }
  reconnectNow()
}

function onPollTick () {
  if (document.visibilityState !== 'visible' || streamOpen || !wantsPush()) return
  notify('poll')
}

function wire () {
  if (wired || !import.meta.client) return
  wired = true
  document.addEventListener('visibilitychange', onVisibility)
  window.addEventListener('online', reconnectNow)
  pollTimer = setInterval(onPollTick, LIVE_STORE_FALLBACK_POLL_MS)
}

function unwire () {
  if (!wired) return
  wired = false
  document.removeEventListener('visibilitychange', onVisibility)
  window.removeEventListener('online', reconnectNow)
  if (pollTimer) clearInterval(pollTimer)
  if (hiddenTimer) clearTimeout(hiddenTimer)
  if (idleTimer) clearTimeout(idleTimer)
  pollTimer = null
  hiddenTimer = null
  idleTimer = null
  closedWhileHidden = false
  resumingFromHidden = false
  clearReconnect()
  drop()
}

function add (listener: Listener) {
  if (!import.meta.client || listeners.has(listener)) return
  listeners.add(listener)
  if (idleTimer) {
    clearTimeout(idleTimer)
    idleTimer = null
  }
  wire()
  open()
}

function remove (listener: Listener) {
  if (listener.timer) clearTimeout(listener.timer)
  listener.timer = null
  if (!listeners.delete(listener)) return
  // A conexão é da aba, não da página: trocar de página não a derruba. Ela só
  // cai depois de um tempo sem ninguém que releia por push (a página seguinte
  // monta nesse intervalo e herda a conexão aberta).
  if (wantsPush() || idleTimer) return
  idleTimer = setTimeout(() => {
    idleTimer = null
    if (listeners.size === 0) unwire()
    else if (!wantsPush()) {
      clearReconnect()
      drop()
    }
  }, LIVE_STORE_IDLE_CLOSE_MS)
}

/**
 * A página relê quando a vitrine pode ter mudado. `onChange` é a releitura
 * canônica da página; o motivo vem como argumento.
 */
export function useLiveStore (
  onChange: (cause: LiveStoreCause) => void | Promise<void>,
  options: LiveStoreOptions = {}
) {
  const apiPath = useShopmanApiPath()
  if (import.meta.client) streamUrl = apiPath('/sse/loja')
  const listener: Listener = {
    run: onChange,
    minIntervalMs: options.minIntervalMs ?? LIVE_STORE_MIN_INTERVAL_MS,
    causes: options.causes ? new Set(options.causes) : null,
    skus: options.skus ?? null,
    lastRunAt: 0,
    timer: null
  }
  const start = () => add(listener)
  const stop = () => remove(listener)

  // Registra o ciclo de vida só dentro de um componente: assim o composable é
  // testável isoladamente (start/stop manuais) sem avisos de hook órfão.
  if (getCurrentInstance()) {
    onMounted(start)
    onBeforeUnmount(stop)
  }
  return { start, stop }
}

/**
 * Releitura em segundo plano de um dado de página: busca de novo e troca o valor
 * no lugar, sem passar por "carregando" (o esqueleto é da primeira carga).
 * `scope` identifica o que a página mostra agora (o SKU, a coleção): se mudou
 * enquanto a busca corria, a resposta é descartada.
 */
export function useLiveRevalidate<T> (
  data: Ref<T | null | undefined>,
  fetchFresh: () => Promise<T>,
  options: LiveStoreOptions & { scope?: () => unknown } = {}
) {
  return useLiveStore(async () => {
    if (!data.value) return
    const scope = options.scope?.()
    const fresh = await fetchFresh()
    if (!data.value || (options.scope && options.scope() !== scope)) return
    data.value = fresh
  }, options)
}

/** O servidor recusou um gesto: as páginas abertas releem agora. */
export function announceStoreChange (cause: LiveStoreCause = 'refusal') {
  if (!import.meta.client) return
  notify(cause)
}

/** Só para testes: zera o estado do módulo entre um caso e outro. */
export function resetLiveStoreForTests () {
  listeners.forEach((listener) => {
    if (listener.timer) clearTimeout(listener.timer)
  })
  listeners.clear()
  unwire()
  attempt = 0
  openedAt = 0
  everOpened = false
  streamUrl = ''
}
