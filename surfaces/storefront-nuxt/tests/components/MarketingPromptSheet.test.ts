import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import MarketingPromptSheet from '~/components/MarketingPromptSheet.vue'

// O convite de novidades é um bottom sheet na página de destino, não um passo
// do login. O que só o COMPONENTE decide, e por isso se monta:
//
// - nasce desligado, com três linhas + chave, e nada além disso (sem "18",
//   sem Termos, sem "Continuar", sem "Deixar para depois", sem "Conta ›");
// - LIGAR salva na hora (`whatsapp: true`), fecha e agradece;
// - FECHAR sem ligar grava só o carimbo (`whatsapp: false`) — nunca um opt-out;
// - nunca sobe em /entrar, /a, no checkout ou no pedido;
// - não volta depois de respondido/fechado, nem quando o carimbo falhou.

const { fetchMock, mocks, sonner } = vi.hoisted(() => {
  const sonner: any = vi.fn()
  sonner.success = vi.fn()
  sonner.error = vi.fn()
  sonner.info = vi.fn()
  return { fetchMock: vi.fn(), mocks: { path: '/menu' }, sonner }
})
mockNuxtImport('$fetch', () => fetchMock)
mockNuxtImport('useRoute', () => () => ({
  get path () { return mocks.path }
}))
// `useSonner` é o `toast` do vue-sonner reexportado (nuxt.config): o mock vai no módulo de origem.
vi.mock('vue-sonner', async (importOriginal) => ({ ...(await importOriginal<object>()), toast: sonner }))

const SHOWN_KEY = 'shopman-marketing-prompt-shown'

function routeFetch (url: string) {
  if (String(url).endsWith('/api/v1/account/marketing-prompt/')) return Promise.resolve({ ok: true, whatsapp_opted_in: true })
  return Promise.resolve({})
}

function answers () {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/api/v1/account/marketing-prompt/'))
}

const mounted: Array<{ unmount: () => void }> = []

function seedSession (opts: { authenticated?: boolean, asksMarketing?: boolean } = {}) {
  const session = useShopSession()
  session.reset()
  session.setFromAuthSession({
    is_authenticated: opts.authenticated ?? true,
    customer_name: 'Ana Silva',
    requires_welcome: false,
    welcome_asks_name: false,
    welcome_asks_marketing: opts.asksMarketing ?? true
  })
  return session
}

// O sheet real vive num portal (Reka); o stub deixa tudo no wrapper e expõe o
// gesto de fechar (X/arrastar/tocar fora/Esc = `update:open` false).
async function mountSheet (props: { delayMs?: number } = { delayMs: 0 }) {
  const page = await mountSuspended(MarketingPromptSheet, {
    props,
    global: {
      stubs: {
        BottomSheet: {
          props: ['open', 'title'],
          emits: ['update:open'],
          // O botão de fechar fica FORA do `v-if`: a primitiva real ainda emite
          // `update:open` false ao terminar a animação de saída, já fechada.
          template: `<div>
            <button type="button" data-testid="sheet-close" @click="$emit('update:open', false)">Fechar</button>
            <div v-if="open" data-testid="sheet-open">
              <h2 data-testid="sheet-title">{{ title }}</h2>
              <slot />
            </div>
          </div>`
        }
      }
    }
  })
  mounted.push(page)
  await settle()
  return page
}

async function settle () {
  await flushPromises()
  await new Promise(resolve => setTimeout(resolve, 5))
  await flushPromises()
}

describe('MarketingPromptSheet — o convite de novidades', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=synthetic'
    fetchMock.mockReset()
    fetchMock.mockImplementation(routeFetch)
    sonner.success.mockReset()
    sonner.error.mockReset()
    sonner.info.mockReset()
    sessionStorage.removeItem(SHOWN_KEY)
    mocks.path = '/menu'
  })

  afterEach(() => {
    for (const page of mounted.splice(0)) page.unmount()
  })

  it('nasce desligado: três linhas, a chave e nada mais', async () => {
    seedSession()
    const page = await mountSheet()

    expect(page.find('[data-testid="sheet-open"]').exists()).toBe(true)
    expect(page.find('[data-testid="sheet-title"]').text()).toBe('Saber das fornadas antes de todo mundo?')
    const body = page.find('[data-marketing-prompt]')
    expect(body.text()).toContain('Avisos pelo WhatsApp')
    expect(body.text()).toContain('Mude quando quiser em Preferências.')
    const toggle = page.find('#marketing-prompt-whatsapp')
    expect(toggle.exists()).toBe(true)
    expect(toggle.attributes('aria-checked')).toBe('false')
    // Nada além das três linhas + chave + fechar.
    const text = page.text()
    expect(text).not.toMatch(/Continuar|Deixar para depois|Novidades da Nelson|Termos|Conta ›|\b18\b|maior|nascimento/i)
    expect(page.find('button[type="submit"]').exists()).toBe(false)
    expect(sessionStorage.getItem(SHOWN_KEY)).toBe('1')
    expect(answers()).toHaveLength(0)
  })

  it('só sobe autenticado e com a pergunta pendente', async () => {
    seedSession({ asksMarketing: false })
    const page = await mountSheet()
    expect(page.find('[data-testid="sheet-open"]').exists()).toBe(false)

    seedSession({ authenticated: false })
    const anon = await mountSheet()
    expect(anon.find('[data-testid="sheet-open"]').exists()).toBe(false)
    expect(sessionStorage.getItem(SHOWN_KEY)).toBeNull()
  })

  it('ligar salva na hora (whatsapp: true), fecha e agradece', async () => {
    const session = seedSession()
    const page = await mountSheet()

    await page.find('#marketing-prompt-whatsapp').trigger('click')
    await settle()

    expect(answers()).toHaveLength(1)
    expect(answers()[0]![1] as any).toMatchObject({ method: 'POST', body: { whatsapp: true } })
    expect(page.find('[data-testid="sheet-open"]').exists()).toBe(false)
    expect(sonner.success).toHaveBeenCalledWith('Combinado. Você vai saber primeiro.')
    expect(session.welcomeAsksMarketing.value).toBe(false)
    // Nunca um opt-out por baixo dos panos.
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/api/v1/account/preferences/notifications/'))).toBe(false)
  })

  it('diz quando o servidor não concedeu (a data do perfil prova menor)', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (String(url).endsWith('/api/v1/account/marketing-prompt/')) return Promise.resolve({ ok: true, whatsapp_opted_in: false })
      return Promise.resolve({})
    })
    seedSession()
    const page = await mountSheet()

    await page.find('#marketing-prompt-whatsapp').trigger('click')
    await settle()

    expect(page.find('[data-testid="sheet-open"]').exists()).toBe(false)
    expect(sonner.success).not.toHaveBeenCalled()
    expect(sonner.info).toHaveBeenCalledWith('Novidades só vão para maiores de idade. Sua resposta ficou guardada.')
  })

  it('se salvar falhar, a chave volta e o sheet fica — a pessoa decide', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (String(url).endsWith('/api/v1/account/marketing-prompt/')) return Promise.reject(new Error('offline'))
      return Promise.resolve({})
    })
    const session = seedSession()
    const page = await mountSheet()

    await page.find('#marketing-prompt-whatsapp').trigger('click')
    await settle()

    expect(page.find('[data-testid="sheet-open"]').exists()).toBe(true)
    expect(page.find('#marketing-prompt-whatsapp').attributes('aria-checked')).toBe('false')
    expect(sonner.error).toHaveBeenCalledWith('Não foi possível salvar sua resposta.')
    expect(session.welcomeAsksMarketing.value).toBe(true)
  })

  it('fechar sem ligar grava só o carimbo (whatsapp: false) e a pergunta não volta', async () => {
    const session = seedSession()
    const page = await mountSheet()

    await page.find('[data-testid="sheet-close"]').trigger('click')
    await settle()

    expect(page.find('[data-testid="sheet-open"]').exists()).toBe(false)
    expect(answers()).toHaveLength(1)
    expect((answers()[0]![1] as any).body).toEqual({ whatsapp: false })
    expect(session.welcomeAsksMarketing.value).toBe(false)
    expect(sonner.success).not.toHaveBeenCalled()

    // Navegar para outra página elegível não reabre: a sessão já sabe.
    mocks.path = '/conta'
    await settle()
    expect(page.find('[data-testid="sheet-open"]').exists()).toBe(false)
  })

  it('depois de ligar, o fechamento não grava uma segunda resposta', async () => {
    seedSession()
    const page = await mountSheet()

    await page.find('#marketing-prompt-whatsapp').trigger('click')
    await settle()
    // O sheet já fechou; um `update:open` false tardio (animação) não pode virar `false`.
    await page.find('[data-testid="sheet-close"]').trigger('click')
    await settle()

    expect(answers()).toHaveLength(1)
    expect((answers()[0]![1] as any).body).toEqual({ whatsapp: true })
  })

  it.each(['/entrar', '/a', '/finalizar', '/finalizar/endereco', '/pedido/NB-123', '/pedido/NB-123/pagamento'])(
    'nunca sobe em %s',
    async path => {
      mocks.path = path
      seedSession()
      const page = await mountSheet()

      expect(page.find('[data-testid="sheet-open"]').exists()).toBe(false)
      expect(answers()).toHaveLength(0)
      expect(sessionStorage.getItem(SHOWN_KEY)).toBeNull()
    }
  )

  it('uma vez por sessão de navegador, mesmo que o carimbo tenha falhado', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (String(url).endsWith('/api/v1/account/marketing-prompt/')) return Promise.reject(new Error('offline'))
      return Promise.resolve({})
    })
    seedSession()
    const first = await mountSheet()
    await first.find('[data-testid="sheet-close"]').trigger('click')
    await settle()
    expect(answers()).toHaveLength(1)

    // Recarga: a sessão volta a dizer "pendente" (o carimbo não gravou), mas não se insiste.
    seedSession()
    const second = await mountSheet()
    expect(second.find('[data-testid="sheet-open"]').exists()).toBe(false)
    expect(answers()).toHaveLength(1)
  })

  it('espera a página assentar antes de subir (~600 ms)', async () => {
    seedSession()
    const page = await mountSheet({})

    expect(page.find('[data-testid="sheet-open"]').exists()).toBe(false)
    await new Promise(resolve => setTimeout(resolve, 700))
    await flushPromises()
    expect(page.find('[data-testid="sheet-open"]').exists()).toBe(true)
  })
})
