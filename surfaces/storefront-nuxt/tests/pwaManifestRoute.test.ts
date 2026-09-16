import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, eventHandler, toWebHandler } from 'h3'

afterEach(() => vi.unstubAllGlobals())

const agents = {
  mac: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/153.0.0.0',
  android: 'Mozilla/5.0 (Linux; Android 15) Chrome/153.0.0.0 Mobile',
  ipad: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) Mobile/15E148'
}

describe('manifest HTTP cache boundary', () => {
  it.each([false, true])('never makes device variants shareable (fallback=%s)', async fallback => {
    vi.stubGlobal('defineEventHandler', eventHandler)
    const { default: route } = await import('../server/routes/manifest.webmanifest')
    const app = createApp().use(eventHandler(event => {
      event.$fetch = vi.fn().mockImplementation(async () => {
        if (fallback) throw new Error('upstream unavailable')
        return { home: { shop: { brand_name: 'Loja de teste' } } }
      }) as typeof event.$fetch
      return route(event)
    }))
    const handle = toWebHandler(app)
    for (const order of [['mac', 'android', 'mac', 'ipad'], ['android', 'mac', 'android', 'ipad']] as const) {
      for (const client of order) {
        const response = await handle(new Request('http://store.test/manifest.webmanifest?v=4', {
          headers: { 'user-agent': agents[client] }
        }))
        expect(response.status).toBe(200)
        expect(response.headers.get('cache-control')).toBe('private, no-store')
        expect(response.headers.get('vary')).toBe('User-Agent')
        const manifest = await response.json()
        expect(manifest.icons.some((icon: { purpose: string }) => icon.purpose === 'maskable')).toBe(client !== 'mac')
        expect(manifest).toMatchObject({ id: '/', scope: '/', start_url: '/?source=pwa', name: fallback ? 'Nelson Boulangerie' : 'Loja de teste' })
      }
    }
  })
})
