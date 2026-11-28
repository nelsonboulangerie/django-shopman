import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { reactive, ref, type Ref } from 'vue'
import MarketingPromptSheet from '~/components/MarketingPromptSheet.vue'
import PwaInstallInvite from '~/components/PwaInstallInvite.vue'
import type { PwaCopyProjection } from '~/types/shopman'

// UM convite por visita (useShopInvite; decisão 3 do plano de excelência da loja,
// 16/11/2026). Monta os dois convites do shell juntos, como no app.vue, e prova a
// regra:
//
// - com o convite de instalar aberto, o de novidades não sobe;
// - fechado o de instalar, o de novidades não sobe nem na próxima página nem na
//   recarga: um convite já subiu nesta visita;
// - quando o de instalar não vai abrir, o de novidades tem a vez, e, aberto ele,
//   o de instalar que ficou elegível depois fica para a próxima visita.

const mocks = vi.hoisted(() => ({
  route: null as unknown as { path: string },
  canInstall: null as unknown as Ref<boolean>,
  isDismissed: null as unknown as Ref<boolean>,
  fetch: null as unknown as ReturnType<typeof vi.fn>
}))

mockNuxtImport('useRoute', () => () => mocks.route)
mockNuxtImport('$fetch', () => (...args: unknown[]) => mocks.fetch(...args))
mockNuxtImport('usePwaInstall', () => () => ({
  // `canInstall` virou o plano: quem decide se o convite pode subir é `plan.invite`.
  plan: computed(() => (mocks.canInstall.value
    ? { kind: 'prompt', invite: true, steps: [], os: 'android', browser: 'chrome' }
    : { kind: 'none', invite: false, steps: [], os: 'unknown', browser: 'unknown' })),
  install: vi.fn(),
  isStandalone: ref(false),
  isDismissed: mocks.isDismissed,
  hasOrdered: ref(true),
  refreshHasOrdered: vi.fn(),
  markShown: vi.fn(),
  // Fechar o convite de instalar adia por dias, como o composable real.
  dismiss: () => { mocks.isDismissed.value = true },
  dismissAsDone: () => { mocks.isDismissed.value = true }
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
  manual_title: entry(),
  manual_done_cta: entry(),
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

describe('convites do shell: um por visita', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=synthetic'
    mocks.route = reactive({ path: '/menu' })
    mocks.canInstall = ref(true)
    mocks.isDismissed = ref(false)
    mocks.fetch = vi.fn().mockResolvedValue({ ok: true, whatsapp_opted_in: true })
    sessionStorage.removeItem('shopman-marketing-prompt-shown')
    sessionStorage.removeItem('shopman-invite-shown')
    useState('shop-invite').value = { open: null, shownThisVisit: false, synced: false }
    sessionStorage.setItem('shopman-order-secured', '1')
    const session = useShopSession()
    session.reset()
    session.setFromAuthSession({ is_authenticated: true, customer_name: 'Ana Silva', welcome_asks_name: false, welcome_asks_marketing: true })
  })

  afterEach(() => {
    for (const page of mounted.splice(0)) page.unmount()
  })

  it('com o de instalar aberto, o de novidades não sobe; fechado, nem na próxima página', async () => {
    const { pwa, marketing } = await mountShell()

    expect(pwaOpen(pwa)).toBe(true)
    expect(marketingOpen(marketing)).toBe(false)

    await pwa.findAll('button').find((b: any) => b.text().includes('Agora não'))!.trigger('click')
    await settle()
    expect(pwaOpen(pwa)).toBe(false)
    expect(marketingOpen(marketing)).toBe(false)

    // Navegou: nesta visita um convite já subiu, o de novidades fica para a próxima.
    mocks.route.path = '/conta'
    await settle()
    expect(marketingOpen(marketing)).toBe(false)
    expect(pwaOpen(pwa)).toBe(false)
    expect(sessionStorage.getItem('shopman-invite-shown')).toBe('1')
    expect(mocks.fetch).not.toHaveBeenCalled()
  })

  it('a marca da visita sobrevive à recarga: nenhum convite sobe de novo', async () => {
    sessionStorage.setItem('shopman-invite-shown', '1')
    const { pwa, marketing } = await mountShell()

    expect(pwaOpen(pwa)).toBe(false)
    expect(marketingOpen(marketing)).toBe(false)
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
