import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import PwaInstallInvite from '~/components/PwaInstallInvite.vue'
import type { PwaCopyProjection } from '~/types/shopman'

const mocks = vi.hoisted(() => ({
  path: '/menu',
  markShown: vi.fn()
}))

mockNuxtImport('useRoute', () => () => ({
  get path () { return mocks.path }
}))

mockNuxtImport('usePwaInstall', () => () => ({
  canInstall: { __v_isRef: true, value: true },
  install: vi.fn(),
  isStandalone: { __v_isRef: true, value: false },
  isIos: { __v_isRef: true, value: false },
  isDismissed: { __v_isRef: true, value: false },
  markShown: mocks.markShown,
  dismiss: vi.fn()
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
  ios_title: entry(),
  ios_message: entry(),
  ios_share_step: entry(),
  ios_add_step: entry(),
  ios_done_cta: entry(),
  update_title: entry(),
  update_cta: entry()
}

async function mountInvite () {
  return mountSuspended(PwaInstallInvite, {
    props: { copy },
    global: {
      stubs: {
        BottomSheet: {
          props: ['open'],
          template: '<div v-if="open" data-testid="open-install-invite"><slot /></div>'
        }
      }
    }
  })
}

describe('PwaInstallInvite', () => {
  beforeEach(() => {
    mocks.path = '/menu'
    mocks.markShown.mockClear()
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
})
