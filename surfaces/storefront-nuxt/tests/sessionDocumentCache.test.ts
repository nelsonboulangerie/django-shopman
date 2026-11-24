// #3474: documento SSR renderizado com sessão nunca vira cópia compartilhada.
//
// O HTML embute o shell da cliente (nome, sacola, versão de experimento). Com o
// cookie de sessão do Django, TODA rota sai `private, no-store`; sem ele, cada
// rota segue com a política que já tinha. O teste exercita o plugin de verdade
// (`server/plugins/securityHeaders.ts`, o `render:response` do Nitro) contra
// todas as páginas de `app/pages`, então página nova entra na varredura sozinha.
import { readdirSync } from 'node:fs'
import { IncomingMessage, ServerResponse } from 'node:http'
import { Socket } from 'node:net'
import { join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createEvent, getResponseHeader, setResponseHeader, type H3Event } from 'h3'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { headerValue, type RenderHeaders } from '../server/utils/homeCompression'
import {
  documentCarriesSession,
  privateDocumentCacheControl,
  storefrontResponseHeaders
} from '../server/utils/storefrontSecurity'

vi.mock('nitropack/runtime', () => ({ defineNitroPlugin: (plugin: unknown) => plugin }))

type RenderResponse = { body: string, statusCode: number, headers: RenderHeaders }
type RenderHook = (response: RenderResponse, context: { event: H3Event }) => void | Promise<void>

// A regra de rota da home (`nuxt.config.ts`, `routeRules['/']`): o Nitro a põe no
// evento antes do render.
const HOME_ROUTE_RULE = 'private, no-transform'

const PAGES_DIR = fileURLToPath(new URL('../app/pages', import.meta.url))

function pageFiles (dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap(entry => (
    entry.isDirectory() ? pageFiles(join(dir, entry.name)) : entry.name.endsWith('.vue') ? [join(dir, entry.name)] : []
  ))
}

/** `produto/[sku].vue` → `/produto/EXEMPLO`; `conta/index.vue` → `/conta`. */
function examplePath (file: string): string {
  const segments = relative(PAGES_DIR, file).replace(/\.vue$/, '').split(sep)
    .filter(segment => segment !== 'index')
    .map(segment => segment.replace(/^\[\.{0,3}[^\]]+\]$/, 'EXEMPLO'))
  return `/${segments.join('/')}`
}

const PAGE_PATHS = [...new Set(pageFiles(PAGES_DIR).map(examplePath))].sort()
// O que também passa pelo renderer: o payload da navegação e a página de erro.
const RENDERED_PATHS = [...PAGE_PATHS, '/menu/_payload.json', '/rota-que-nao-existe-123']

let renderHook: RenderHook

beforeAll(async () => {
  const hooks: Record<string, RenderHook> = {}
  const plugin = (await import('../server/plugins/securityHeaders')).default as unknown as (nitro: unknown) => void
  plugin({ hooks: { hook: (name: string, fn: RenderHook) => { hooks[name] = fn } } })
  renderHook = hooks['render:response']!
  expect(renderHook).toBeTypeOf('function')
})

async function render (path: string, headers: Record<string, string> = {}, responseHeaders: RenderHeaders = {}): Promise<string | undefined> {
  const req = new IncomingMessage(new Socket())
  req.method = 'GET'
  req.url = path
  req.headers = headers
  const event = createEvent(req, new ServerResponse(req))
  if (path === '/') setResponseHeader(event, 'cache-control', HOME_ROUTE_RULE)
  const response: RenderResponse = {
    body: '<html></html>',
    statusCode: 200,
    headers: { 'content-type': 'text/html;charset=utf-8', ...responseHeaders }
  }
  await renderHook(response, { event })
  // O renderer do Nitro aplica `response.headers` por cima do evento: é o que vai à rede.
  const value = headerValue(response.headers, 'cache-control') ?? getResponseHeader(event, 'cache-control')
  return value === undefined ? undefined : String(value)
}

function directives (value: string | undefined): Set<string> {
  return new Set(String(value ?? '').split(',').map(part => part.split('=')[0]!.trim().toLowerCase()).filter(Boolean))
}

describe('varredura das páginas', () => {
  it('encontra as páginas do app (a varredura não está vazia)', () => {
    expect(PAGE_PATHS).toEqual(expect.arrayContaining(['/', '/menu', '/produto/EXEMPLO', '/termos', '/privacidade', '/faq', '/colecao/EXEMPLO']))
  })
})

describe('documento com sessão: private, no-store em TODA rota (#3474)', () => {
  it.each(RENDERED_PATHS)('%s com cookie de sessão sai private, no-store', async (path) => {
    const value = await render(path, { cookie: 'csrftoken=t; sessionid=cliente-a; _ga=x' })
    const parsed = directives(value)
    expect(parsed.has('private') && parsed.has('no-store'), `${path}: '${value}'`).toBe(true)
    expect(parsed.has('public'), `${path}: '${value}'`).toBe(false)
  })

  it('a sessão que nasce no próprio render também torna o documento privado', async () => {
    const value = await render('/menu', {}, { 'set-cookie': ['sessionid=nova; Path=/; HttpOnly'] })
    expect(value).toBe('private, no-store')
  })

  it('a home com sessão mantém o no-transform da regra de rota', async () => {
    expect(await render('/', { cookie: 'sessionid=cliente-a' })).toBe('private, no-store, no-transform')
  })

  it('página de capacidade com sessão mantém o max-age=0 que já tinha', async () => {
    expect(await render('/gerenciar-aviso', { cookie: 'sessionid=cliente-a' })).toBe('private, no-store, max-age=0')
  })
})

describe('anônimo: a política de cada rota não muda', () => {
  // O de antes: a regra de rota da home, as páginas pessoais e de capacidade da
  // `storefrontResponseHeaders`, e nada nas demais (cacheáveis).
  function before (path: string): string | undefined {
    if (path === '/') return HOME_ROUTE_RULE
    return storefrontResponseHeaders(false, path)['Cache-Control']
  }

  it.each(RENDERED_PATHS)('%s sem sessão sai como antes', async (path) => {
    expect(await render(path, { cookie: 'csrftoken=t; _ga=x' })).toBe(before(path))
    expect(await render(path)).toBe(before(path))
  })

  it('o cardápio, o produto e as páginas legais anônimos continuam sem no-store', async () => {
    for (const path of ['/menu', '/produto/EXEMPLO', '/termos', '/privacidade', '/faq']) {
      expect(await render(path), path).toBeUndefined()
    }
  })
})

describe('documentCarriesSession', () => {
  it('só o cookie de sessão do Django conta, pelo nome exato', () => {
    expect(documentCarriesSession('sessionid=a', undefined)).toBe(true)
    expect(documentCarriesSession('csrftoken=t; sessionid=', undefined)).toBe(true)
    expect(documentCarriesSession('xsessionid=1; csrftoken=t', undefined)).toBe(false)
    expect(documentCarriesSession(undefined, undefined)).toBe(false)
  })

  it('a resposta que cria a sessão também conta', () => {
    expect(documentCarriesSession(undefined, 'sessionid=n; Path=/')).toBe(true)
    expect(documentCarriesSession(undefined, ['csrftoken=t; Path=/', 'sessionid=n; HttpOnly'])).toBe(true)
    expect(documentCarriesSession(undefined, ['csrftoken=t; Path=/'])).toBe(false)
  })
})

describe('privateDocumentCacheControl', () => {
  it('documento sem cabeçalho sai private, no-store', () => {
    expect(privateDocumentCacheControl(undefined)).toBe('private, no-store')
    expect(privateDocumentCacheControl('')).toBe('private, no-store')
  })

  it('a home mantém o no-transform da regra de rota e ganha no-store', () => {
    expect(privateDocumentCacheControl('private, no-transform')).toBe('private, no-store, no-transform')
  })

  it('nenhuma diretiva de cache compartilhado sobrevive', () => {
    const value = privateDocumentCacheControl('public, max-age=60, s-maxage=300, stale-while-revalidate=30, no-transform')
    expect(value).toBe('private, no-store, no-transform')
    expect(value).not.toMatch(/public|max-age/)
  })

  it('o que já é private, no-store fica como está', () => {
    expect(privateDocumentCacheControl('private, no-store, max-age=0')).toBe('private, no-store, max-age=0')
  })
})
