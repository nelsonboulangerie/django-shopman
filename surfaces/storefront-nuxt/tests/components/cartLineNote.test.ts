// Observação por item da sacola: grava pelo PUT da linha (meta.notes no
// servidor) e mostra o texto salvo com "Alterar".
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import CartLineNote from '~/components/CartLineNote.vue'

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)
mockNuxtImport('useSonner', () => {
  const fn: any = () => {}
  fn.success = () => {}
  fn.error = () => {}
  return fn
})

const flush = () => new Promise(resolve => setTimeout(resolve, 0))

describe('CartLineNote', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=testtoken'
    fetchMock.mockReset()
  })

  it('grava a observação do item pela rota da linha', async () => {
    fetchMock.mockResolvedValue({ cart: { items: [], actions: [] } })
    const wrapper = await mountSuspended(CartLineNote, {
      props: { lineId: 'L-1', name: 'Croissant', notes: '' }
    })

    await wrapper.get('[data-cart-line-note-open]').trigger('click')
    const input = wrapper.get('[data-cart-line-note-input]')
    expect(input.attributes('placeholder')).toBe('Ex.: sem cebola')
    expect(input.attributes('maxlength')).toBe('280')
    await input.setValue('  sem cebola  ')
    await wrapper.get('[data-cart-line-note-save]').trigger('click')
    await flush()

    const putCall = fetchMock.mock.calls.find(([url]) => String(url).includes('/api/v1/cart/lines/'))
    expect(putCall).toBeTruthy()
    expect(String(putCall![0])).toContain('/api/v1/cart/lines/L-1/notes/')
    expect(putCall![1]).toMatchObject({ method: 'PUT', body: { notes: 'sem cebola' } })
    expect(wrapper.find('[data-cart-line-note-input]').exists()).toBe(false)
  })

  it('mostra a observação já salva', async () => {
    const wrapper = await mountSuspended(CartLineNote, {
      props: { lineId: 'L-2', name: 'Quiche', notes: 'bem quente' }
    })
    expect(wrapper.get('[data-cart-line-note-text]').text()).toContain('bem quente')
    expect(wrapper.text()).toContain('Alterar')
    expect(wrapper.find('[data-cart-line-note-open]').exists()).toBe(false)
  })
})
