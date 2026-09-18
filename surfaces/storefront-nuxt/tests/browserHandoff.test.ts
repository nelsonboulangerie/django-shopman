// A travessia do webview para o navegador de verdade.
//
// ⚠️ O motivo é pote de cookie: o webview do WhatsApp tem o seu, separado do Safari. Sessão e
// aparelho confiado conquistados ali não existem no navegador que ela usa no resto do dia.
//
// Estes testes guardam as três coisas que decidem se isso funciona no mundo real: reconhecer
// que estamos num webview, montar o esquema CERTO para cada plataforma, e nunca deixar a
// pessoa sem saída quando o truque falhar.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'

const WHATSAPP_IOS = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 WhatsApp/24.10.79'
const WHATSAPP_ANDROID = 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36 WhatsApp/2.24.10'
const SAFARI = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'

describe('reconhecer o navegador embutido', () => {
  it('reconhece o do WhatsApp nos dois sistemas', async () => {
    const { isInAppBrowser } = await import('../app/composables/useBrowserHandoff')

    expect(isInAppBrowser(WHATSAPP_IOS)).toBe(true)
    expect(isInAppBrowser(WHATSAPP_ANDROID)).toBe(true)
  })

  it('reconhece o do Instagram e do Facebook, que também nos trazem gente', async () => {
    const { isInAppBrowser } = await import('../app/composables/useBrowserHandoff')

    expect(isInAppBrowser('Mozilla/5.0 iPhone Instagram 300.0.0')).toBe(true)
    expect(isInAppBrowser('Mozilla/5.0 iPhone [FBAN/FBIOS;FBAV/450.0]')).toBe(true)
  })

  it('NÃO oferece travessia em navegador de verdade — ali não há nada a atravessar', async () => {
    const { isInAppBrowser } = await import('../app/composables/useBrowserHandoff')

    expect(isInAppBrowser(SAFARI)).toBe(false)
    expect(isInAppBrowser('')).toBe(false)
  })
})

describe('o esquema certo para cada plataforma', () => {
  it('iOS usa x-safari-https, que abre o Safari de dentro do webview', async () => {
    const { systemBrowserUrl } = await import('../app/composables/useBrowserHandoff')

    expect(systemBrowserUrl('https://loja.exemplo/a?t=abc', WHATSAPP_IOS))
      .toBe('x-safari-https://loja.exemplo/a?t=abc')
  })

  it('Android usa intent://, que é o mecanismo documentado de entregar a outro app', async () => {
    const { systemBrowserUrl } = await import('../app/composables/useBrowserHandoff')

    const url = systemBrowserUrl('https://loja.exemplo/a?t=abc', WHATSAPP_ANDROID)

    expect(url).toBe('intent://loja.exemplo/a?t=abc#Intent;scheme=https;package=com.android.chrome;end')
  })

  it('o token continua no link — é ele que faz a identidade nascer do outro lado', async () => {
    const { systemBrowserUrl } = await import('../app/composables/useBrowserHandoff')

    expect(systemBrowserUrl('https://loja.exemplo/a?t=segredo', WHATSAPP_IOS)).toContain('t=segredo')
    expect(systemBrowserUrl('https://loja.exemplo/a?t=segredo', WHATSAPP_ANDROID)).toContain('t=segredo')
  })
})

describe('a travessia', () => {
  let navigated: string | null = null
  let posted: { url: string, body: unknown } | null = null

  beforeEach(() => {
    navigated = null
    posted = null
    vi.useFakeTimers()
    Object.assign(globalThis, {
      ref,
      computed,
      useShopmanApiPath: () => (p: string) => p,
      useShopmanCsrfHeaders: () => async () => ({}),
      useRoute: () => ({ fullPath: '/finalizar' }),
      $fetch: vi.fn(async (url: string, opts: { body?: unknown }) => {
        posted = { url, body: opts?.body }
        return { url: 'https://loja.exemplo/a?t=abc' }
      })
    })
    Object.defineProperty(globalThis, 'window', {
      value: { location: { get href() { return '' }, set href(v: string) { navigated = v } } },
      writable: true,
      configurable: true
    })
    Object.defineProperty(globalThis, 'navigator', {
      value: { userAgent: WHATSAPP_IOS },
      writable: true,
      configurable: true
    })
  })

  it('pede o link ao servidor, mandando a tela onde ela está', async () => {
    const { useBrowserHandoff } = await import('../app/composables/useBrowserHandoff')

    await useBrowserHandoff().crossOver()

    expect(posted?.url).toBe('/api/v1/auth/handoff/')
    expect(posted?.body).toEqual({ next: '/finalizar' })
  })

  it('navega pelo esquema da plataforma, não pela URL crua', async () => {
    const { useBrowserHandoff } = await import('../app/composables/useBrowserHandoff')

    await useBrowserHandoff().crossOver()

    expect(navigated).toBe('x-safari-https://loja.exemplo/a?t=abc')
  })

  it('⚠️ ensina o menu do WhatsApp quando o truque não pega', async () => {
    // O truque falha em SILÊNCIO: se o esquema não é entendido, o webview simplesmente não
    // navega. Sem este degrau, a pessoa fica olhando uma tela que não fez nada.
    const { useBrowserHandoff } = await import('../app/composables/useBrowserHandoff')

    const handoff = useBrowserHandoff()
    await handoff.crossOver()
    expect(handoff.needsManualStep.value).toBe(false)

    await vi.advanceTimersByTimeAsync(1500)

    expect(handoff.needsManualStep.value).toBe(true)
  })

  it('erro do servidor não deixa o botão preso, e diz que falhou', async () => {
    Object.assign(globalThis, { $fetch: vi.fn(async () => { throw new Error('offline') }) })
    const { useBrowserHandoff } = await import('../app/composables/useBrowserHandoff')

    const handoff = useBrowserHandoff()
    await handoff.crossOver()

    expect(handoff.failed.value).toBe(true)
    expect(handoff.working.value).toBe(false)
    expect(navigated).toBeNull()
  })
})
