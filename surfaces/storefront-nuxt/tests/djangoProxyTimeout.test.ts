// Prazo do BFF da loja (laudo 23/10, T9): Django que não responde vira resposta do
// próprio BFF, com `error_code` que a tela distingue de uma recusa do Django.
import { IncomingMessage, ServerResponse } from 'node:http'
import { Socket } from 'node:net'
import { createEvent } from 'h3'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  UPSTREAM_TIMEOUT_MS,
  isUpstreamTimeout,
  proxyDjangoPath
} from '../server/utils/djangoProxy'

const DJANGO = 'http://django.internal:8000'

function makeEvent (method = 'GET', path = '/api/v1/checkout/') {
  const req = new IncomingMessage(new Socket())
  req.method = method
  req.url = path
  req.headers = method === 'GET' ? {} : { cookie: 'sessionid=s1; csrftoken=tok' }
  if (method !== 'GET') {
    req.push('{}')
    req.push(null)
  }
  const res = new ServerResponse(req)
  return { event: createEvent(req, res), res }
}

function timeoutError () {
  const reason = new DOMException('The operation was aborted due to timeout', 'TimeoutError')
  return Object.assign(new Error('[GET] "http://django": <no response> timeout'), { name: 'FetchError', cause: reason })
}

describe('proxyDjangoPath — prazo do upstream', () => {
  let signals: AbortSignal[]
  let raw: ReturnType<typeof vi.fn>

  beforeEach(() => {
    signals = []
    vi.stubGlobal('useRuntimeConfig', () => ({ djangoBaseUrl: DJANGO }))
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    raw = vi.fn((_url: string, options: { signal?: AbortSignal }) => {
      if (options.signal) signals.push(options.signal)
      return Promise.resolve({ status: 200, _data: { ok: true }, headers: new Headers() })
    })
    vi.stubGlobal('$fetch', Object.assign(vi.fn(), { raw }))
  })

  afterEach(() => { vi.restoreAllMocks() })

  it('toda chamada ao Django leva um AbortSignal de prazo', async () => {
    const { event } = makeEvent()
    await proxyDjangoPath(event, '/api/v1/storefront/cart/')
    expect(signals).toHaveLength(1)
    expect(signals[0]).toBeInstanceOf(AbortSignal)
    expect(UPSTREAM_TIMEOUT_MS).toBeGreaterThan(0)
    expect(UPSTREAM_TIMEOUT_MS).toBeLessThanOrEqual(30_000)
  })

  it('Django mudo: 504 upstream_timeout, em JSON, sem exceção solta', async () => {
    raw.mockImplementationOnce(() => Promise.reject(timeoutError()))
    const { event, res } = makeEvent('POST')

    const body = await proxyDjangoPath(event, '/api/v1/checkout/')

    expect(res.statusCode).toBe(504)
    expect(body).toMatchObject({ error_code: 'upstream_timeout' })
    expect((body as { detail: string }).detail).toBeTruthy()
    expect(String(res.getHeader('content-type'))).toContain('application/json')
  })

  it('conexão recusada: 502 upstream_unreachable, distinguível do prazo', async () => {
    raw.mockImplementationOnce(() => Promise.reject(Object.assign(new Error('fetch failed'), { cause: { code: 'ECONNREFUSED' } })))
    const { event, res } = makeEvent()

    const body = await proxyDjangoPath(event, '/api/v1/storefront/home/')

    expect(res.statusCode).toBe(502)
    expect(body).toMatchObject({ error_code: 'upstream_unreachable' })
  })

  it('o prazo de verdade aborta: AbortSignal.timeout é reconhecido como prazo', async () => {
    const signal = AbortSignal.timeout(1)
    await new Promise(resolve => setTimeout(resolve, 10))
    expect(signal.aborted).toBe(true)
    expect(isUpstreamTimeout(signal.reason)).toBe(true)
    expect(isUpstreamTimeout(timeoutError())).toBe(true)
    expect(isUpstreamTimeout(new Error('fetch failed'))).toBe(false)
  })
})
