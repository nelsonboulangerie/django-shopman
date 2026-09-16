import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import OfferPage from '~/pages/oferta/[ref].vue'

const { fetchMock, navigate } = vi.hoisted(() => ({ fetchMock: vi.fn(), navigate: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)
mockNuxtImport('navigateTo', () => navigate)

describe('offer outcome on its existing page', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=synthetic'
    fetchMock.mockReset()
    navigate.mockReset()
    sessionStorage.clear()
  })
  it('shows added and missing names before navigating after a partial claim', async () => {
    fetchMock.mockResolvedValue({ ok: true, offer: { ref: 'sample', name: 'Café' }, added: ['P'], skipped: [{ sku: 'C', name: 'Croissant', is_notifiable: false }], cart: { items: [{ sku: 'P', name: 'Pão', qty: 1 }], items_count: 1, is_empty: false } })
    const page = await mountSuspended(OfferPage, { route: '/oferta/sample' })
    await flushPromises()
    expect(page.text()).toContain('Pão')
    expect(page.text()).toContain('Croissant')
    expect(page.text()).toContain('parcialmente')
    expect(navigate).not.toHaveBeenCalled()
    page.unmount()
  })
  it('does not announce success when nothing was added', async () => {
    fetchMock.mockResolvedValue({ ok: false, offer: { ref: 'empty', name: 'Café' }, added: [], skipped: [{ sku: 'C', name: 'Croissant', is_notifiable: false }], cart: { items: [], items_count: 0, is_empty: true } })
    const page = await mountSuspended(OfferPage, { route: '/oferta/empty' })
    await flushPromises()
    expect(page.text()).toContain('Nenhum item foi adicionado')
    expect(page.text()).toContain('Croissant')
    expect(navigate).not.toHaveBeenCalled()
    page.unmount()
  })
})
