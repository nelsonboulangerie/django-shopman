import { IncomingMessage, ServerResponse } from 'node:http'
import { Socket } from 'node:net'
import { createEvent, type H3Event } from 'h3'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { proxyPublicContinuumCatalog } from '../server/utils/continuumSnapshot'

function makeEvent (url = '/api/v1/storefront/continuum/v0.2/catalog-structure/', headers: Record<string, string> = {}) {
  const req = new IncomingMessage(new Socket())
  req.method = 'GET'
  req.url = url
  req.headers = headers
  const res = new ServerResponse(req)
  return { event: createEvent(req, res) as H3Event, res }
}

function upstream (status = 200) {
  return {
    status,
    _data: new TextEncoder().encode('{"ok":true}').buffer,
    headers: new Headers({
      'cache-control': 'public, max-age=30',
      'content-type': 'application/cloudevents+json; continuum=0.2; schema=1',
      etag: '"etag-1"',
      'continuum-sequence': '00000000000000000001',
      'set-cookie': 'sessionid=must-not-leak'
    })
  }
}

describe('BFF público do snapshot Continuum', () => {
  const calls: Array<{ url: string, options: any }> = []

  beforeEach(() => {
    calls.length = 0
    vi.stubGlobal('useRuntimeConfig', () => ({
      djangoBaseUrl: 'https://api.example.test',
      public: { continuumCatalogEnabled: true }
    }))
    const raw = vi.fn((url: string, options: any) => {
      calls.push({ url, options })
      return Promise.resolve(upstream())
    })
    vi.stubGlobal('$fetch', Object.assign(vi.fn(), { raw }))
  })

  it('remove credenciais, preserva o validator e repassa só headers públicos', async () => {
    const { event, res } = makeEvent(undefined, {
      cookie: 'sessionid=private',
      authorization: 'Bearer private',
      'if-none-match': '"etag-0"'
    })

    const body = await proxyPublicContinuumCatalog(event)

    expect(body).toBeInstanceOf(Uint8Array)
    expect(calls[0]?.url).toBe('https://api.example.test/api/v1/storefront/continuum/v0.2/catalog-structure/')
    expect(calls[0]?.options.headers).toEqual({
      accept: 'application/cloudevents+json; continuum=0.2; schema=1',
      'if-none-match': '"etag-0"'
    })
    expect(res.getHeader('etag')).toBe('"etag-1"')
    expect(res.getHeader('cache-control')).toBe('public, max-age=30')
    expect(res.getHeader('set-cookie')).toBeUndefined()
  })

  it('preserva 304 sem corpo', async () => {
    ;($fetch.raw as any).mockResolvedValueOnce(upstream(304))
    const { event, res } = makeEvent()
    expect(await proxyPublicContinuumCatalog(event)).toBeNull()
    expect(res.statusCode).toBe(304)
    expect(res.getHeader('etag')).toBe('"etag-1"')
  })

  it('falha fechado quando a flag está desligada ou há query livre', async () => {
    vi.stubGlobal('useRuntimeConfig', () => ({
      djangoBaseUrl: 'https://api.example.test',
      public: { continuumCatalogEnabled: 'false' }
    }))
    await expect(proxyPublicContinuumCatalog(makeEvent().event)).rejects.toMatchObject({ statusCode: 404 })

    vi.stubGlobal('useRuntimeConfig', () => ({
      djangoBaseUrl: 'https://api.example.test',
      public: { continuumCatalogEnabled: 'true' }
    }))
    await expect(proxyPublicContinuumCatalog(makeEvent('/api/x?cohort=owner').event)).rejects.toMatchObject({ statusCode: 400 })
  })

  it('não converte uma escrita recebida em leitura pública', async () => {
    const { event } = makeEvent()
    event.node.req.method = 'POST'
    await expect(proxyPublicContinuumCatalog(event)).rejects.toMatchObject({ statusCode: 405 })
    expect(calls).toHaveLength(0)
  })
})
