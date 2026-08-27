// O degrau de identidade na loja: um toque, sem código para digitar.
//
// ⚠️ A prova é a MENSAGEM ENVIADA, não o toque num link — quem toca pode ter recebido a
// mensagem encaminhada; quem envia controla o número. Estes testes guardam as duas coisas
// que fazem esse degrau valer a pena: que ele chama o start que JÁ existe (nada de mecanismo
// novo) e que a sacola não se perde no caminho.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { computed, ref } from 'vue'

function source(path: string): string {
  return readFileSync(new URL(path, new URL('..', import.meta.url)), 'utf8')
}

describe('useWhatsAppConfirm', () => {
  let fetched: { url: string, body: unknown } | null = null
  let navigated: string | null = null

  beforeEach(async () => {
    fetched = null
    navigated = null
    Object.assign(globalThis, {
      ref,
      computed,
      useShopmanApiPath: () => (p: string) => p,
      useShopmanCsrfHeaders: () => async () => ({}),
      $fetch: vi.fn(async (url: string, opts: { body?: unknown }) => {
        fetched = { url, body: opts?.body }
        return { deep_link: 'https://wa.me/5543999?text=Meu%20c%C3%B3digo' }
      })
    })
    // `window.location.href` é o alvo: dentro do navegador embutido do WhatsApp, abrir aba
    // nova costuma virar tela em branco.
    Object.defineProperty(globalThis, 'window', {
      value: { location: { get href() { return '' }, set href(v: string) { navigated = v } } },
      writable: true,
      configurable: true
    })
  })

  it('chama o start que já existe, em vez de inventar endpoint', async () => {
    const { useWhatsAppConfirm } = await import('../app/composables/useWhatsAppConfirm')

    await useWhatsAppConfirm().confirm('/finalizar')

    expect(fetched?.url).toBe('/api/v1/auth/whatsapp/start/')
  })

  it('manda o destino, para a pessoa voltar onde estava', async () => {
    const { useWhatsAppConfirm } = await import('../app/composables/useWhatsAppConfirm')

    await useWhatsAppConfirm().confirm('/finalizar')

    expect(fetched?.body).toEqual({ next: '/finalizar' })
  })

  it('abre o WhatsApp com a mensagem pronta', async () => {
    const { useWhatsAppConfirm } = await import('../app/composables/useWhatsAppConfirm')

    await useWhatsAppConfirm().confirm('/finalizar')

    expect(navigated).toContain('wa.me')
  })

  it('sem deep link não navega, e diz que falhou', async () => {
    Object.assign(globalThis, { $fetch: vi.fn(async () => ({})) })
    const { useWhatsAppConfirm } = await import('../app/composables/useWhatsAppConfirm')

    const confirmer = useWhatsAppConfirm()
    await confirmer.confirm('/finalizar')

    expect(navigated).toBeNull()
    expect(confirmer.failed.value).toBe(true)
  })

  it('erro de rede não deixa o botão preso em "abrindo"', async () => {
    Object.assign(globalThis, { $fetch: vi.fn(async () => { throw new Error('offline') }) })
    const { useWhatsAppConfirm } = await import('../app/composables/useWhatsAppConfirm')

    const confirmer = useWhatsAppConfirm()
    await confirmer.confirm('/finalizar')

    expect(confirmer.failed.value).toBe(true)
    expect(confirmer.starting.value).toBe(false)
  })
})

describe('useWhatsappVerify', () => {
  let fetched: { url: string, body: unknown } | null = null

  beforeEach(() => {
    fetched = null
    Object.assign(globalThis, {
      ref,
      useShopmanApiPath: () => (p: string) => p,
      useShopmanCsrfHeaders: () => async () => ({}),
      $fetch: vi.fn(async (url: string, opts: { body?: unknown }) => {
        fetched = { url, body: opts?.body }
        return {
          code: 'NB-ABC123',
          message: '#menu NB-ABC123',
          deep_link: 'https://wa.me/5543999?text=%23menu%20NB-ABC123',
          wa_number: '5543999'
        }
      })
    })
  })

  it('usa o endpoint canônico do start leve de WhatsApp', async () => {
    const { useWhatsappVerify } = await import('../app/composables/useWhatsappVerify')

    const verify = useWhatsappVerify()
    await verify.start('/finalizar')

    expect(fetched?.url).toBe('/api/v1/auth/whatsapp/start/')
    expect(fetched?.body).toEqual({ next: '/finalizar' })
    expect(verify.code.value).toBe('NB-ABC123')
    expect(verify.message.value).toBe('#menu NB-ABC123')
  })

  it('mostra estado de preparo enquanto o link do WhatsApp nasce', async () => {
    let resolveFetch!: (value: { code: string, message?: string, deep_link: string, wa_number: string }) => void
    Object.assign(globalThis, {
      $fetch: vi.fn((url: string, opts: { body?: unknown }) => {
        fetched = { url, body: opts?.body }
        return new Promise<{ code: string, message?: string, deep_link: string, wa_number: string }>(resolve => {
          resolveFetch = resolve
        })
      })
    })
    const { useWhatsappVerify } = await import('../app/composables/useWhatsappVerify')

    const verify = useWhatsappVerify()
    const pendingStart = verify.start('/finalizar')

    expect(verify.status.value).toBe('loading')
    await Promise.resolve()
    resolveFetch({ code: 'NB-ABC123', deep_link: 'https://wa.me/5543999?text=%23menu%20NB-ABC123', wa_number: '5543999' })
    await pendingStart
    expect(verify.status.value).toBe('ready')
    expect(verify.message.value).toBe('#menu NB-ABC123')
  })
})

describe('o degrau aparece no checkout, e só nessa combinação', () => {
  const page = source('app/pages/finalizar.vue')

  it('roteia pelo `error_code` do dialeto da casa', () => {
    // ⚠️ `code` seria um segundo nome para a mesma pergunta: a página já lê `error_code`
    // (`total_changed`), e é ele que `docs/reference/errors.md` canoniza.
    expect(page).toContain("data.error_code === 'identity_confirmation_required'")
    expect(page).not.toContain("data.code === 'identity_confirmation_required'")
  })

  it('diz o que dá para fazer agora, não só o que está barrado', () => {
    expect(page).toContain('endereço já salvo ou')
    expect(page).toContain('retirando no balcão')
  })

  it('promete que a sacola fica guardada, porque ela fica', () => {
    // O `cart_session_key` viaja no código NB-XxXx e o resgate adota a sacola.
    expect(page).toContain('Sua sacola fica guardada')
  })

  it('oferece o toque, não um campo de código', () => {
    expect(page).toContain('Confirmar pelo WhatsApp')
    expect(page).not.toMatch(/identityConfirmOffer[\s\S]{0,400}Digite o código/)
  })
})
