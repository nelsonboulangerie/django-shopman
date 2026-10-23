// Push instantâneo do acompanhamento (G1): o composable abre um EventSource
// same-origin no BFF e chama onPush a cada evento. Testado isoladamente
// (connect/close manuais — fora de componente, os hooks de ciclo de vida não
// registram) com um EventSource fake.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mockNuxtImport } from '@nuxt/test-utils/runtime'

mockNuxtImport('useShopmanApiPath', () => () => (path: string) => path)

class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  withCredentials: boolean
  listeners: Record<string, Array<() => void>> = {}
  onerror: ((e?: unknown) => void) | null = null
  onopen: ((e?: unknown) => void) | null = null
  readyState = 0
  closed = false

  constructor (url: string, init?: { withCredentials?: boolean }) {
    this.url = url
    this.withCredentials = Boolean(init?.withCredentials)
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

  // O navegador desistiu: status não-200 na (re)conexão, como o 502 de deploy.
  fail () { this.readyState = 2; this.onerror?.() }
}

async function loadComposable () {
  const mod = await import('~/composables/useOrderTrackingStream')
  return mod.useOrderTrackingStream
}

describe('useOrderTrackingStream', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource as unknown as typeof EventSource)
  })

  it('conecta same-origin em /sse/pedido/<ref> com withCredentials', async () => {
    const useOrderTrackingStream = await loadComposable()
    const { connect } = useOrderTrackingStream(() => 'ORD-42', () => {})
    connect()

    expect(FakeEventSource.instances).toHaveLength(1)
    const es = FakeEventSource.instances[0]!
    expect(es.url).toBe('/sse/pedido/ORD-42')
    expect(es.withCredentials).toBe(true)
  })

  it('chama onPush nos eventos order-update e message', async () => {
    const useOrderTrackingStream = await loadComposable()
    const onPush = vi.fn()
    const { connect } = useOrderTrackingStream(() => 'ORD-1', onPush)
    connect()

    const es = FakeEventSource.instances[0]!
    es.emit('order-update')
    es.emit('message')
    expect(onPush).toHaveBeenCalledTimes(2)
  })

  it('encoda o ref na URL', async () => {
    const useOrderTrackingStream = await loadComposable()
    const { connect } = useOrderTrackingStream(() => 'ORD/42 A', () => {})
    connect()
    expect(FakeEventSource.instances[0]!.url).toBe('/sse/pedido/ORD%2F42%20A')
  })

  it('não conecta sem ref', async () => {
    const useOrderTrackingStream = await loadComposable()
    const { connect } = useOrderTrackingStream(() => '', () => {})
    connect()
    expect(FakeEventSource.instances).toHaveLength(0)
  })

  it('não abre uma segunda conexão em connect() repetido', async () => {
    const useOrderTrackingStream = await loadComposable()
    const { connect } = useOrderTrackingStream(() => 'ORD-1', () => {})
    connect()
    connect()
    expect(FakeEventSource.instances).toHaveLength(1)
  })

  it('close() fecha o EventSource e permite reconectar depois', async () => {
    const useOrderTrackingStream = await loadComposable()
    const { connect, close } = useOrderTrackingStream(() => 'ORD-1', () => {})
    connect()
    const first = FakeEventSource.instances[0]!
    close()
    expect(first.closed).toBe(true)

    connect()
    expect(FakeEventSource.instances).toHaveLength(2)
  })

  it('degrada em silêncio se o construtor do EventSource lançar', async () => {
    vi.stubGlobal('EventSource', class {
      constructor () { throw new Error('no SSE') }
      close () {}
    } as unknown as typeof EventSource)
    const useOrderTrackingStream = await loadComposable()
    const { connect, close } = useOrderTrackingStream(() => 'ORD-1', () => {})
    expect(() => connect()).not.toThrow()
    expect(() => close()).not.toThrow()
  })

  describe('reconexão (laudo 23/10, U3)', () => {
    beforeEach(() => { vi.useFakeTimers() })
    afterEach(() => { vi.useRealTimers() })

    it('depois de um 502 que fecha o stream, abre um EventSource novo com backoff', async () => {
      const useOrderTrackingStream = await loadComposable()
      const { connect, close } = useOrderTrackingStream(() => 'ORD-1', () => {})
      connect()
      FakeEventSource.instances[0]!.open()
      FakeEventSource.instances[0]!.fail()

      expect(FakeEventSource.instances).toHaveLength(1)
      vi.advanceTimersByTime(1_999)
      expect(FakeEventSource.instances).toHaveLength(1)
      vi.advanceTimersByTime(1)
      expect(FakeEventSource.instances).toHaveLength(2)

      // Caiu de novo sem abrir: a espera dobra.
      FakeEventSource.instances[1]!.fail()
      vi.advanceTimersByTime(3_999)
      expect(FakeEventSource.instances).toHaveLength(2)
      vi.advanceTimersByTime(1)
      expect(FakeEventSource.instances).toHaveLength(3)
      close()
    })

    it('ao reabrir, refaz o fetch canônico (onPush) para cobrir o que passou', async () => {
      const useOrderTrackingStream = await loadComposable()
      const onPush = vi.fn()
      const { connect, close } = useOrderTrackingStream(() => 'ORD-1', onPush)
      connect()
      FakeEventSource.instances[0]!.open()
      expect(onPush).not.toHaveBeenCalled() // a primeira abertura não é reconexão

      FakeEventSource.instances[0]!.fail()
      vi.advanceTimersByTime(2_000)
      FakeEventSource.instances[1]!.open()
      expect(onPush).toHaveBeenCalledTimes(1)
      close()
    })

    it('o teto da espera é 60 s', async () => {
      const useOrderTrackingStream = await loadComposable()
      const { connect, close } = useOrderTrackingStream(() => 'ORD-1', () => {})
      connect()
      FakeEventSource.instances[0]!.open()
      for (let i = 0; i < 8; i++) {
        FakeEventSource.instances.at(-1)!.fail()
        vi.advanceTimersByTime(60_000)
      }
      const before = FakeEventSource.instances.length
      FakeEventSource.instances.at(-1)!.fail()
      vi.advanceTimersByTime(59_999)
      expect(FakeEventSource.instances).toHaveLength(before)
      vi.advanceTimersByTime(1)
      expect(FakeEventSource.instances).toHaveLength(before + 1)
      close()
    })

    it('canal que nunca abriu (convidado, 404) desiste e deixa o poll', async () => {
      const useOrderTrackingStream = await loadComposable()
      const { connect, close } = useOrderTrackingStream(() => 'ORD-1', () => {})
      connect()
      for (let i = 0; i < 10; i++) {
        FakeEventSource.instances.at(-1)!.fail()
        vi.advanceTimersByTime(60_000)
      }
      // 1 inicial + 5 novas tentativas, e para.
      expect(FakeEventSource.instances).toHaveLength(6)
      close()
    })

    it('stream-error do Django vira backoff, não o laço de 3 s do navegador', async () => {
      const useOrderTrackingStream = await loadComposable()
      const { connect, close } = useOrderTrackingStream(() => 'ORD-1', () => {})
      connect()
      const first = FakeEventSource.instances[0]!
      first.open()
      first.emit('stream-error')
      expect(first.closed).toBe(true)
      vi.advanceTimersByTime(2_000)
      expect(FakeEventSource.instances).toHaveLength(2)
      close()
    })

    it('reconnectNow() não espera o backoff e close() cancela a espera', async () => {
      const useOrderTrackingStream = await loadComposable()
      const { connect, close, reconnectNow } = useOrderTrackingStream(() => 'ORD-1', () => {})
      connect()
      FakeEventSource.instances[0]!.open()
      FakeEventSource.instances[0]!.fail()
      reconnectNow()
      expect(FakeEventSource.instances).toHaveLength(2)

      FakeEventSource.instances[1]!.fail()
      close()
      vi.advanceTimersByTime(120_000)
      expect(FakeEventSource.instances).toHaveLength(2)
    })
  })
})
