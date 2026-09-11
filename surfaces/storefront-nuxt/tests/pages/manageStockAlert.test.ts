import { beforeEach, describe, expect, it, vi } from 'vitest'
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

describe('stock alert management capability page', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=testtoken'
    window.history.replaceState({}, '', '/gerenciar-aviso#opaque-capability')
    fetchMock.mockReset()
    fetchMock.mockResolvedValue(activeState)
  })

  it('reads state by header, removes the fragment, and GET never mutates', async () => {
    const wrapper = await mountSuspended(ManageStockAlertPage)
    await vi.waitFor(() => expect(wrapper.text()).toContain('Croissant'))

    expect(window.location.hash).toBe('')
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      method: 'GET',
      headers: { 'X-Stock-Alert-Capability': 'opaque-capability' },
    })
    expect(wrapper.text()).toContain('O aviso está ativo')
  })

  it('pauses only after the explicit PATCH action', async () => {
    fetchMock
      .mockResolvedValueOnce(activeState)
      .mockResolvedValueOnce({ ...activeState, state: 'paused', can_pause: false, can_resume: true })
    const wrapper = await mountSuspended(ManageStockAlertPage)
    await vi.waitFor(() => expect(wrapper.text()).toContain('Pausar aviso'))

    await wrapper.get('button').trigger('click')
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))

    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      method: 'PATCH',
      body: { action: 'pause' },
    })
    expect(wrapper.text()).toContain('Retomar para próximas ocorrências')
  })

  it('does not call the API without a capability fragment', async () => {
    window.history.replaceState({}, '', '/gerenciar-aviso')
    const wrapper = await mountSuspended(ManageStockAlertPage)

    expect(fetchMock).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Este link de gestão não é válido')
  })
})
