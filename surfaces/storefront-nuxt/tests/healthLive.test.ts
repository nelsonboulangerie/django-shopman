import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, eventHandler, toWebHandler } from 'h3'

import liveRoute from '../server/routes/health/live.get'

afterEach(() => vi.unstubAllGlobals())

describe('storefront BFF /health/live', () => {
  it('answers alive without calling the Django upstream or reading runtime config', async () => {
    const fetchSpy = vi.fn().mockRejectedValue(new Error('Django is down'))
    const runtimeConfig = vi.fn(() => {
      throw new Error('liveness must not read the upstream')
    })
    vi.stubGlobal('fetch', fetchSpy)
    vi.stubGlobal('$fetch', fetchSpy)
    vi.stubGlobal('useRuntimeConfig', runtimeConfig)
    const handle = toWebHandler(createApp().use(eventHandler(event => {
      event.$fetch = fetchSpy as unknown as typeof event.$fetch
      return liveRoute(event)
    })))

    const response = await handle(new Request('https://store.test/health/live'))

    expect(response.status).toBe(200)
    expect(await response.json()).toEqual({ status: 'ok', checks: { bff: 'ok' } })
    expect(response.headers.get('cache-control')).toBe('no-store')
    expect(response.headers.get('x-content-type-options')).toBe('nosniff')
    expect(response.headers.get('x-robots-tag')).toBe('noindex')
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(runtimeConfig).not.toHaveBeenCalled()
  })
})
