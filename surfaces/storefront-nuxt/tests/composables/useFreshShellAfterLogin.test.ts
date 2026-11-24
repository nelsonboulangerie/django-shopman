// #3572: logo depois do login, a primeira página saía com a versão A para a cliente B.
// O shell do anônimo era relido só DEPOIS de a página de destino montar. Aqui a prova
// é a ordem: saindo do login, a releitura termina antes de a navegação chegar, e a
// página de destino já lê a versão que o servidor decidiu.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import { STOREFRONT_SHELL_KEY } from '~/composables/useStorefrontShell'
import { useExperience } from '~/composables/useExperience'
import { useFreshShellAfterLogin } from '~/composables/useFreshShellAfterLogin'
import type { ShellResponse } from '~/types/shopman'

const AUTH_ROUTES = new Set(['/entrar', '/a'])

function shellWith (variant: string): ShellResponse {
  return { shell: { experience: [{ ref: 'prova', variant }] }, cart: {} } as unknown as ShellResponse
}

function setShell (value: ShellResponse | undefined) {
  useNuxtApp().payload.data[STOREFRONT_SHELL_KEY] = value
}

const mounted: Array<{ unmount: () => void }> = []

async function mountGuard (refreshShell: () => Promise<unknown>) {
  const Harness = defineComponent({
    setup () {
      useFreshShellAfterLogin(path => AUTH_ROUTES.has(path), refreshShell)
      return () => h('div')
    }
  })
  const wrapper = await mountSuspended(Harness)
  mounted.push(wrapper)
}

describe('useFreshShellAfterLogin (#3572)', () => {
  afterEach(async () => {
    for (const wrapper of mounted.splice(0)) wrapper.unmount()
    setShell(undefined)
    await navigateTo('/')
  })

  it('saindo do login, a página de destino só chega depois do shell de quem entrou', async () => {
    const order: string[] = []
    await mountGuard(async () => {
      order.push(`releu em ${useRoute().path}`)
      await new Promise(resolve => setTimeout(resolve, 20))
      setShell(shellWith('b'))
    })
    await navigateTo('/entrar')
    // O shell da página de login é o do anônimo: versão padrão.
    setShell(shellWith('a'))
    const removeAfterEach = useRouter().afterEach(to => {
      // O que a página de destino leria ao montar, no instante em que a rota muda.
      const { variant } = useExperience('prova')
      order.push(`chegou ${to.path} com ${variant.value}`)
    })

    await navigateTo('/')
    removeAfterEach()

    expect(order).toEqual(['releu em /entrar', 'chegou / com b'])
  })

  it('a releitura que falha não prende a cliente no login', async () => {
    await mountGuard(() => Promise.reject(new Error('rede caiu')))
    await navigateTo('/entrar')

    await navigateTo('/menu')

    expect(useRoute().path).toBe('/menu')
  })

  it('fora do login a navegação não relê o shell', async () => {
    const refreshShell = vi.fn(() => Promise.resolve())
    await mountGuard(refreshShell)

    await navigateTo('/menu')
    await navigateTo('/sacola')
    await navigateTo('/entrar')

    expect(refreshShell).not.toHaveBeenCalled()
  })

  it('dentro do login (de /a para /entrar) também não relê', async () => {
    const refreshShell = vi.fn(() => Promise.resolve())
    await mountGuard(refreshShell)
    await navigateTo('/a')

    await navigateTo('/entrar?welcome=1')

    expect(refreshShell).not.toHaveBeenCalled()
  })
})
