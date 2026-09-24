import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import PwaInstallInvite from '~/components/PwaInstallInvite.vue'
import { installPlan, type InstallPlan } from '~/utils/installGuide'
import type { PwaCopyProjection } from '~/types/shopman'

const IPHONE_SAFARI =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
const IPHONE_CHROME =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/126.0.6478.108 Mobile/15E148 Safari/604.1'
const WINDOWS_FIREFOX = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0'

const PROMPT: InstallPlan = { kind: 'prompt', invite: true, steps: [], os: 'android', browser: 'chrome' }

const mocks = vi.hoisted(() => ({
  path: '/menu',
  plan: undefined as unknown as InstallPlan,
  markShown: vi.fn(),
  dismiss: vi.fn(),
  dismissAsDone: vi.fn()
}))

mockNuxtImport('useRoute', () => () => ({
  get path () { return mocks.path }
}))

mockNuxtImport('usePwaInstall', () => () => ({
  install: vi.fn(),
  isStandalone: { __v_isRef: true, value: false },
  plan: {
    __v_isRef: true,
    get value () { return mocks.plan }
  },
  isDismissed: { __v_isRef: true, value: false },
  markShown: mocks.markShown,
  dismiss: mocks.dismiss,
  dismissAsDone: mocks.dismissAsDone
}))

const entry = (title = '', message = '') => ({ title, message })
const copy: PwaCopyProjection = {
  offline_title: entry(),
  offline_message: entry(),
  offline_retry_cta: entry(),
  install_title: entry('A loja mais perto de você'),
  install_message: entry('', 'Instale para abrir a loja direto da Tela de Início.'),
  install_cta: entry('Instalar'),
  install_dismiss_cta: entry('Agora não'),
  manual_title: entry('Coloque a loja na Tela de Início'),
  manual_done_cta: entry('Já adicionei'),
  update_title: entry(),
  update_cta: entry()
}

async function mountInvite () {
  return mountSuspended(PwaInstallInvite, {
    props: { copy },
    global: {
      stubs: {
        BottomSheet: {
          props: ['open', 'title'],
          template: '<div v-if="open" data-testid="open-install-invite">{{ title }}<slot /><footer><slot name="footer" /></footer></div>'
        }
      }
    }
  })
}

describe('PwaInstallInvite', () => {
  beforeEach(() => {
    mocks.path = '/menu'
    mocks.plan = PROMPT
    mocks.markShown.mockClear()
    mocks.dismiss.mockClear()
    mocks.dismissAsDone.mockClear()
  })

  it.each(['/finalizar', '/finalizar/endereco', '/pedido/PED-123'])(
    'não renderiza na rota %s',
    async (path) => {
      mocks.path = path
      const wrapper = await mountInvite()

      expect(wrapper.find('[data-testid="pwa-install-invite"]').exists()).toBe(false)
      expect(mocks.markShown).not.toHaveBeenCalled()
    }
  )

  it('abre em rota elegível e registra a janela de sete dias', async () => {
    const wrapper = await mountInvite()

    expect(wrapper.find('[data-testid="pwa-install-invite"]').exists()).toBe(true)
    expect(mocks.markShown).toHaveBeenCalledOnce()
  })

  it('no iPhone com Safari mostra os passos do Safari, todos de uma vez', async () => {
    mocks.plan = installPlan({ userAgent: IPHONE_SAFARI, canPrompt: false })
    const wrapper = await mountInvite()

    expect(wrapper.get('[data-testid="pwa-install-steps"]').text()).toContain('Compartilhar')
    expect(wrapper.text()).toContain('Adicionar à Tela de Início')
    expect(wrapper.text()).toContain('barra de baixo')
    expect(wrapper.text()).toContain('Coloque a loja na Tela de Início')
  })

  it('no Chrome do iPhone NÃO fala em Safari: o caminho é o menu do Chrome', async () => {
    // A regressão que originou o WP: a loja dizia "barra do Safari" para quem estava
    // no Chrome, e o passo 1 apontava um botão que não existe naquela tela.
    mocks.plan = installPlan({ userAgent: IPHONE_CHROME, canPrompt: false })
    const wrapper = await mountInvite()

    const passos = wrapper.get('[data-testid="pwa-install-steps"]').text()
    expect(passos).toContain('⋯')
    expect(passos).toContain('Chrome')
    expect(passos).not.toContain('barra do Safari')
  })

  it('"já adicionei" encerra de vez; "agora não" só adia', async () => {
    mocks.plan = installPlan({ userAgent: IPHONE_SAFARI, canPrompt: false })
    const wrapper = await mountInvite()

    await wrapper.get('[data-testid="install-done"]').trigger('click')
    expect(mocks.dismissAsDone).toHaveBeenCalledOnce()
    expect(mocks.dismiss).not.toHaveBeenCalled()
  })

  it('onde não há caminho honesto, o convite não aparece', async () => {
    // Firefox de computador não instala aplicativo. Informação correta, ou nada.
    mocks.plan = installPlan({ userAgent: WINDOWS_FIREFOX, canPrompt: false })
    const wrapper = await mountInvite()

    expect(wrapper.find('[data-testid="pwa-install-invite"]').exists()).toBe(false)
    expect(mocks.markShown).not.toHaveBeenCalled()
  })
})
