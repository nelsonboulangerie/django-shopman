import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import SearchOverlay from '~/components/SearchOverlay.vue'

// Beta 05/11 (LOJA-12): a busca do cardápio terminava em "veja o cardápio completo"
// sem botão nenhum, enquanto a página /busca, com a mesma frase, tinha o botão.

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)

const mounted: Array<{ unmount: () => void }> = []

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount()
  useSearchOverlay().closeSearch()
})

describe('SearchOverlay: busca sem resultado', () => {
  it('oferece o cardápio completo no próprio vazio', async () => {
    fetchMock.mockResolvedValue({
      catalog: {
        items: [],
        sections: [],
        search_empty_state: {
          title: 'Nada por aqui',
          message: 'Não encontramos esse item. Tente outro termo ou veja o cardápio completo.',
          cta_label: 'Ver cardápio completo',
          cta_href: '/menu'
        }
      }
    })
    const wrapper = await mountSuspended(SearchOverlay, { attachTo: document.body })
    mounted.push(wrapper)
    useSearchOverlay().openSearch()
    await flushPromises()

    const input = document.getElementById('overlay-search-input') as HTMLInputElement
    input.value = 'zzzzzz'
    input.dispatchEvent(new Event('input'))
    await flushPromises()

    const button = document.querySelector('[data-search-empty-menu]')
    expect(button).not.toBeNull()
    expect(button!.textContent).toContain('Ver cardápio completo')
    expect(button!.getAttribute('href')).toBe('/menu')
  }, 30_000)
})
