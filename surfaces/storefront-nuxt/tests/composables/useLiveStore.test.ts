// Loja viva (WP-L04): uma conexão por aba em /sse/loja, e cada página relê a
// própria leitura canônica quando o aviso chega, quando o stream volta, quando a
// aba volta, na consulta de reserva e na recusa do servidor. Testado fora de
// componente (start/stop manuais), com um EventSource falso e relógio falso.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mockNuxtImport } from '@nuxt/test-utils/runtime'
import { ref } from 'vue'
import { BASE_DELAY_MS, MAX_ATTEMPTS_NEVER_OPENED, STABLE_MS } from '~/composables/useOrderTrackingStream'
import {
  LIVE_STORE_MIN_INTERVAL_MS,
  LIVE_STORE_FALLBACK_POLL_MS,
  LIVE_STORE_HIDDEN_CLOSE_MS,
  LIVE_STORE_IDLE_CLOSE_MS,
  LIVE_STORE_EVENT,
  announceStoreChange,
  resetLiveStoreForTests,
  useLiveRevalidate,
  useLiveStore
} from '~/composables/useLiveStore'

mockNuxtImport('useShopmanApiPath', () => () => (path: string) => path)

class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  listeners: Record<string, Array<() => void>> = {}
  onerror: ((e?: unknown) => void) | null = null
  onopen: ((e?: unknown) => void) | null = null
  readyState = 0
  closed = false

  constructor (url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener (name: string, handler: () => void) {
    ;(this.listeners[name] ||= []).push(handler)
  }

  emit (name: string) {
    ;(this.listeners[name] || []).forEach(h => h())
  }

  close () { this.closed = true; this.readyState = 2 }

  open () { this.readyState = 1; this.onopen?.() }

  /** O navegador desistiu: status não-200, como o 502 de deploy. */
  fail () { this.readyState = 2; this.onerror?.() }

  /** Queda no meio do stream: o navegador reconecta sozinho. */
  blip () { this.readyState = 0; this.onerror?.() }
}

function last () {
  return FakeEventSource.instances[FakeEventSource.instances.length - 1]!
}

function setVisibility (state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state })
  document.dispatchEvent(new Event('visibilitychange'))
}

describe('useLiveStore', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource as unknown as typeof EventSource)
    // Sem sorteio no teste: o atraso que espalha as abas vira zero.
    vi.spyOn(Math, 'random').mockReturnValue(0)
    setVisibility('visible')
    resetLiveStoreForTests()
  })

  afterEach(() => {
    resetLiveStoreForTests()
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('abre uma conexão só, same-origin em /sse/loja, para todas as páginas', () => {
    const product = useLiveStore(() => {})
    const cards = useLiveStore(() => {})
    product.start()
    cards.start()

    expect(FakeEventSource.instances).toHaveLength(1)
    expect(last().url).toBe('/sse/loja')
  })

  it('o aviso da vitrine faz a página reler', () => {
    const onChange = vi.fn()
    useLiveStore(onChange).start()
    last().open()

    last().emit(LIVE_STORE_EVENT)
    vi.advanceTimersByTime(0)

    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith('push')
  })

  it('avisos em rajada viram uma releitura, e a seguinte respeita a janela', () => {
    const onChange = vi.fn()
    useLiveStore(onChange).start()
    last().open()

    last().emit(LIVE_STORE_EVENT)
    last().emit(LIVE_STORE_EVENT)
    last().emit(LIVE_STORE_EVENT)
    vi.advanceTimersByTime(0)
    expect(onChange).toHaveBeenCalledTimes(1)

    // Outro aviso dentro da janela: fica marcado para o fim dela, não some.
    vi.advanceTimersByTime(1_000)
    last().emit(LIVE_STORE_EVENT)
    vi.advanceTimersByTime(LIVE_STORE_MIN_INTERVAL_MS - 1_001)
    expect(onChange).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(1)
    expect(onChange).toHaveBeenCalledTimes(2)
  })

  it('espalha as releituras de um mesmo aviso entre as abas', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5)
    const onChange = vi.fn()
    useLiveStore(onChange).start()
    last().open()

    last().emit(LIVE_STORE_EVENT)
    vi.advanceTimersByTime(749)
    expect(onChange).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('a recusa do servidor relê na hora, fora da janela', () => {
    const onChange = vi.fn()
    useLiveStore(onChange).start()
    last().open()
    last().emit(LIVE_STORE_EVENT)
    vi.advanceTimersByTime(0)
    expect(onChange).toHaveBeenCalledTimes(1)

    announceStoreChange()

    expect(onChange).toHaveBeenCalledTimes(2)
    expect(onChange).toHaveBeenLastCalledWith('refusal')
  })

  it('quando o stream cai e volta, a página relê o que perdeu', () => {
    const onChange = vi.fn()
    useLiveStore(onChange).start()
    last().open()
    expect(onChange).not.toHaveBeenCalled()

    // Um stream que já estava firme cai no meio: o navegador reconecta sozinho.
    vi.advanceTimersByTime(STABLE_MS)
    last().blip()
    last().open()
    vi.advanceTimersByTime(0)

    expect(FakeEventSource.instances).toHaveLength(1)
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith('reopen')
  })

  it('stream que abre e cai em seguida não vira laço de releitura', () => {
    const onChange = vi.fn()
    useLiveStore(onChange).start()
    // Um proxy que responde 200 e fecha: sem freio, o navegador reabriria a cada
    // 3 s para sempre, e cada reabertura releria a página.
    let reopened = 0
    for (let i = 0; i < 400 && reopened < 12; i += 1) {
      const current = last()
      if (!current.closed && current.readyState !== 1) {
        current.open()
        reopened += 1
        current.blip()
      }
      vi.advanceTimersByTime(1_000)
    }
    const elapsedMs = 400 * 1_000

    // O backoff daqui assume: as tentativas se espaçam até uma por minuto. A
    // página relê nas reaberturas e na consulta de reserva (uma por minuto), e só.
    expect(reopened).toBeLessThan(12)
    expect(elapsedMs / reopened).toBeGreaterThan(30_000)
    const reserveTicks = Math.ceil(elapsedMs / LIVE_STORE_FALLBACK_POLL_MS)
    expect(onChange.mock.calls.length).toBeLessThanOrEqual(reopened + reserveTicks)
  })

  it('depois de um 502 que fecha o stream, abre um EventSource novo com backoff', () => {
    useLiveStore(() => {}).start()
    last().open()
    last().fail()

    expect(FakeEventSource.instances).toHaveLength(1)
    vi.advanceTimersByTime(BASE_DELAY_MS - 1)
    expect(FakeEventSource.instances).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(FakeEventSource.instances).toHaveLength(2)
  })

  it('com o push fora, a consulta de reserva relê em cadência calma', () => {
    const onChange = vi.fn()
    useLiveStore(onChange).start()
    // O stream nunca abre (SSE bloqueado no caminho).
    last().fail()

    // O relógio falso agenda em +1 ms o que nasce dentro de outro temporizador.
    vi.advanceTimersByTime(LIVE_STORE_FALLBACK_POLL_MS + 1)
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith('poll')

    vi.advanceTimersByTime(LIVE_STORE_FALLBACK_POLL_MS)
    expect(onChange).toHaveBeenCalledTimes(2)
  })

  it('com o push de pé, a consulta de reserva não roda', () => {
    const onChange = vi.fn()
    useLiveStore(onChange).start()
    last().open()

    vi.advanceTimersByTime(LIVE_STORE_FALLBACK_POLL_MS * 3)

    expect(onChange).not.toHaveBeenCalled()
  })

  it('stream que nunca abriu desiste depois de algumas tentativas', () => {
    useLiveStore(() => {}).start()
    for (let i = 0; i < MAX_ATTEMPTS_NEVER_OPENED + 3; i += 1) {
      last().fail()
      vi.advanceTimersByTime(60_000)
    }

    expect(FakeEventSource.instances).toHaveLength(MAX_ATTEMPTS_NEVER_OPENED + 1)
  })

  it('troca rápida de aba não derruba a conexão nem relê', () => {
    const onChange = vi.fn()
    useLiveStore(onChange).start()
    last().open()

    setVisibility('hidden')
    vi.advanceTimersByTime(LIVE_STORE_HIDDEN_CLOSE_MS - 1)
    setVisibility('visible')
    vi.advanceTimersByTime(LIVE_STORE_HIDDEN_CLOSE_MS)

    expect(last().closed).toBe(false)
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('aba esquecida solta a conexão; a volta reabre e relê uma vez só', () => {
    const onChange = vi.fn()
    useLiveStore(onChange).start()
    const first = last()
    first.open()

    setVisibility('hidden')
    vi.advanceTimersByTime(LIVE_STORE_HIDDEN_CLOSE_MS)
    expect(first.closed).toBe(true)
    // Escondida, nem a reserva roda.
    vi.advanceTimersByTime(LIVE_STORE_FALLBACK_POLL_MS * 2)
    expect(onChange).not.toHaveBeenCalled()

    setVisibility('visible')
    expect(FakeEventSource.instances).toHaveLength(2)
    last().open()
    vi.advanceTimersByTime(LIVE_STORE_MIN_INTERVAL_MS * 2)

    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith('visible')
  })

  it('trocar de página herda a conexão aberta', () => {
    const menu = useLiveStore(() => {})
    menu.start()
    last().open()

    menu.stop()
    vi.advanceTimersByTime(LIVE_STORE_IDLE_CLOSE_MS - 1)
    const product = useLiveStore(() => {})
    product.start()
    vi.advanceTimersByTime(LIVE_STORE_IDLE_CLOSE_MS)

    expect(FakeEventSource.instances).toHaveLength(1)
    expect(last().closed).toBe(false)
  })

  it('sem ninguém ouvindo, a conexão cai', () => {
    const menu = useLiveStore(() => {})
    menu.start()
    last().open()

    menu.stop()
    vi.advanceTimersByTime(LIVE_STORE_IDLE_CLOSE_MS)

    expect(last().closed).toBe(true)
  })

  it('quem só ouve a volta da aba não segura conexão nem relê por aviso', () => {
    const onChange = vi.fn()
    useLiveStore(onChange, { causes: ['visible'] }).start()

    expect(FakeEventSource.instances).toHaveLength(0)
    vi.advanceTimersByTime(LIVE_STORE_FALLBACK_POLL_MS * 2)
    expect(onChange).not.toHaveBeenCalled()

    setVisibility('hidden')
    vi.advanceTimersByTime(LIVE_STORE_HIDDEN_CLOSE_MS)
    setVisibility('visible')
    vi.advanceTimersByTime(0)

    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith('visible')
    expect(FakeEventSource.instances).toHaveLength(0)
  })

  it('releitura que falha não derruba nada, e a próxima tenta de novo', async () => {
    const onChange = vi.fn().mockRejectedValueOnce(new Error('rede')).mockResolvedValue(undefined)
    useLiveStore(onChange).start()
    last().open()

    last().emit(LIVE_STORE_EVENT)
    await vi.advanceTimersByTimeAsync(0)
    last().emit(LIVE_STORE_EVENT)
    await vi.advanceTimersByTimeAsync(LIVE_STORE_MIN_INTERVAL_MS)

    expect(onChange).toHaveBeenCalledTimes(2)
  })

  it('degrada em silêncio se o construtor do EventSource lançar', () => {
    vi.stubGlobal('EventSource', class {
      constructor () { throw new Error('no SSE') }
      close () {}
    } as unknown as typeof EventSource)
    const live = useLiveStore(() => {})

    expect(() => live.start()).not.toThrow()
    expect(() => live.stop()).not.toThrow()
  })
})

describe('useLiveRevalidate', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource as unknown as typeof EventSource)
    vi.spyOn(Math, 'random').mockReturnValue(0)
    setVisibility('visible')
    resetLiveStoreForTests()
  })

  afterEach(() => {
    resetLiveStoreForTests()
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('troca o dado no lugar, sem passar por carregando', async () => {
    const data = ref<{ label: string } | null>({ label: 'Últimas unidades' })
    useLiveRevalidate(data, async () => ({ label: 'Indisponível' })).start()

    announceStoreChange()
    await vi.advanceTimersByTimeAsync(0)

    expect(data.value).toEqual({ label: 'Indisponível' })
  })

  it('não busca enquanto a primeira carga não chegou', async () => {
    const data = ref<{ label: string } | null>(null)
    const fetchFresh = vi.fn(async () => ({ label: 'x' }))
    useLiveRevalidate(data, fetchFresh).start()

    announceStoreChange()
    await vi.advanceTimersByTimeAsync(0)

    expect(fetchFresh).not.toHaveBeenCalled()
    expect(data.value).toBeNull()
  })

  it('descarta a resposta se a página já mostra outra coisa', async () => {
    const sku = ref('TABAT')
    const data = ref<{ sku: string } | null>({ sku: 'TABAT' })
    useLiveRevalidate(data, async () => {
      const asked = sku.value
      // A cliente foi para outro produto enquanto a busca corria.
      sku.value = 'CROIS'
      data.value = { sku: 'CROIS' }
      return { sku: asked }
    }, { scope: () => sku.value }).start()

    announceStoreChange()
    await vi.advanceTimersByTimeAsync(0)

    expect(data.value).toEqual({ sku: 'CROIS' })
  })

  it('falha na releitura mantém o que a tela tinha', async () => {
    const data = ref<{ label: string } | null>({ label: 'Últimas unidades' })
    useLiveRevalidate(data, async () => { throw new Error('502') }).start()

    announceStoreChange()
    await vi.advanceTimersByTimeAsync(0)

    expect(data.value).toEqual({ label: 'Últimas unidades' })
  })
})
