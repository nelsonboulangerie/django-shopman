// EXPERIMENT(duvida-no-ponto) remove_after 2027-02-20
// OC-33 B3: a dúvida respondida onde ela aparece. Versão A: a home de sempre (6
// perguntas e "Ver todas as perguntas"). Versão B: a home fica só com o caminho para
// /faq, e a sacola mostra as perguntas dela, recolhidas.
import { beforeEach, describe, expect, it } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import FaqAtPoint from '~/components/FaqAtPoint.vue'
import HomeFaqSection from '~/components/HomeFaqSection.vue'
import { STOREFRONT_SHELL_KEY } from '~/composables/useStorefrontShell'
import type { FAQItemProjection, ShellResponse } from '~/types/shopman'

const SHELL_FAQ: FAQItemProjection[] = [
  { ref: 'delivery', question: 'Vocês fazem entrega?', answer: 'Sim. Fazemos entrega.' },
  { ref: 'hours', question: 'Quais são os horários de funcionamento?', answer: 'Seg a sáb: 7h às 19h' },
  { ref: 'location', question: 'Onde vocês ficam?', answer: 'Ficamos na Rua X, 10.' },
  { ref: 'payment', question: 'Como posso pagar?', answer: 'Você paga com Pix ou cartão.' },
  { ref: 'preorder', question: 'Posso encomendar para outro dia?', answer: 'Sim. Ao finalizar o pedido, você escolhe o dia.' },
  { ref: 'allergens', question: 'Os produtos têm alérgenos?', answer: 'Produzimos em cozinha compartilhada.' },
  { ref: 'contact', question: 'Como falar com vocês?', answer: 'Por telefone.' }
]

function setShell (variant: 'a' | 'b' | null) {
  useNuxtApp().payload.data[STOREFRONT_SHELL_KEY] = {
    shell: { faq: SHELL_FAQ, experience: variant ? [{ ref: 'duvida-no-ponto', variant }] : [] },
    cart: {}
  } as unknown as ShellResponse
}

const heading = { title: 'Perguntas frequentes', message: 'O que mais nos perguntam.' }

describe('home: a seção de dúvidas', () => {
  beforeEach(() => setShell(null))

  for (const variant of [null, 'a'] as const) {
    it(`versão A (${variant ?? 'sem experimento'}): igual ao main, 6 perguntas e "Ver todas as perguntas"`, async () => {
      setShell(variant)
      const faq = SHELL_FAQ.slice(0, 6)
      const wrapper = await mountSuspended(HomeFaqSection, { props: { faq, heading } })
      const section = wrapper.find('section#duvidas-frequentes')
      expect(section.exists()).toBe(true)
      expect(section.find('h2').text()).toBe('Perguntas frequentes')
      expect(section.text()).toContain('O que mais nos perguntam.')
      expect(section.findAll('[data-slot="accordion-trigger"]').map(t => t.text())).toEqual(faq.map(item => item.question))
      expect(section.find('a[href="/faq"]').text()).toBe('Ver todas as perguntas')
      expect(wrapper.find('[data-home-faq-link]').exists()).toBe(false)
    })
  }

  it('versão B: a home perde a lista e fica só com o link para /faq', async () => {
    setShell('b')
    const wrapper = await mountSuspended(HomeFaqSection, { props: { faq: SHELL_FAQ.slice(0, 6), heading } })
    expect(wrapper.find('#duvidas-frequentes').exists()).toBe(false)
    expect(wrapper.find('[data-slot="accordion"]').exists()).toBe(false)
    const link = wrapper.find('[data-home-faq-link] a[href="/faq"]')
    expect(link.exists()).toBe(true)
    expect(link.text()).toBe('Dúvidas frequentes')
    for (const item of SHELL_FAQ) expect(wrapper.text()).not.toContain(item.question)
  })
})

describe('FaqAtPoint: as perguntas do ponto, recolhidas, com a resposta da FAQ', () => {
  beforeEach(() => setShell('b'))

  const expected = {
    cart: ['Vocês fazem entrega?', 'Quais são os horários de funcionamento?', 'Posso encomendar para outro dia?']
  } as const

  for (const [point, questions] of Object.entries(expected)) {
    it(`${point}: ${questions.length} pergunta(s), todas fechadas`, async () => {
      const wrapper = await mountSuspended(FaqAtPoint, { props: { point: point as keyof typeof expected } })
      const section = wrapper.find(`[data-faq-point="${point}"]`)
      expect(section.exists()).toBe(true)
      expect(section.find('h2').text()).toBe('Dúvidas frequentes')
      expect(section.attributes('aria-labelledby')).toBe(section.find('h2').attributes('id'))
      const triggers = section.findAll('[data-slot="accordion-trigger"]')
      expect(triggers.map(t => t.text())).toEqual([...questions])
      // Recolhidas: nenhuma resposta aberta até a pessoa pedir.
      for (const trigger of triggers) expect(trigger.attributes('aria-expanded')).toBe('false')
    })
  }

  it('abre a resposta que a FAQ dá, sem reescrita', async () => {
    const wrapper = await mountSuspended(FaqAtPoint, { props: { point: 'cart' } })
    await wrapper.find('[data-slot="accordion-trigger"]').trigger('click')
    expect(wrapper.find('[data-faq-point-answer="delivery"]').text()).toBe('Sim. Fazemos entrega.')
  })

  it('sem pergunta para o ponto, nada (nem o título)', async () => {
    useNuxtApp().payload.data[STOREFRONT_SHELL_KEY] = { shell: { faq: [] }, cart: {} } as unknown as ShellResponse
    const wrapper = await mountSuspended(FaqAtPoint, { props: { point: 'cart' } })
    expect(wrapper.find('[data-faq-point]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Dúvidas frequentes')
  })
})
