import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { reactive, ref, type Ref } from 'vue'
import MarketingPromptSheet from '~/components/MarketingPromptSheet.vue'
import PwaInstallInvite from '~/components/PwaInstallInvite.vue'
import type { PwaCopyProjection } from '~/types/shopman'

// UM convite por visualização de página (useShopInvite). Monta os dois convites
// do shell juntos, como no app.vue, e prova a regra:
//
// - com o convite de instalar aberto, o de novidades não sobe;
// - fechado o de instalar, o de novidades ainda espera: ele abriu NESTA página;
// - navegou, o de novidades sobe;
// - quando o de instalar não vai abrir, o de novidades tem a vez — e, aberto ele,
//   o de instalar que ficou elegível depois espera a próxima página.

const mocks = vi.hoisted(() => ({
  route: null as unknown as { path: string },
  canInstall: null as unknown as Ref<boolean>,
  isDismissed: null as unknown as Ref<boolean>,
  fetch: null as unknown as ReturnType<typeof vi.fn>
}))

mockNuxtImport('useRoute', () => () => mocks.route)
mockNuxtImport('$fetch', () => (...args: unknown[]) => mocks.fetch(...args))
mockNuxtImport('usePwaInstall', () => () => ({
  canInstall: mocks.canInstall,
  install: vi.fn(),
  isStandalone: ref(false),
  isIos: ref(false),
  isDismissed: mocks.isDismissed,
  markShown: vi.fn(),
  // Fechar o convite de instalar adia por dias, como o composable real.
  dismiss: () => { mocks.isDismissed.value = true }
}))

vi.mock('vue-sonner', async (importOriginal) => {
  const toast: any = vi.fn()
  toast.success = vi.fn()
  toast.error = vi.fn()
  toast.info = vi.fn()
  return { ...(await importOriginal<object>()), toast }
})

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

const stubs = {
  BottomSheet: {
    props: ['open', 'title', 'description'],
    template: '<div v-if="open"><slot /><footer><slot name="footer" /></footer></div>'
  }
}

const mounted: Array<{ unmount: () => void }> = []

async function mountShell () {
  const pwa = await mountSuspended(PwaInstallInvite, { props: { copy }, global: { stubs } })
  const marketing = await mountSuspended(MarketingPromptSheet, { props: { delayMs: 0 }, global: { stubs } })
  mounted.push(pwa, marketing)
  await settle()
  return { pwa, marketing }
}

async function settle () {
  await flushPromises()
  await new Promise(resolve => setTimeout(resolve, 5))
  await flushPromises()
}

const pwaOpen = (w: any) => w.find('[data-testid="pwa-install-invite"]').exists()
const marketingOpen = (w: any) => w.find('[data-testid="marketing-prompt-sheet"]').exists()

describe('convites do shell — um por página', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=synthetic'
    mocks.route = reactive({ path: '/menu' })
    mocks.canInstall = ref(true)
    mocks.isDismissed = ref(false)
    mocks.fetch = vi.fn().mockResolvedValue({ ok: true, whatsapp_opted_in: true })
    sessionStorage.removeItem('shopman-marketing-prompt-shown')
    useState('shop-invite-open').value = { open: null, shownOnPath: null }
    const session = useShopSession()
    session.reset()
    session.setFromAuthSession({ is_authenticated: true, customer_name: 'Ana Silva', welcome_asks_name: false, welcome_asks_marketing: true })
  })

  afterEach(() => {
    for (const page of mounted.splice(0)) page.unmount()
  })

  it('com o de instalar aberto, o de novidades não sobe; fechado e navegado, sobe', async () => {
    const { pwa, marketing } = await mountShell()

    expect(pwaOpen(pwa)).toBe(true)
    expect(marketingOpen(marketing)).toBe(false)

    // Fecha o de instalar: nesta página ele já abriu, o de novidades espera.
    await pwa.findAll('button').find((b: any) => b.text().includes('Agora não'))!.trigger('click')
    await settle()
    expect(pwaOpen(pwa)).toBe(false)
    expect(marketingOpen(marketing)).toBe(false)

    // Próxima navegação: a vez é do de novidades.
    mocks.route.path = '/conta'
    await settle()
    expect(marketingOpen(marketing)).toBe(true)
    expect(pwaOpen(pwa)).toBe(false)
    // Nada foi respondido por baixo dos panos enquanto esperava.
    expect(mocks.fetch).not.toHaveBeenCalled()
  })

  it('quando o de instalar não vai abrir, o de novidades tem a vez — e segura a página', async () => {
    mocks.canInstall.value = false
    const { pwa, marketing } = await mountShell()

    expect(pwaOpen(pwa)).toBe(false)
    expect(marketingOpen(marketing)).toBe(true)

    // O navegador libera a instalação depois: nesta página, com o de novidades
    // aberto, o de instalar espera.
    mocks.canInstall.value = true
    await settle()
    expect(pwaOpen(pwa)).toBe(false)
    expect(marketingOpen(marketing)).toBe(true)
  })
})
