// Comportamento do BFF (WP-S2): além dos helpers de CSRF, exercita proxyDjangoPath
// ponta a ponta com um H3Event real (mock de http.IncomingMessage/ServerResponse)
// e $fetch.raw stubado — assertando as decisões de transporte que blindam a sessão
// e o CSRF, e o repasse fiel de status/set-cookie/content-type nas duas direções.
import { IncomingMessage, ServerResponse } from 'node:http'
import { Socket } from 'node:net'
import { createEvent, type H3Event } from 'h3'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { proxyDjangoPath, publicTwinPath } from '../server/utils/djangoProxy'

interface RawCall {
  url: string
  options: {
    method: string
    headers: Record<string, string>
    body: unknown
  }
}

const DJANGO = 'http://django.internal:8000'

function makeEvent (opts: {
  method?: string
  path?: string
  headers?: Record<string, string>
  body?: string
}): { event: H3Event, res: ServerResponse } {
  const req = new IncomingMessage(new Socket())
  req.method = opts.method || 'GET'
  req.url = opts.path || '/x'
  req.headers = opts.headers || {}
  const res = new ServerResponse(req)
  if (opts.body != null) {
    req.push(opts.body)
    req.push(null)
  }
  return { event: createEvent(req, res), res }
}

// Resposta upstream fake no formato do $fetch.raw (Headers reais + _data + status).
function upstream (status: number, data: unknown, headers: Record<string, string> = {}) {
  return { status, _data: data, headers: new Headers(headers) }
}

describe('proxyDjangoPath — transporte do BFF', () => {
  let calls: RawCall[]

  beforeEach(() => {
    calls = []
    vi.stubGlobal('useRuntimeConfig', () => ({ djangoBaseUrl: DJANGO }))
    const raw = vi.fn((url: string, options: RawCall['options']) => {
      calls.push({ url, options })
      return Promise.resolve(upstream(200, { ok: true }))
    })
    vi.stubGlobal('$fetch', Object.assign(vi.fn(), { raw }))
  })

  it('reescreve origin/referer para o Django e injeta x-csrftoken do cookie em método unsafe', async () => {
    const { event } = makeEvent({
      method: 'POST',
      path: '/api/v1/cart/skus/PAO/',
      headers: { cookie: 'sessionid=s1; csrftoken=tok-123', 'content-type': 'application/json' },
      body: JSON.stringify({ qty: 2 })
    })

    await proxyDjangoPath(event, '/api/v1/cart/skus/PAO')

    expect(calls).toHaveLength(1)
    const { url, options } = calls[0]!
    expect(url).toBe(`${DJANGO}/api/v1/cart/skus/PAO/`) // normaliza barra final
    expect(options.method).toBe('POST')
    expect(options.headers.origin).toBe(DJANGO) // não vaza o origin do cliente
    expect(options.headers.referer).toBe(`${DJANGO}/`)
    expect(options.headers['x-csrftoken']).toBe('tok-123')
    expect(options.headers.cookie).toContain('sessionid=s1')
    // (o passthrough do corpo é coberto no e2e do WP-S5: o mock de stream do
    // IncomingMessage não entrega body de forma confiável sob vitest.)
  })

  describe('gêmea pública (cache de borda)', () => {
    it.each([
      ['/api/v1/storefront/home', `${DJANGO}/api/v1/storefront/public/home/`],
      ['/api/v1/storefront/shell/', `${DJANGO}/api/v1/storefront/public/shell/`],
      ['/api/v1/storefront/catalog', `${DJANGO}/api/v1/storefront/public/catalog/`],
      ['/api/v1/storefront/catalog/paes/', `${DJANGO}/api/v1/storefront/public/catalog/paes/`],
      ['/api/v1/storefront/products/PAO-FRANCES/', `${DJANGO}/api/v1/storefront/public/products/PAO-FRANCES/`],
      // O rail de sugestões da PDP é o único request que a página faz depois do
      // SSR: vai para a gêmea de 60 s, e sem o cookie do visitante.
      ['/api/v1/storefront/products/PAO-FRANCES/recommendations/', `${DJANGO}/api/v1/storefront/public/products/PAO-FRANCES/recommendations/`]
    ])('GET sem sessão de %s vai para a gêmea, sem cookie nenhum', async (path, expected) => {
      const { event } = makeEvent({ path, headers: { cookie: 'csrftoken=tok; _ga=x' } })

      await proxyDjangoPath(event, path)

      expect(calls[0]!.url).toBe(expected)
      expect(calls[0]!.options.headers.cookie).toBeUndefined()
    })

    it.each(['/api/v1/storefront/home/', '/api/v1/storefront/products/PAO-FRANCES/'])('quem tem sessão fica em %s, com o cookie dele', async (path) => {
      const { event } = makeEvent({
        path,
        headers: { cookie: 'csrftoken=tok; sessionid=s1' }
      })

      await proxyDjangoPath(event, path)

      expect(calls[0]!.url).toBe(`${DJANGO}${path}`)
      expect(calls[0]!.options.headers.cookie).toContain('sessionid=s1')
    })

    it('query string e rotas sem gêmea ficam na rota de sempre', async () => {
      for (const path of [
        '/api/v1/storefront/home/?channel=whatsapp',
        '/api/v1/storefront/menu/',
        '/api/v1/storefront/cart/',
        '/api/v1/storefront/products/PAO/?channel=whatsapp',
        '/api/v1/storefront/products/PAO/recommendations/?channel=whatsapp'
      ]) {
        const { event } = makeEvent({ path })
        await proxyDjangoPath(event, path.split('?')[0]!)
      }

      expect(calls.map(call => call.url)).toEqual([
        `${DJANGO}/api/v1/storefront/home/?channel=whatsapp`,
        `${DJANGO}/api/v1/storefront/menu/`,
        `${DJANGO}/api/v1/storefront/cart/`,
        `${DJANGO}/api/v1/storefront/products/PAO/?channel=whatsapp`,
        `${DJANGO}/api/v1/storefront/products/PAO/recommendations/?channel=whatsapp`
      ])
    })

    it('o rail de sugestões com sessão fica na rota privada, com o cookie', async () => {
      const path = '/api/v1/storefront/products/PAO-FRANCES/recommendations/'
      const { event } = makeEvent({ path, headers: { cookie: 'sessionid=s1' } })

      await proxyDjangoPath(event, path)

      expect(calls[0]!.url).toBe(`${DJANGO}${path}`)
      expect(calls[0]!.options.headers.cookie).toContain('sessionid=s1')
    })

    it('para a gêmea do rail não vai NENHUM cookie, nem o csrftoken', async () => {
      // A gêmea recusa credencial no Django; se o BFF mandasse o csrftoken o
      // request viraria 400 e o rail ficaria vazio para todo visitante novo.
      const path = '/api/v1/storefront/products/PAO-FRANCES/recommendations/'
      const { event } = makeEvent({
        path,
        headers: { cookie: 'csrftoken=tok-123; _ga=x; _fbp=y', authorization: 'Bearer x' }
      })

      await proxyDjangoPath(event, path)

      const { url, options } = calls[0]!
      expect(url).toBe(`${DJANGO}/api/v1/storefront/public/products/PAO-FRANCES/recommendations/`)
      expect(options.headers.cookie).toBeUndefined()
      // O csrftoken viaja em cabeçalho próprio quando o cookie é lido: nenhum dos dois.
      expect(options.headers['x-csrftoken']).toBeUndefined()
      expect(options.headers['x-csrf-token']).toBeUndefined()
      expect(options.headers.authorization).toBeUndefined()
      expect(JSON.stringify(options.headers)).not.toContain('tok-123')
    })

    it('a leitura pública da PDP não substitui a sacola recebida pelo shell', async () => {
      const product = { sku: 'PAO-FRANCES', qty_in_cart: 0, is_favorite: false }
      vi.stubGlobal('$fetch', Object.assign(vi.fn(), {
        raw: vi.fn().mockResolvedValue(upstream(200, { product }))
      }))
      const { event, res } = makeEvent({ path: '/api/v1/storefront/products/PAO-FRANCES/' })

      const body = await proxyDjangoPath(event, '/api/v1/storefront/products/PAO-FRANCES/')

      expect(body).toEqual({ product })
      expect(body).not.toHaveProperty('cart')
      expect(res.getHeader('cache-control')).toBe('private, no-store')
    })

    it('mutação nunca vai para a gêmea', () => {
      expect(publicTwinPath('POST', '/api/v1/storefront/home/', undefined, false)).toBeNull()
      expect(publicTwinPath('GET', '/api/v1/storefront/home/', undefined, false)).toBe('/api/v1/storefront/public/home/')
      expect(publicTwinPath('GET', '/api/v1/storefront/home/', 'xsessionid=1', false)).toBe('/api/v1/storefront/public/home/')
    })

    it('o cookie de sessão é o que decide a gêmea do rail, e só ele', () => {
      const rail = '/api/v1/storefront/products/PAO-FRANCES/recommendations/'
      const twin = '/api/v1/storefront/public/products/PAO-FRANCES/recommendations/'

      expect(publicTwinPath('GET', rail, 'csrftoken=tok; _ga=x', false)).toBe(twin)
      expect(publicTwinPath('GET', rail, undefined, false)).toBe(twin)
      expect(publicTwinPath('GET', rail, 'sessionid=s1', false)).toBeNull()
      expect(publicTwinPath('GET', rail, 'xsessionid=1', false)).toBe(twin)
      expect(publicTwinPath('GET', rail, undefined, true)).toBeNull()
      expect(publicTwinPath('HEAD', rail, undefined, false)).toBe(twin)
      expect(publicTwinPath('POST', rail, undefined, false)).toBeNull()
      // A PDP pública separa o produto da sacola que vem no shell.
      expect(publicTwinPath('GET', '/api/v1/storefront/products/PAO-FRANCES/', undefined, false)).toBe('/api/v1/storefront/public/products/PAO-FRANCES/')
    })
  })

  it('não força origin/referer nem CSRF em GET (método safe)', async () => {
    const { event } = makeEvent({
      method: 'GET',
      path: '/api/v1/storefront/menu/?channel=web',
      headers: { cookie: 'sessionid=s1' }
    })

    await proxyDjangoPath(event, '/api/v1/storefront/menu')

    const { url, options } = calls[0]!
    expect(url).toBe(`${DJANGO}/api/v1/storefront/menu/?channel=web`) // query preservada
    expect(options.headers.origin).toBeUndefined()
    expect(options.headers['x-csrftoken']).toBeUndefined()
    expect(options.body).toBeUndefined()
  })

  it('preserva o status upstream (409) e devolve o corpo cru (sem envelope de erro)', async () => {
    ;($fetch.raw as any).mockResolvedValueOnce(upstream(409, { error_code: 'insufficient_supply' }))
    const { event, res } = makeEvent({
      method: 'PUT',
      path: '/api/v1/cart/skus/X/',
      headers: { cookie: 'csrftoken=t', 'content-type': 'application/json' },
      body: '{"qty":9}'
    })

    const data = await proxyDjangoPath(event, '/api/v1/cart/skus/X')

    expect(res.statusCode).toBe(409)
    expect(data).toEqual({ error_code: 'insufficient_supply' })
  })

  it('não repassa HTML de debug do Django quando uma API JSON falha', async () => {
    ;($fetch.raw as any).mockResolvedValueOnce(upstream(500, '<html>SECRET_DEBUG_PAGE</html>', {
      'content-type': 'text/html; charset=utf-8'
    }))
    const { event, res } = makeEvent({ method: 'GET', path: '/api/v1/storefront/home/' })

    const data = await proxyDjangoPath(event, '/api/v1/storefront/home')

    expect(res.statusCode).toBe(500)
    expect(res.getHeader('content-type')).toBe('application/json; charset=utf-8')
    expect(data).toEqual({ detail: 'Não foi possível responder agora.' })
    expect(JSON.stringify(data)).not.toContain('SECRET_DEBUG_PAGE')
  })

  it('repassa set-cookie host-only (split) e content-type da resposta upstream', async () => {
    ;($fetch.raw as any).mockResolvedValueOnce(upstream(200, { ok: true }, {
      'set-cookie': 'sessionid=new; Domain=.boulangerie.com.br; Path=/, csrftoken=fresh; Domain=.boulangerie.com.br; Path=/',
      'content-type': 'application/json'
    }))
    const { event, res } = makeEvent({ method: 'GET', path: '/api/v1/storefront/home/' })

    await proxyDjangoPath(event, '/api/v1/storefront/home')

    const setCookies = res.getHeader('set-cookie') as string[]
    expect(Array.isArray(setCookies)).toBe(true)
    expect(setCookies).toHaveLength(2) // splitCookiesString separou os dois cookies
    expect(setCookies.some(c => c.startsWith('sessionid=new'))).toBe(true)
    expect(setCookies.some(c => c.startsWith('csrftoken=fresh'))).toBe(true)
    expect(setCookies.every(c => !/;\s*domain=/i.test(c))).toBe(true)
  })

  it('preserva Server-Timing do Django e acrescenta o estágio BFF', async () => {
    ;($fetch.raw as any).mockResolvedValueOnce(upstream(200, { ok: true }, {
      'server-timing': 'projection;dur=12.30, db;dur=4.20'
    }))
    const { event, res } = makeEvent({ method: 'GET', path: '/api/v1/storefront/menu/' })

    await proxyDjangoPath(event, '/api/v1/storefront/menu')

    expect(String(res.getHeader('server-timing'))).toContain('projection;dur=12.30')
    expect(String(res.getHeader('server-timing'))).toMatch(/bff;dur=\d+\.\d{2}/)
  })

  it('faz o handshake de CSRF quando falta token em método unsafe', async () => {
    // 1ª chamada raw = seed do cart (GET) devolvendo csrftoken; 2ª = a mutação real.
    ;($fetch.raw as any)
      .mockResolvedValueOnce(upstream(200, {}, { 'set-cookie': 'csrftoken=seeded; Path=/' }))
      .mockResolvedValueOnce(upstream(200, { ok: true }))
    const { event, res } = makeEvent({
      method: 'POST',
      path: '/api/v1/cart/coupon/',
      headers: { 'content-type': 'application/json' }, // sem cookie → precisa semear
      body: '{"code":"X"}'
    })

    await proxyDjangoPath(event, '/api/v1/cart/coupon')

    expect((($fetch.raw as any).mock.calls as RawCall['options'][][]).length).toBe(2)
    const seedUrl = ($fetch.raw as any).mock.calls[0][0]
    expect(seedUrl).toContain('/api/v1/storefront/cart/')
    const rawSetCookies = res.getHeader('set-cookie')
    const setCookies = Array.isArray(rawSetCookies) ? rawSetCookies : [String(rawSetCookies)]
    expect(setCookies.every(c => !/;\s*domain=/i.test(c))).toBe(true)
    const mutationHeaders = ($fetch.raw as any).mock.calls[1][1].headers
    expect(mutationHeaders['x-csrftoken']).toBe('seeded')
  })

  it('carimba a duração da semente de CSRF em separado do total do BFF', async () => {
    ;($fetch.raw as any)
      .mockResolvedValueOnce(upstream(200, {}, { 'set-cookie': 'csrftoken=seeded; Path=/' }))
      .mockResolvedValueOnce(upstream(200, { ok: true }))
    const { event, res } = makeEvent({
      method: 'PUT',
      path: '/api/v1/cart/skus/X/',
      headers: { 'content-type': 'application/json' },
      body: '{"qty":1}'
    })

    await proxyDjangoPath(event, '/api/v1/cart/skus/X')

    expect(String(res.getHeader('server-timing'))).toMatch(/csrf;dur=\d+\.\d{2}, bff;dur=\d+\.\d{2}/)
  })

  it('sem semente, nada de csrf;dur: só o primeiro pedido unsafe paga a semente', async () => {
    const { event, res } = makeEvent({
      method: 'PUT',
      path: '/api/v1/cart/skus/X/',
      headers: { cookie: 'csrftoken=t', 'content-type': 'application/json' },
      body: '{"qty":1}'
    })

    await proxyDjangoPath(event, '/api/v1/cart/skus/X')

    expect((($fetch.raw as any).mock.calls as unknown[]).length).toBe(1)
    expect(String(res.getHeader('server-timing'))).not.toContain('csrf;dur')
  })

  it('semente de CSRF que cai na rede não derruba a mutação: ela segue sem token', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    ;($fetch.raw as any)
      .mockRejectedValueOnce(new TypeError('fetch failed'))
      .mockResolvedValueOnce(upstream(200, { cart: { items_count: 1 } }))
    const { event, res } = makeEvent({
      method: 'PUT',
      path: '/api/v1/cart/skus/X/',
      headers: { 'content-type': 'application/json' }, // navegador novo: sem cookie
      body: '{"qty":1}'
    })

    const data = await proxyDjangoPath(event, '/api/v1/cart/skus/X')

    expect(res.statusCode).toBe(200)
    expect(data).toEqual({ cart: { items_count: 1 } })
    const mutation = ($fetch.raw as any).mock.calls[1]
    expect(mutation[0]).toBe(`${DJANGO}/api/v1/cart/skus/X/`)
    expect(mutation[1].headers['x-csrftoken']).toBeUndefined()
    expect(warn).toHaveBeenCalledOnce() // a falha é dita no log do BFF, não engolida
    warn.mockRestore()
  })

  it('apresenta o segredo do BFF ao Django junto do XFF recebido, quando configurado', async () => {
    vi.stubGlobal('useRuntimeConfig', () => ({ djangoBaseUrl: DJANGO, djangoProxySecret: 's3cr3t' }))
    const { event } = makeEvent({
      method: 'GET',
      path: '/api/v1/account/',
      headers: { 'x-forwarded-for': '203.0.113.9, 10.244.0.1' }
    })

    await proxyDjangoPath(event, '/api/v1/account')

    const { options } = calls[0]!
    expect(options.headers['x-forwarded-for']).toBe('203.0.113.9, 10.244.0.1')
    expect(options.headers['x-shopman-proxy-secret']).toBe('s3cr3t')
  })

  it('não repassa segredo que o navegador escreveu, nem inventa um sem config', async () => {
    const { event } = makeEvent({
      method: 'GET',
      path: '/api/v1/account/',
      headers: { 'x-shopman-proxy-secret': 'chutado-pelo-cliente', 'x-forwarded-for': '6.6.6.6' }
    })

    await proxyDjangoPath(event, '/api/v1/account')

    const { options } = calls[0]!
    expect(options.headers['x-shopman-proxy-secret']).toBeUndefined()
  })
})
