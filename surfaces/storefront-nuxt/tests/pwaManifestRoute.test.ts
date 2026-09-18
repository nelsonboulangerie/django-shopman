import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, eventHandler, toWebHandler } from 'h3'

afterEach(() => vi.unstubAllGlobals())

const agents = {
  mac: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/153.0.0.0',
  android: 'Mozilla/5.0 (Linux; Android 15) Chrome/153.0.0.0 Mobile',
  ipad: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) Mobile/15E148'
}

describe('manifest HTTP cache boundary', () => {
  it.each([false, true])('serves one private manifest, with maskable, to every device (fallback=%s)', async fallback => {
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
    const bodies = new Set<string>()
    for (const order of [['mac', 'android', 'mac', 'ipad'], ['android', 'mac', 'android', 'ipad']] as const) {
      for (const client of order) {
        const response = await handle(new Request('http://store.test/manifest.webmanifest?v=6', {
          headers: { 'user-agent': agents[client] }
        }))
        expect(response.status).toBe(200)
        expect(response.headers.get('cache-control')).toBe('private, no-store')
        expect(response.headers.get('vary')).toBeNull()
        const body = await response.text()
        bodies.add(body)
        const manifest = JSON.parse(body)
        // O Mac também recebe o `maskable`: é dele que o Chrome tira o ícone do Dock.
        expect(manifest.icons.some((icon: { purpose: string }) => icon.purpose === 'maskable')).toBe(true)
        expect(manifest).toMatchObject({ id: '/', scope: '/', start_url: '/?source=pwa', name: fallback ? 'Nelson Boulangerie' : 'Loja de teste' })
      }
    }
    expect(bodies.size).toBe(1)
  })
})
