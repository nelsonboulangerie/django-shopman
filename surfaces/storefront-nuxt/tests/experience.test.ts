// OC-21: a loja lê a versão que o servidor decidiu, e a versão não vaza entre
// visitantes (X14) nem no BFF nem no documento SSR.
import { readFileSync } from 'node:fs'
import { IncomingMessage, ServerResponse } from 'node:http'
import { Socket } from 'node:net'
import { createEvent, type H3Event } from 'h3'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { proxyDjangoPath } from '../server/utils/djangoProxy'
import {
  DEFAULT_EXPERIENCE_VARIANT,
  experienceVariant,
  hasNonDefaultExperience,
  privateDocumentCacheControl
} from '~/utils/experience'
import type { ExperienceProjection, ShellResponse } from '~/types/shopman'

function shellWith (experience?: ExperienceProjection[]): ShellResponse {
  return { shell: { experience }, cart: {} } as unknown as ShellResponse
}

describe('experienceVariant', () => {
  it('a padrão é "a"', () => {
    expect(DEFAULT_EXPERIENCE_VARIANT).toBe('a')
  })

  it('sem shell, sem campo ou sem o experimento: padrão', () => {
    expect(experienceVariant(undefined, 'prova')).toBe('a')
    expect(experienceVariant(null, 'prova')).toBe('a')
    expect(experienceVariant(shellWith(undefined), 'prova')).toBe('a')
    expect(experienceVariant(shellWith([]), 'prova')).toBe('a')
    expect(experienceVariant(shellWith([{ ref: 'outro', variant: 'b' }]), 'prova')).toBe('a')
  })

  it('a versão do experimento pedido, e só dele', () => {
    const shell = shellWith([{ ref: 'outro', variant: 'a' }, { ref: 'prova', variant: 'b' }])
    expect(experienceVariant(shell, 'prova')).toBe('b')
    expect(experienceVariant(shell, 'outro')).toBe('a')
  })

  it('variante vazia ou ilegível vira a padrão, nunca uma terceira', () => {
    expect(experienceVariant(shellWith([{ ref: 'prova', variant: '' }]), 'prova')).toBe('a')
    expect(experienceVariant(shellWith([{ ref: 'prova', variant: null as never }]), 'prova')).toBe('a')
  })
})

describe('hasNonDefaultExperience', () => {
  it('só a versão fora da padrão torna o shell de uma pessoa', () => {
    expect(hasNonDefaultExperience(undefined)).toBe(false)
    expect(hasNonDefaultExperience(shellWith(undefined))).toBe(false)
    expect(hasNonDefaultExperience(shellWith([]))).toBe(false)
    expect(hasNonDefaultExperience(shellWith([{ ref: 'prova', variant: 'a' }]))).toBe(false)
    expect(hasNonDefaultExperience(shellWith([{ ref: 'outro', variant: 'a' }, { ref: 'prova', variant: 'b' }]))).toBe(true)
  })
})

describe('privateDocumentCacheControl (X14 no documento SSR)', () => {
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
})

// ── BFF: o proxy do shell ────────────────────────────────────────────────────

const DJANGO = 'http://django.internal:8000'
const SHELL_PATH = '/api/v1/storefront/shell/'

interface RawCall { url: string, options: { headers: Record<string, string> } }

function makeEvent (headers: Record<string, string> = {}): { event: H3Event, res: ServerResponse } {
  const req = new IncomingMessage(new Socket())
  req.method = 'GET'
  req.url = SHELL_PATH
  req.headers = headers
  const res = new ServerResponse(req)
  return { event: createEvent(req, res), res }
}

describe('BFF do shell: a versão de uma pessoa nunca vira cache compartilhado (X14)', () => {
  let calls: RawCall[]
  let upstreamHeaders: Record<string, string>
  let upstreamBody: unknown

  beforeEach(() => {
    calls = []
    upstreamHeaders = {}
    upstreamBody = shellWith([])
    vi.stubGlobal('useRuntimeConfig', () => ({ djangoBaseUrl: DJANGO }))
    const raw = vi.fn((url: string, options: RawCall['options']) => {
      calls.push({ url, options })
      return Promise.resolve({ status: 200, _data: upstreamBody, headers: new Headers({ 'content-type': 'application/json', ...upstreamHeaders }) })
    })
    vi.stubGlobal('$fetch', Object.assign(vi.fn(), { raw }))
  })

  it('quem tem sessão vai à rota privada, com o cookie, e a resposta B sai private, no-store', async () => {
    upstreamBody = shellWith([{ ref: 'prova', variant: 'b' }])
    upstreamHeaders = { 'cache-control': 'private, no-store' }
    const { event, res } = makeEvent({ cookie: 'sessionid=cliente-b; csrftoken=t' })

    const body = await proxyDjangoPath(event, SHELL_PATH)

    expect(calls).toHaveLength(1)
    expect(calls[0]!.url).toBe(`${DJANGO}${SHELL_PATH}`)
    expect(calls[0]!.options.headers.cookie).toContain('sessionid=cliente-b')
    expect(experienceVariant(body as ShellResponse, 'prova')).toBe('b')
    expect(res.getHeader('cache-control')).toBe('private, no-store')
  })

  it('o BFF não repassa cabeçalho de cache do upstream: nem um "public" errado vaza o shell', async () => {
    // Se um dia o Django errar e marcar o shell de sessão como público, a borda do
    // Nitro continua dizendo private, no-store: a resposta é da pessoa da sessão.
    upstreamBody = shellWith([{ ref: 'prova', variant: 'b' }])
    upstreamHeaders = { 'cache-control': 'public, max-age=60' }
    const { event, res } = makeEvent({ cookie: 'sessionid=cliente-b' })

    await proxyDjangoPath(event, SHELL_PATH)

    expect(res.getHeader('cache-control')).toBe('private, no-store')
  })

  it('o anônimo vai à gêmea pública, sem cookie nenhum (lá só existe a padrão)', async () => {
    const { event } = makeEvent({ cookie: 'csrftoken=t; _ga=x' })

    await proxyDjangoPath(event, SHELL_PATH)

    expect(calls[0]!.url).toBe(`${DJANGO}/api/v1/storefront/public/shell/`)
    expect(calls[0]!.options.headers.cookie).toBeUndefined()
  })

  it('query string não escolhe versão: com ela, a leitura fica na rota privada e a query só passa adiante', async () => {
    const { event } = makeEvent({ cookie: 'sessionid=cliente-a' })
    event.node.req.url = `${SHELL_PATH}?experience=b`

    await proxyDjangoPath(event, SHELL_PATH)

    // O BFF não interpreta a query; quem decide é o Django, que a ignora (OC-20,
    // test_experience: nenhuma entrada da requisição escolhe a versão).
    expect(calls[0]!.url).toBe(`${DJANGO}${SHELL_PATH}?experience=b`)
  })
})

// ── D1: nada no cliente escolhe a versão ─────────────────────────────────────

describe('D1: a loja não tem como trocar a versão', () => {
  const sources = ['app/composables/useExperience.ts', 'app/utils/experience.ts'].map(path => ({
    path,
    code: readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')
      // só o código: o comentário pode citar o que não se faz
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/^\s*\/\/.*$/gm, '')
  }))

  it.each(sources)('$path não lê URL, cookie, armazenamento nem cabeçalho', ({ code }) => {
    for (const forbidden of ['useRoute', 'query', 'useCookie', 'document.cookie', 'localStorage', 'sessionStorage', 'useRequestHeader', 'useState']) {
      expect(code, forbidden).not.toContain(forbidden)
    }
  })

  it('useExperience não devolve setter: a versão é só leitura', () => {
    const composable = sources[0]!.code
    expect(composable).toMatch(/variant: ComputedRef<string>/)
    expect(composable).not.toMatch(/set[A-Z]\w*\s*[:(]/)
  })
})
