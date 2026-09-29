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
    fetchMock.mockResolvedValue({ ok: true, offer: { ref: 'sample', name: 'Café' }, added: ['P'], skipped: [{ sku: 'C', name: 'Croissant', is_notifiable: false }], kept_existing_items: false, cart: { items: [{ sku: 'P', name: 'Pão', qty: 1 }], items_count: 1, is_empty: false } })
    const page = await mountSuspended(OfferPage, { route: '/oferta/sample' })
    await flushPromises()
    expect(page.text()).toContain('Pão')
    expect(page.text()).toContain('Croissant')
    expect(page.text()).toContain('parcialmente')
    expect(navigate).not.toHaveBeenCalled()
    page.unmount()
  })
  it('does not announce success when nothing was added', async () => {
    fetchMock.mockResolvedValue({ ok: false, offer: { ref: 'empty', name: 'Café' }, added: [], skipped: [{ sku: 'C', name: 'Croissant', is_notifiable: false }], kept_existing_items: true, cart: { items: [], items_count: 0, is_empty: true } })
    const page = await mountSuspended(OfferPage, { route: '/oferta/empty' })
    await flushPromises()
    expect(page.text()).toContain('Nenhum item foi adicionado')
    expect(page.text()).toContain('Croissant')
    expect(navigate).not.toHaveBeenCalled()
    page.unmount()
  })
})

const QUESTION = 'Você já tinha itens na sacola e a oferta foi adicionada.'
const merged = {
  ok: true,
  offer: { ref: 'cafe', name: 'Café da tarde' },
  added: ['CRO'],
  skipped: [],
  kept_existing_items: true,
  cart: { items: [{ sku: 'PAO', name: 'Pão', qty: 1 }, { sku: 'CRO', name: 'Croissant', qty: 1 }], items_count: 2, is_empty: false }
}
const onlyTheOffer = {
  ...merged,
  kept_existing_items: false,
  cart: { items: [{ sku: 'CRO', name: 'Croissant', qty: 1 }], items_count: 1, is_empty: false }
}

function buttonNamed (label: string) {
  const button = Array.from(document.body.querySelectorAll('button')).find(el => el.textContent?.trim() === label)
  if (!button) throw new Error(`botão "${label}" não está na tela`)
  return button
}

describe('offer on a bag that already had items', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=synthetic'
    fetchMock.mockReset()
    navigate.mockReset()
    sessionStorage.clear()
  })

  it('always opens by merging, never asking before', async () => {
    fetchMock.mockResolvedValue(merged)
    const page = await mountSuspended(OfferPage, { route: '/oferta/cafe' })
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0]![1].body).toEqual({})
    page.unmount()
  })

  it('asks, with two answers and no way around them', async () => {
    fetchMock.mockResolvedValue(merged)
    const page = await mountSuspended(OfferPage, { route: '/oferta/cafe' })
    await flushPromises()
    expect(document.body.textContent).toContain(QUESTION)
    expect(document.body.textContent).toContain('Deseja manter tudo na sacola?')
    const labels = Array.from(document.body.querySelectorAll('[role="alertdialog"] button')).map(el => el.textContent?.trim())
    expect(labels).toEqual(['Sim, manter tudo', 'Não, só a oferta'])
    expect(navigate).not.toHaveBeenCalled()
    page.unmount()
  })

  it('"Sim, manter tudo" goes to the bag without touching it again', async () => {
    fetchMock.mockResolvedValue(merged)
    const page = await mountSuspended(OfferPage, { route: '/oferta/cafe' })
    await flushPromises()
    buttonNamed('Sim, manter tudo').click()
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(navigate).toHaveBeenCalledWith('/sacola')
    page.unmount()
  })

  it('"Não, só a oferta" asks the server to keep only the offer', async () => {
    fetchMock.mockResolvedValueOnce(merged).mockResolvedValueOnce(onlyTheOffer)
    const page = await mountSuspended(OfferPage, { route: '/oferta/cafe' })
    await flushPromises()
    buttonNamed('Não, só a oferta').click()
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[1]![1].body).toEqual({ mode: 'replace' })
    expect(navigate).toHaveBeenCalledWith('/sacola')
    expect(document.body.textContent).not.toContain(QUESTION)
    page.unmount()
  })

  it('does not ask when the bag was empty', async () => {
    fetchMock.mockResolvedValue({ ...onlyTheOffer })
    const page = await mountSuspended(OfferPage, { route: '/oferta/cafe' })
    await flushPromises()
    expect(document.body.textContent).not.toContain(QUESTION)
    expect(navigate).toHaveBeenCalledWith('/sacola')
    page.unmount()
  })
})
