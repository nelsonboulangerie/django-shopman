import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import FaqPage from '~/pages/faq.vue'

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)

const site = {
  pages: {
    home: { title: '', description: '' },
    menu: { title: '', description: '' },
    faq: { title: 'Dúvidas da casa', description: 'Entrega, encomenda e horário.' }
  },
  share_image_url: '',
  verifications: { google: '', bing: '', facebook: '', pinterest: '' },
  business: {
    type: 'Bakery',
    name: 'Nelson Boulangerie',
    telephone: '+55 43 3323-1997',
    email: 'nelson@boulangerie.com.br',
    address: {},
    geo: null,
    opening_hours: [],
    same_as: []
  },
  faq: [
    { ref: 'delivery', question: 'Vocês fazem entrega?', answer: 'Sim, em Londrina, pelo site.' },
    { ref: 'preorder', question: 'Dá para encomendar?', answer: 'Sim, com um dia de antecedência.' }
  ]
}

const mounted: Array<{ unmount: () => void }> = []

describe('página /faq', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    clearNuxtData('shopman-site-seo')
  })

  afterEach(() => {
    for (const wrapper of mounted.splice(0)) wrapper.unmount()
  })

  it('serve pergunta E resposta no DOM, com o contato do cadastro', async () => {
    fetchMock.mockResolvedValue({ site })
    const wrapper = await mountSuspended(FaqPage)
    mounted.push(wrapper)

    await vi.waitFor(() => expect(wrapper.find('h1').text()).toBe('Dúvidas da casa'))
    const items = wrapper.findAll('[data-faq-item]')
    expect(items).toHaveLength(2)
    // Fechado para quem lê, inteiro para quem indexa: a resposta está no HTML.
    expect(items[0]!.element.tagName).toBe('DETAILS')
    expect(items[0]!.text()).toContain('Sim, em Londrina, pelo site.')
    expect(wrapper.find('[data-faq-contact-link="phone"]').attributes('href')).toBe('tel:+554333231997')
    expect(wrapper.find('[data-faq-contact-link="email"]').attributes('href')).toBe('mailto:nelson@boulangerie.com.br')
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/storefront/site/')
  })

  it('sem o endpoint, a página continua de pé com o estado vazio', async () => {
    fetchMock.mockRejectedValue(Object.assign(new Error('Not Found'), { statusCode: 404 }))
    const wrapper = await mountSuspended(FaqPage)
    mounted.push(wrapper)

    await vi.waitFor(() => expect(wrapper.find('h1').text()).toBe('Perguntas frequentes'))
    expect(wrapper.find('[data-faq-empty]').exists()).toBe(true)
    expect(wrapper.findAll('[data-faq-item]')).toHaveLength(0)
  })
})
