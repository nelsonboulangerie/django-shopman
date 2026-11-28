import { describe, expect, it } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import AppBottomNav from '~/components/AppBottomNav.vue'

// Beta 05/11 (LOJA-15): os links da barra inferior chegavam ao leitor de tela sem nome.

describe('AppBottomNav: todo link tem nome', () => {
  it('Início, Cardápio, Sacola e Entrar, cada um com o nome que a tela mostra', async () => {
    useShopSession().reset()
    const wrapper = await mountSuspended(AppBottomNav, { route: '/' })

    const names = wrapper.findAll('[data-bottom-nav-link]').map(link => link.attributes('aria-label'))
    expect(names).toEqual(['Início', 'Cardápio', 'Sacola', 'Entrar'])
  }, 30_000)
})
