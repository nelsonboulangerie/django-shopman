// O aviso de página (#3242) com a saída que resolve (#3267): o botão mora dentro do aviso,
// abaixo das barras do topo, e o X o tira. Sem ação, segue o aviso de sempre.
import { beforeEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import PageNotice from '~/components/PageNotice.vue'
import { usePageNotice, usePageNoticeAnchor } from '~/composables/usePageNotice'

describe('PageNotice', () => {
  beforeEach(() => {
    usePageNotice().dismiss()
    usePageNoticeAnchor().claims.value = 0
  })

  it('mostra a frase e o botão da ação, que leva ao destino', async () => {
    const path = useRoute().path
    usePageNotice().show('Sua sacola ficou vazia antes do envio.', path, {
      tone: 'attention',
      action: { label: 'Ver o cardápio', to: '/menu' }
    })
    const wrapper = await mountSuspended(PageNotice)

    expect(wrapper.text()).toContain('Sua sacola ficou vazia antes do envio.')
    const action = wrapper.find('[data-page-notice-action]')
    expect(action.exists()).toBe(true)
    expect(action.text()).toBe('Ver o cardápio')
    expect(action.attributes('href')).toBe('/menu')
    expect(wrapper.find('[data-page-notice-tone]').attributes('data-page-notice-tone')).toBe('attention')
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
  })

  it('o X tira o aviso, com ação ou sem', async () => {
    const path = useRoute().path
    usePageNotice().show('Sua sacola ficou vazia antes do envio.', path, {
      tone: 'attention',
      action: { label: 'Ver o cardápio', to: '/menu' }
    })
    const wrapper = await mountSuspended(PageNotice)

    await wrapper.find('[data-page-notice-close]').trigger('click')
    await nextTick()
    expect(usePageNotice().notice.value).toBeNull()
    expect(wrapper.find('[data-page-notice]').exists()).toBe(false)
  })

  it('sem ação, é o aviso de sempre: frase, X e nenhum botão a mais', async () => {
    const path = useRoute().path
    usePageNotice().show('Este pedido já foi enviado.', path)
    const wrapper = await mountSuspended(PageNotice)

    expect(wrapper.text()).toContain('Este pedido já foi enviado.')
    expect(wrapper.find('[data-page-notice-action]').exists()).toBe(false)
    expect(wrapper.find('[data-page-notice-close]').exists()).toBe(true)
    expect(wrapper.find('[data-page-notice-tone]').attributes('data-page-notice-tone')).toBe('success')
  })

  it('só aparece na página em que foi deixado', async () => {
    usePageNotice().show('Este pedido já foi enviado.', '/pedido/NB-1')
    const wrapper = await mountSuspended(PageNotice)

    expect(wrapper.find('[data-page-notice]').exists()).toBe(false)
  })
})
