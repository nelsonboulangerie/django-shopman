// StockNotifyButton (WP-S6): estado confirmado persiste da projeção; logado assina
// em 1 clique (telefone da conta); a confirmação vira estado calmo e desabilitado.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { DOMWrapper } from '@vue/test-utils'
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import StockNotifyButton from '~/components/StockNotifyButton.vue'

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)
mockNuxtImport('useSonner', () => {
  const fn: any = () => {}
  fn.success = () => {}
  fn.error = () => {}
  return () => fn
})

async function setAuthenticated (value: boolean) {
  const { useShopSession } = await import('~/composables/useShopSession')
  const s = useShopSession()
  s.reset()
  if (value) s.setFromAuthSession({ is_authenticated: true, customer_name: 'Ana', customer_phone: '43999' })
}

async function setDefaultDdd (value: string) {
  const { useShopSession } = await import('~/composables/useShopSession')
  const s = useShopSession()
  s.state.value = {
    ...s.state.value,
    publicConfig: {
      google_maps_api_key: '',
      whatsapp_url: '',
      shop_latitude: null,
      shop_longitude: null,
      default_ddd: value
    }
  }
}

describe('StockNotifyButton', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=testtoken'
    vi.unstubAllGlobals()
    fetchMock.mockReset()
    vi.stubGlobal('$fetch', fetchMock)
    document.body.innerHTML = ''
  })

  it('shows the calm confirmed state when already subscribed', async () => {
    await setAuthenticated(true)
    const wrapper = await mountSuspended(StockNotifyButton, {
      props: { sku: 'PAO', name: 'Pão', subscribed: true }
    })
    expect(wrapper.text()).toContain('Avisaremos você')
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
  })

  it('authenticated one-click subscribe hits the notify endpoint and confirms', async () => {
    await setAuthenticated(true)
    fetchMock.mockResolvedValue({})
    const wrapper = await mountSuspended(StockNotifyButton, {
      props: { sku: 'PAO', name: 'Pão', subscribed: false }
    })

    await wrapper.get('button').trigger('click')
    await new Promise(r => setTimeout(r, 0))
    await nextTick()

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0]?.[0]).toContain('/availability/PAO/notify/')
    expect(wrapper.text()).toContain('Avisaremos você') // virou estado confirmado
  })

  it('renders the notify affordance with an accessible label when not subscribed', async () => {
    await setAuthenticated(true)
    const wrapper = await mountSuspended(StockNotifyButton, {
      props: { sku: 'PAO', name: 'Pão', pill: true, subscribed: false }
    })
    expect(wrapper.get('button').attributes('aria-label')).toBe('Avise quando Pão voltar')
  })

  it('anonymous submit uses the shop default DDD and repairs legacy mobile input', async () => {
    await setAuthenticated(false)
    await setDefaultDdd('43')
    fetchMock.mockResolvedValue({})
    const wrapper = await mountSuspended(StockNotifyButton, {
      props: { sku: 'PAO', name: 'Pão', subscribed: false }
    })

    await wrapper.get('button').trigger('click')
    await nextTick()
    const input = document.body.querySelector<HTMLInputElement>('input[aria-label="Telefone para aviso"]')
    const form = document.body.querySelector<HTMLFormElement>('form')
    expect(input).not.toBeNull()
    expect(form).not.toBeNull()
    await new DOMWrapper(input!).setValue('9840-4900')
    await new DOMWrapper(form!).trigger('submit')
    await new Promise(r => setTimeout(r, 0))

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0]?.[1]?.body).toEqual({ phone: '+5543998404900' })
  })
})
