import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import ManageStockAlertPage from '~/pages/gerenciar-aviso.vue'

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)
mockNuxtImport('useSonner', () => {
  const fn: any = () => {}
  fn.success = vi.fn()
  fn.error = vi.fn()
  return () => fn
})

const activeState = {
  ok: true,
  sku: 'CROISSANT',
  product_name: 'Croissant',
  event_label: 'saiu do forno',
  state: 'active',
  can_pause: true,
  can_resume: false,
  can_cancel: true,
  suppressed_deliveries: 0,
  accepted_deliveries: 0,
  unresolved_deliveries: 0,
  delivery_note: 'Mensagens já aceitas pelo provedor não podem ser retiradas.',
}

const mountedWrappers: Array<{ unmount: () => void }> = []

async function mountPage () {
  const wrapper = await mountSuspended(ManageStockAlertPage)
  mountedWrappers.push(wrapper)
  return wrapper
}

describe('stock alert management capability page', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=testtoken'
    window.history.replaceState({}, '', '/gerenciar-aviso#opaque-capability')
    fetchMock.mockReset()
    fetchMock.mockResolvedValue(activeState)
    const transientStates = useState<Record<string, 'paused' | 'cancelled'>>('stock-notify-transient-states', () => ({}))
    transientStates.value = {}
  })

  afterEach(() => {
    for (const wrapper of mountedWrappers.splice(0)) wrapper.unmount()
  })

  it('reads state by header, removes the fragment, and GET never mutates', async () => {
    const wrapper = await mountPage()
    await vi.waitFor(() => expect(wrapper.text()).toContain('Croissant'))

    expect(window.location.hash).toBe('')
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      method: 'GET',
      headers: { 'X-Stock-Alert-Capability': 'opaque-capability' },
    })
    expect(wrapper.text()).toContain('Anotado')
    expect(wrapper.get('[role="status"] button').attributes('title')).toContain('ativo para as próximas ocorrências')
  })

  it('pauses only after the explicit PATCH action', async () => {
    fetchMock
      .mockResolvedValueOnce(activeState)
      .mockResolvedValueOnce({ ...activeState, state: 'paused', can_pause: false, can_resume: true })
    const wrapper = await mountPage()
    await vi.waitFor(() => expect(wrapper.text()).toContain('Pausar aviso'))

    await wrapper.findAll('button').find(button => button.text().includes('Pausar aviso'))!.trigger('click')
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))

    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      method: 'PATCH',
      body: { action: 'pause' },
    })
    expect(wrapper.get('[role="status"]').text()).toBe('Pausado')
    expect(useState<Record<string, string>>('stock-notify-transient-states').value).toEqual({ CROISSANT: 'paused' })
    expect(wrapper.text()).toContain('Retomar para próximas ocorrências')
  })

  it('shows Cancelado immediately after the definitive action', async () => {
    fetchMock
      .mockResolvedValueOnce(activeState)
      .mockResolvedValueOnce({ ...activeState, state: 'cancelled', can_pause: false, can_resume: false, can_cancel: false })
    const wrapper = await mountPage()
    await vi.waitFor(() => expect(wrapper.text()).toContain('Cancelar aviso'))

    const buttons = wrapper.findAll('button')
    await buttons.find(button => button.text().includes('Cancelar aviso'))!.trigger('click')
    await vi.waitFor(() => expect(document.body.textContent).toContain('Cancelar este aviso?'))
    const dialogButtons = Array.from(document.body.querySelectorAll<HTMLButtonElement>('button'))
    dialogButtons.filter(button => button.textContent?.includes('Cancelar aviso')).at(-1)?.click()
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))

    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({ method: 'DELETE' })
    expect(wrapper.get('[role="status"]').text()).toBe('Cancelado')
    expect(useState<Record<string, string>>('stock-notify-transient-states').value).toEqual({ CROISSANT: 'cancelled' })
    expect(wrapper.findAll('button').some(button => button.text().includes('Cancelar aviso'))).toBe(false)
  })

  it('clears the transient confirmation when a paused alert is resumed', async () => {
    const pausedState = { ...activeState, state: 'paused', can_pause: false, can_resume: true }
    fetchMock
      .mockResolvedValueOnce(pausedState)
      .mockResolvedValueOnce(activeState)
    const transientStates = useState<Record<string, 'paused' | 'cancelled'>>('stock-notify-transient-states', () => ({}))
    transientStates.value = { CROISSANT: 'paused' }
    const wrapper = await mountPage()
    await vi.waitFor(() => expect(wrapper.text()).toContain('Retomar para próximas ocorrências'))

    await wrapper.findAll('button').find(button => button.text().includes('Retomar para próximas ocorrências'))!.trigger('click')
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))

    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({ method: 'PATCH', body: { action: 'resume' } })
    expect(transientStates.value).toEqual({})
    expect(wrapper.get('[role="status"]').text()).toBe('Anotado')
  })

  it('does not call the API without a capability fragment', async () => {
    window.history.replaceState({}, '', '/gerenciar-aviso')
    const wrapper = await mountPage()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Este link de gestão não é válido')
  })
})
