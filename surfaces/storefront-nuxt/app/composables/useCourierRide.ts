// A rota do entregador da casa no celular dele (DEV-2026-030, M2). Ver
// `~/presentation/courierRide.ts` para o que cada tela diz.
//
// Sem login e sem cookie: quem abre é o token do link e a chave deste celular, gerada uma
// vez e guardada no `localStorage` (o servidor guarda só o hash, `courier_links`). Sem
// canal de SSE para o link, a tela relê o momento a cada 15 s com a página visível e na
// volta do foco; é essa releitura que faz a tela mudar sozinha.
import {
  type CourierLocal,
  type CourierRideView,
  type CourierTheme,
  type PendingDelivery,
  type ProblemKind,
  newDeviceKey,
  parsePending,
  parseTheme,
  pendingIsDue,
  problemAck,
  UNDO_SECONDS
} from '~/presentation/courierRide'

const DEVICE_KEY = 'shopman-courier-device'
const LAST_TOKEN = 'shopman-courier-last'
const THEME_KEY = 'shopman-courier-theme'
const PENDING_KEY = 'shopman-courier-pending'
const LOCAL_PREFIX = 'shopman-courier-local:'
const POLL_MS = 15_000

function readStorage (key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStorage (key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    // Sem armazenamento (aba privada): vale o que está na memória até fechar.
  }
}

export function useCourierTheme () {
  const theme = ref<CourierTheme>('system')
  onMounted(() => { theme.value = parseTheme(readStorage(THEME_KEY)) })
  function setTheme (value: CourierTheme) {
    theme.value = value
    writeStorage(THEME_KEY, value)
  }
  return { theme, setTheme }
}

/** O último link aberto neste celular: o app instalado abre em `/rota/` e volta a ele. */
export function lastCourierToken (): string {
  return readStorage(LAST_TOKEN) || ''
}

interface FetchFailure {
  statusCode?: number
  data?: { detail?: string, moment?: string }
}

export function useCourierRide (token: Ref<string>) {
  const apiPath = useShopmanApiPath()
  const view = ref<CourierRideView | null>(null)
  const local = ref<CourierLocal & { wasOnRoute?: boolean }>({})
  const pending = ref<PendingDelivery | null>(null)
  const undoLeft = ref(0)
  const notice = ref('')
  const busy = ref(false)
  const offline = ref(false)
  let deviceKey = ''
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let undoTimer: ReturnType<typeof setInterval> | null = null
  let noticeTimer: ReturnType<typeof setTimeout> | null = null

  function ensureDeviceKey (): string {
    if (deviceKey) return deviceKey
    deviceKey = readStorage(DEVICE_KEY) || ''
    if (deviceKey.length < 32) {
      deviceKey = newDeviceKey(bytes => crypto.getRandomValues(bytes))
      writeStorage(DEVICE_KEY, deviceKey)
    }
    return deviceKey
  }

  function saveLocal () {
    if (token.value) writeStorage(LOCAL_PREFIX + token.value, JSON.stringify(local.value))
  }

  function loadLocal () {
    try {
      local.value = JSON.parse(readStorage(LOCAL_PREFIX + token.value) || '{}') || {}
    } catch {
      local.value = {}
    }
  }

  function patchLocal (patch: Partial<CourierLocal & { wasOnRoute?: boolean }>) {
    local.value = { ...local.value, ...patch }
    saveLocal()
  }

  function say (message: string, seconds = 5) {
    notice.value = message
    if (noticeTimer) clearTimeout(noticeTimer)
    noticeTimer = setTimeout(() => { notice.value = '' }, seconds * 1000)
  }

  function accept (next: CourierRideView) {
    view.value = next
    offline.value = false
    if (next.moment === 'route' || next.moment === 'back') {
      if (!local.value.wasOnRoute) patchLocal({ wasOnRoute: true })
    }
  }

  async function call (path: string, body?: Record<string, unknown>): Promise<CourierRideView | null> {
    const url = apiPath(`/api/v1/courier/rides/${encodeURIComponent(token.value)}/${path}`)
    try {
      const next = await $fetch<CourierRideView>(url, {
        method: body ? 'POST' : 'GET',
        body,
        credentials: 'omit',
        headers: { 'X-Courier-Device': ensureDeviceKey(), accept: 'application/json' }
      })
      accept(next)
      return next
    } catch (error) {
      const failure = error as FetchFailure
      const status = failure.statusCode || 0
      const data = failure.data || {}
      if (status === 404 || status === 400 || status === 403) {
        view.value = { moment: (data.moment as CourierRideView['moment']) || 'unknown', detail: data.detail }
        return view.value
      }
      if (status === 409) {
        say(data.detail || 'Não deu agora. Tente de novo.')
        if (data.moment === 'confirm') view.value = { ...(view.value || {}), moment: 'confirm' }
        return null
      }
      offline.value = true
      say('Sem conexão. A tela tenta de novo sozinha.', 6)
      return null
    }
  }

  async function refresh () {
    if (!token.value) return
    await call('')
  }

  async function claim () {
    busy.value = true
    try {
      await call('claim/', {})
    } finally {
      busy.value = false
    }
  }

  async function depart () {
    busy.value = true
    try {
      await call('events/', { action: 'depart' })
    } finally {
      busy.value = false
    }
  }

  function arrive (ref: string) {
    patchLocal({ arrivedRef: ref })
  }

  function leaveDoor () {
    patchLocal({ arrivedRef: null, noAnswerRef: null })
  }

  // ── Entreguei + Desfazer ──────────────────────────────────────────────────

  async function flushPending () {
    const due = pending.value
    if (!due) return
    pending.value = null
    writeStorage(PENDING_KEY, null)
    if (undoTimer) clearInterval(undoTimer)
    undoLeft.value = 0
    const next = await call('events/', { action: 'deliver', order_ref: due.orderRef })
    if (next) patchLocal({ arrivedRef: null, noAnswerRef: null })
  }

  function startUndoClock () {
    if (undoTimer) clearInterval(undoTimer)
    const tick = () => {
      const due = pending.value
      if (!due) return
      const left = Math.max(0, UNDO_SECONDS - Math.floor((Date.now() - due.at) / 1000))
      undoLeft.value = left
      if (pendingIsDue(due, Date.now())) void flushPending()
    }
    tick()
    undoTimer = setInterval(tick, 250)
  }

  function deliver (orderRef: string, code: string) {
    pending.value = { token: token.value, orderRef, code, at: Date.now() }
    writeStorage(PENDING_KEY, JSON.stringify(pending.value))
    startUndoClock()
  }

  function undo () {
    pending.value = null
    writeStorage(PENDING_KEY, null)
    if (undoTimer) clearInterval(undoTimer)
    undoLeft.value = 0
  }

  // ── Problema ──────────────────────────────────────────────────────────────

  async function problem (orderRef: string, kind: ProblemKind, payment = '') {
    busy.value = true
    try {
      const next = await call('events/', { action: 'problem', order_ref: orderRef, kind, payment })
      if (!next) return
      const stop = (next.stops || []).find(item => item.ref === orderRef)
      if (kind === 'no_answer') patchLocal({ noAnswerRef: orderRef })
      else if (stop) say(problemAck(kind, stop))
    } finally {
      busy.value = false
    }
  }

  function answered () {
    patchLocal({ noAnswerRef: null })
  }

  function seeCancelled (code: string) {
    patchLocal({ seenCancelled: [...(local.value.seenCancelled || []), code] })
  }

  function seeEnd () {
    patchLocal({ seenEnd: true })
  }

  // ── Ciclo de vida ─────────────────────────────────────────────────────────

  function onVisible () {
    if (document.visibilityState === 'visible') void refresh()
  }

  onMounted(async () => {
    if (!token.value) return
    writeStorage(LAST_TOKEN, token.value)
    loadLocal()
    const stored = parsePending(readStorage(PENDING_KEY))
    if (stored && stored.token === token.value) {
      pending.value = stored
      startUndoClock()
    }
    await refresh()
    pollTimer = setInterval(() => {
      if (document.visibilityState === 'visible' && !pending.value) void refresh()
    }, POLL_MS)
    document.addEventListener('visibilitychange', onVisible)
  })

  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer)
    if (undoTimer) clearInterval(undoTimer)
    if (noticeTimer) clearTimeout(noticeTimer)
    document.removeEventListener('visibilitychange', onVisible)
  })

  return {
    view,
    local,
    pending,
    undoLeft,
    notice,
    busy,
    offline,
    refresh,
    claim,
    depart,
    arrive,
    leaveDoor,
    deliver,
    undo,
    problem,
    answered,
    seeCancelled,
    seeEnd
  }
}
