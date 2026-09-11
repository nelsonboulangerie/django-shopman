import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, eventHandler, toWebHandler } from 'h3'
import { proxyDjangoPath } from '../server/utils/djangoProxy'

const upstream = vi.fn()
afterEach(() => vi.unstubAllGlobals())

async function request (headers: Record<string, string> = {}, status = 200) {
  vi.stubGlobal('useRuntimeConfig', () => ({ djangoBaseUrl: 'http://django.test' }))
  upstream.mockReset().mockResolvedValue({ status, _data: { ok: true }, headers: new Headers({
    'content-type': 'application/json', 'retry-after': '60',
    'set-cookie': 'sessionid=synthetic; Domain=.test; Path=/; HttpOnly; SameSite=Lax',
    'x-api-version': '1'
  }) })
  vi.stubGlobal('$fetch', { raw: upstream })
  const app = createApp().use(eventHandler(event => proxyDjangoPath(event, '/api/v1/checkout/')))
  return toWebHandler(app)(new Request('http://store.test/api/v1/checkout/', {
    method: 'POST', body: JSON.stringify({ idempotency_key: 'intent-A' }),
    headers: { host: 'store.test', 'content-type': 'application/json', cookie: 'csrftoken=synthetic', ...headers }
  }))
}

describe('BFF transport through an H3 request', () => {
  it('passes both key spellings unchanged and preserves retry/cache/cookie protections', async () => {
    const response = await request({ origin: 'http://store.test', 'Idempotency-Key': 'intent-A', 'X-Idempotency-Key': 'intent-A', 'X-Stock-Alert-Capability': 'opaque' }, 429)
    expect(upstream).toHaveBeenCalledTimes(1)
    expect(upstream.mock.calls[0]?.[1].headers).toMatchObject({
      'idempotency-key': 'intent-A',
      'x-idempotency-key': 'intent-A',
      'x-stock-alert-capability': 'opaque'
    })
    expect(response.status).toBe(429)
    expect(response.headers.get('retry-after')).toBe('60')
    expect(response.headers.get('cache-control')).toContain('no-store')
    expect(response.headers.get('set-cookie')).not.toContain('Domain=')
  })
  it.each(['http://foreign.test', 'http://sibling.store.test', 'null'])('refuses unsafe origin %s before touching Django', async origin => {
    const response = await request({ origin })
    expect(response.status).toBe(403)
    expect(upstream).not.toHaveBeenCalled()
  })
  it('refuses a same-site sibling using fetch metadata even without Origin', async () => {
    const response = await request({ 'sec-fetch-site': 'same-site' })
    expect(response.status).toBe(403)
    expect(upstream).not.toHaveBeenCalled()
  })
})
