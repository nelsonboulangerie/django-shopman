// OC-21: a loja lê a versão que o servidor decidiu. O consumidor aqui é de TESTE (o
// OC-33 é que traz a primeira tela B, depois da aprovação L2): ele só mostra qual
// versão o `useExperience` entrega a partir do shell que o `app.vue` já buscou.
import { describe, it, expect, beforeEach } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import { STOREFRONT_SHELL_KEY } from '~/composables/useStorefrontShell'
import { useExperience } from '~/composables/useExperience'
import type { ExperienceProjection, ShellResponse } from '~/types/shopman'

function shellWith (experience?: ExperienceProjection[]): ShellResponse {
  return { shell: { experience }, cart: {} } as unknown as ShellResponse
}

function setShell (value: ShellResponse | undefined) {
  useNuxtApp().payload.data[STOREFRONT_SHELL_KEY] = value
}

const TestConsumer = defineComponent({
  setup () {
    const { variant, is } = useExperience('prova')
    return () => h('p', { 'data-variant': variant.value }, is('b') ? 'versão B' : 'versão A')
  }
})

describe('useExperience', () => {
  beforeEach(() => setShell(undefined))

  it('sem shell, a versão é a padrão "a"', async () => {
    const wrapper = await mountSuspended(TestConsumer)
    expect(wrapper.find('p').attributes('data-variant')).toBe('a')
    expect(wrapper.text()).toBe('versão A')
  })

  it('experimento ausente do shell (regra desligada) é a padrão', async () => {
    setShell(shellWith([{ ref: 'outro', variant: 'b' }]))
    const wrapper = await mountSuspended(TestConsumer)
    expect(wrapper.find('p').attributes('data-variant')).toBe('a')
  })

  it('shell sem o campo (convivência) é a padrão', async () => {
    setShell(shellWith(undefined))
    const wrapper = await mountSuspended(TestConsumer)
    expect(wrapper.find('p').attributes('data-variant')).toBe('a')
  })

  it('mostra a versão que o servidor decidiu para quem está na coorte', async () => {
    setShell(shellWith([{ ref: 'outro', variant: 'a' }, { ref: 'prova', variant: 'b' }]))
    const wrapper = await mountSuspended(TestConsumer)
    expect(wrapper.find('p').attributes('data-variant')).toBe('b')
    expect(wrapper.text()).toBe('versão B')
  })

  it('segue o shell quando ele é relido (o login traz a versão nova sem recarregar)', async () => {
    setShell(shellWith([{ ref: 'prova', variant: 'a' }]))
    const wrapper = await mountSuspended(TestConsumer)
    expect(wrapper.text()).toBe('versão A')

    setShell(shellWith([{ ref: 'prova', variant: 'b' }]))
    await nextTick()
    expect(wrapper.text()).toBe('versão B')

    // Kill switch no servidor: a regra some do shell e a tela volta à padrão.
    setShell(shellWith([]))
    await nextTick()
    expect(wrapper.text()).toBe('versão A')
  })

  it('nada na URL escolhe a versão (D1)', async () => {
    setShell(shellWith([{ ref: 'prova', variant: 'a' }]))
    await navigateTo('/?experience=b&prova=b&variant=b')
    const wrapper = await mountSuspended(TestConsumer)
    expect(wrapper.find('p').attributes('data-variant')).toBe('a')
  })
})
