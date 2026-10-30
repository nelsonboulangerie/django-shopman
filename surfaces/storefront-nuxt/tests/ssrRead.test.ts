import { afterEach, describe, expect, it, vi } from 'vitest'
import { createFetch, type $Fetch } from 'ofetch'
import { publicTwinPath } from '../server/utils/djangoProxy'
import { publicSsrReadOptions, ssrErrorCode, ssrProjectionPath, ssrReadSnapshot, traceSsrFetch } from '../server/utils/ssrRead'
import { reuseSsrRead } from '../shared/utils/ssrRead'
import type { StorefrontSsrRead } from '../shared/types/ssrRead'

function state (): StorefrontSsrRead {
  return { id: 'request-a', route: 'product', startedAt: 0, primaryPath: '/api/v1/storefront/products/FENDU/', reads: [] }
}

afterEach(() => vi.useRealTimers())

describe('seleção da leitura antecipada', () => {
  it.each([
    ['/menu', '/', '/api/v1/storefront/catalog/'],
    ['/produto/FENDU', '/', '/api/v1/storefront/products/FENDU/'],
    ['/loja/produto/P%C3%83O', '/loja/', '/loja/api/v1/storefront/products/P%C3%83O/']
  ])('preserva caminho e base em %s', (path, base, expected) => {
    expect(ssrProjectionPath(path, base)?.path).toBe(expected)
  })

  it('não abre outros caminhos nem antecipa o catálogo Continuum', () => {
    for (const path of ['/finalizar', '/conta', '/api/v1/cart/', '/produto/bad%XX']) expect(ssrProjectionPath(path)).toBeNull()
    expect(ssrProjectionPath('/menu', '/', true)).toBeNull()
    expect(ssrProjectionPath('/menu', '/', 'TRUE')).toBeNull()
    expect(ssrProjectionPath('/menu', '/', 'false')?.route).toBe('catalog')
    expect(ssrProjectionPath('/menu', '/outra/')).toBeNull()
  })

  it('a política existente do BFF exclui sessão e query', () => {
    const path = ssrProjectionPath('/produto/FENDU')!.path
    expect(publicTwinPath('GET', path, 'sessionid=customer-a', false)).toBeNull()
    expect(publicTwinPath('GET', path, 'sessionid=', false)).toBeNull()
    expect(publicTwinPath('GET', path, undefined, true)).toBeNull()
    expect(publicTwinPath('GET', path, 'storefront-nuxt-color-mode=light', false)).toBeTruthy()
  })
})

describe('promessa limitada a uma requisição SSR', () => {
  it('não faz outra busca e não mistura duas visitas', async () => {
    const a = state(); const b = state()
    const payloadA = { product: { sku: 'FENDU', price_q: 100 } }
    const payloadB = { product: { sku: 'FENDU', price_q: 200 } }
    a.primary = Promise.resolve(payloadA); b.primary = Promise.resolve(payloadB)
    const fallback = vi.fn() as unknown as $Fetch
    const fetchA = reuseSsrRead(a, fallback)!; const fetchB = reuseSsrRead(b, fallback)!
    expect(fetchA(a.primaryPath)).toBe(a.primary)
    expect(await fetchA(a.primaryPath)).toBe(payloadA)
    expect(await fetchB(b.primaryPath)).toBe(payloadB)
    expect(fallback).not.toHaveBeenCalled()
    expect(reuseSsrRead(state(), fallback)).toBeUndefined()
  })

  it('delega outra URL, parâmetros, headers ou método sem reaproveitar dado', async () => {
    const value = state(); value.primary = Promise.resolve({ product: {} })
    const fallback = vi.fn().mockResolvedValue({ private: true })
    const fetch = reuseSsrRead(value, fallback as unknown as $Fetch)!
    for (const options of [{ method: 'POST' as const }, { query: { channel: 'x' } }, { headers: { cookie: 'sessionid=a' } }]) {
      expect(await fetch(value.primaryPath, options)).toEqual({ private: true })
    }
    await fetch('/api/v1/storefront/products/OTHER/')
    expect(fallback).toHaveBeenCalledTimes(4)
  })

  it('conserva a falha para a página, sem convertê-la em conteúdo vazio', async () => {
    const value = state(); const error = { statusCode: 503 }
    value.primary = Promise.reject(error)
    const fetch = reuseSsrRead(value, vi.fn() as unknown as $Fetch)!
    await expect(fetch(value.primaryPath)).rejects.toBe(error)
  })
})

describe('tentativas públicas com espera limitada', () => {
  it('sobrevive a uma falha transitória sem repetir imediatamente', async () => {
    vi.useFakeTimers(); vi.setSystemTime(0)
    const transport = vi.fn()
      .mockResolvedValueOnce(new Response('{"detail":"unavailable"}', { status: 503 }))
      .mockResolvedValueOnce(new Response('{"product":{"sku":"FENDU"}}', { status: 200, headers: { 'content-type': 'application/json' } }))
    const value = state()
    const fetch = traceSsrFetch(createFetch({ fetch: transport }), value, () => Date.now())
    const pending = fetch(value.primaryPath, publicSsrReadOptions())
    await vi.advanceTimersByTimeAsync(0)
    expect(transport).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(199)
    expect(transport).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(await pending).toEqual({ product: { sku: 'FENDU' } })
    expect(transport).toHaveBeenCalledTimes(2)
    expect(value.reads[0]?.statuses).toEqual([503, 200])
  })

  it.each([
    [429, undefined], [503, '120'], [503, 'Wed, 01 Jan 2031 00:00:00 GMT'], [404, undefined]
  ])('respeita status %s e Retry-After %s', async (status, retryAfter) => {
    const headers = retryAfter ? { 'retry-after': retryAfter } : undefined
    const transport = vi.fn().mockImplementation(() => Promise.resolve(new Response('{}', { status, headers })))
    const fetch = createFetch({ fetch: transport })
    await expect(fetch('/api/v1/storefront/products/FENDU/', publicSsrReadOptions())).rejects.toMatchObject({ statusCode: status })
    expect(transport).toHaveBeenCalledTimes(1)
  })

  it('não mascara indisponibilidade persistente: duas tentativas e a mesma falha', async () => {
    vi.useFakeTimers()
    const transport = vi.fn().mockImplementation(() => Promise.resolve(new Response('{}', { status: 503 })))
    const pending = createFetch({ fetch: transport })('/pdp', publicSsrReadOptions()).catch(error => error)
    await vi.runAllTimersAsync()
    expect(await pending).toMatchObject({ statusCode: 503 })
    expect(transport).toHaveBeenCalledTimes(2)
  })
})

describe('telemetria sem identidade do comprador', () => {
  it('não serializa corpo, URL, cookie ou mensagem de erro', () => {
    const value = state(); value.primary = Promise.resolve({ secret: 'not-for-logs' })
    value.reads.push({ kind: 'primary', startedAt: 10, finishedAt: 30, statuses: [503, 200] })
    const snapshot = ssrReadSnapshot(value, 40)
    expect(snapshot.reads[0]).toMatchObject({ start_ms: 10, duration_ms: 20, statuses: [503, 200] })
    expect(JSON.stringify(snapshot)).not.toMatch(/FENDU|not-for-logs|primaryPath/)
    expect(ssrErrorCode({ cause: { code: 'ECONNRESET', message: 'token=secret' } })).toBe('ECONNRESET')
    expect(ssrErrorCode({ code: 'secret', message: 'token=secret' })).toBeUndefined()
  })
})
