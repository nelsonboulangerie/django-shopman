// A versão nova da loja é FORÇADA (D9): a navegação recarrega no destino e, fora das
// telas protegidas, um aviso bloqueia a tela até o toque. NUNCA no checkout, no
// pedido nem no login: nem recarga, nem bloqueio. Este arquivo é a trava dessa
// exceção. Porte do `operator-kit/tests/components/OperatorPwaUpdatePrompt.test.ts`.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref, type Ref } from 'vue'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import PwaUpdatePrompt from '~/components/PwaUpdatePrompt.vue'
import { bindPwaUpdateRegistration, reloadAfterPwaUpdate } from '~/composables/usePwaUpdate'
import type { PwaCopyProjection } from '~/types/shopman'

type BeforeEach = (to: { path: string, fullPath: string }, from: { path: string }) => boolean | undefined

const state = vi.hoisted(() => ({
  path: undefined as unknown as Ref<string>,
  online: undefined as unknown as Ref<boolean>,
  beforeEach: [] as BeforeEach[]
}))

mockNuxtImport('useRoute', () => () => ({
  get path () { return state.path.value }
}))

// O roteador real segue servindo o Nuxt; só o `beforeEach` é capturado, para o teste
// disparar a navegação sem carregar páginas.
mockNuxtImport('useRouter', original => () => {
  const router = original()
  return new Proxy(router, {
    get (target, key, receiver) {
      if (key !== 'beforeEach') return Reflect.get(target, key, receiver)
      return (hook: BeforeEach) => {
        state.beforeEach.push(hook)
        return () => { state.beforeEach = state.beforeEach.filter(item => item !== hook) }
      }
    }
  })
})

/**
 * Simula a navegação do cliente: os ganchos `beforeEach` rodam e, se nenhum cancelar
 * (`false`), a rota muda. Devolve se a troca de tela no cliente aconteceu.
 */
async function navigate (from: string, to: string): Promise<boolean> {
  const cancelled = state.beforeEach.some(hook => hook({ path: to, fullPath: to }, { path: from }) === false)
  if (!cancelled) state.path.value = to
  await nextTick()
  return !cancelled
}

const PROTECTED = ['/finalizar', '/pedido/ORD-1', '/entrar', '/a']

mockNuxtImport('useOnline', () => () => state.online)

const entry = (title = '', message = '') => ({ title, message })
const copy: PwaCopyProjection = {
  offline_title: entry(),
  offline_message: entry(),
  offline_retry_cta: entry(),
  install_title: entry(),
  install_message: entry(),
  install_cta: entry(),
  install_dismiss_cta: entry(),
  manual_title: entry(),
  manual_done_cta: entry(),
  update_title: entry('A loja tem uma versão nova', 'Atualize para continuar. Sua sacola fica guardada.'),
  update_cta: entry('Atualizar')
}

function fakeWorker () {
  const needRefresh = ref(false)
  const updateServiceWorker = vi.fn().mockResolvedValue(undefined)
  const checkForUpdate = vi.fn().mockResolvedValue(true)
  bindPwaUpdateRegistration({ needRefresh, updateServiceWorker, checkForUpdate })
  return { needRefresh, updateServiceWorker, checkForUpdate }
}

const prompt = '[data-testid="pwa-update-prompt"]'

beforeEach(() => {
  state.path = ref('/menu')
  state.online = ref(true)
  state.beforeEach = []
})

afterEach(() => {
  bindPwaUpdateRegistration(null)
  vi.clearAllMocks()
})

describe('PwaUpdatePrompt: aviso que bloqueia', () => {
  it('aparece somente quando há worker em espera, com a copy da casa', async () => {
    const worker = fakeWorker()
    const wrapper = await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    expect(wrapper.find(prompt).exists()).toBe(false)

    worker.needRefresh.value = true
    await nextTick()
    expect(wrapper.find(prompt).exists()).toBe(true)
    expect(wrapper.text()).toContain('A loja tem uma versão nova')
    expect(wrapper.text()).toContain('Sua sacola fica guardada.')
    expect(wrapper.text()).toContain('Atualizar')
  })

  it('sem copy do servidor, usa o texto padrão', async () => {
    const worker = fakeWorker()
    worker.needRefresh.value = true
    const wrapper = await mountSuspended(PwaUpdatePrompt)
    expect(wrapper.text()).toContain('A loja tem uma versão nova')
  })

  it('bloqueia: diálogo modal, um único botão, e o Esc não fecha', async () => {
    const worker = fakeWorker()
    worker.needRefresh.value = true
    const wrapper = await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    expect(wrapper.findAll(`${prompt} button`)).toHaveLength(1)
    const dialog = wrapper.get(`${prompt} [role="alertdialog"]`)
    expect(dialog.attributes('aria-modal')).toBe('true')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(wrapper.find(prompt).exists()).toBe(true)
  })

  it('não aplica a versão antes do toque explícito, e aplica uma vez só', async () => {
    const worker = fakeWorker()
    worker.updateServiceWorker.mockImplementation(() => new Promise(() => {}))
    worker.needRefresh.value = true
    const wrapper = await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    expect(worker.updateServiceWorker).not.toHaveBeenCalled()

    await wrapper.get(`${prompt} button`).trigger('click')
    await wrapper.get(`${prompt} button`).trigger('click')
    expect(worker.updateServiceWorker).toHaveBeenCalledOnce()
    expect(worker.updateServiceWorker).toHaveBeenCalledWith(true)
  })

  it('deixa a loja inerte por trás, mas nunca o próprio aviso', async () => {
    const worker = fakeWorker()
    const shell = document.createElement('div')
    shell.className = 'shop-shell'
    const main = document.createElement('div')
    main.id = 'main-content'
    shell.appendChild(main)
    document.body.appendChild(shell)
    try {
      const wrapper = await mountSuspended(PwaUpdatePrompt, { props: { copy }, attachTo: shell })
      worker.needRefresh.value = true
      await nextTick()
      await nextTick()
      expect(main.inert).toBe(true)
      let node: HTMLElement | null = wrapper.get(`${prompt} button`).element as HTMLElement
      while (node) {
        expect(node.inert, node.className).not.toBe(true)
        node = node.parentElement
      }
      wrapper.unmount()
    } finally {
      shell.remove()
    }
  })

  it('NUNCA bloqueia no checkout, no pedido e no login, e volta na tela seguinte', async () => {
    const worker = fakeWorker()
    worker.needRefresh.value = true
    state.path.value = PROTECTED[0]!
    const wrapper = await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    for (const path of PROTECTED) {
      state.path.value = path
      await nextTick()
      expect(wrapper.find(prompt).exists(), path).toBe(false)
    }

    state.path.value = '/menu'
    await nextTick()
    expect(wrapper.find(prompt).exists()).toBe(true)
  })

  it('espera a rede voltar: recarregar offline cairia no casco', async () => {
    const worker = fakeWorker()
    worker.needRefresh.value = true
    state.online.value = false
    const wrapper = await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    expect(wrapper.find(prompt).exists()).toBe(false)

    state.online.value = true
    await nextTick()
    expect(wrapper.find(prompt).exists()).toBe(true)
  })

  it('sonda o servidor ao montar: o aviso não depende de o navegador lembrar de olhar', async () => {
    const worker = fakeWorker()
    await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    await nextTick()
    expect(worker.checkForUpdate).toHaveBeenCalled()
  })
})

describe('PwaUpdatePrompt: navegação carrega o destino pela versão nova', () => {
  it('com versão nova, navegar entre telas comuns cancela a troca e aplica a versão rumo ao destino', async () => {
    const worker = fakeWorker()
    await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    worker.needRefresh.value = true
    expect(await navigate('/menu', '/produto/PAO')).toBe(false)
    expect(worker.updateServiceWorker).toHaveBeenCalledOnce()
    expect(worker.updateServiceWorker).toHaveBeenCalledWith(true)

    // O worker novo assumiu: a página vai ao destino, não recarrega a origem.
    const target = { assign: vi.fn(), reload: vi.fn() }
    reloadAfterPwaUpdate(target)
    expect(target.assign).toHaveBeenCalledWith('/produto/PAO')
    expect(target.reload).not.toHaveBeenCalled()
  })

  it('sem versão nova, navegar é troca de tela comum', async () => {
    const worker = fakeWorker()
    await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    expect(await navigate('/menu', '/sacola')).toBe(true)
    expect(worker.updateServiceWorker).not.toHaveBeenCalled()
  })

  it('NUNCA recarrega entrando ou saindo do checkout, do pedido ou do login', async () => {
    const worker = fakeWorker()
    await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    worker.needRefresh.value = true
    for (const path of PROTECTED) {
      expect(await navigate('/sacola', path), `para ${path}`).toBe(true)
      expect(await navigate(path, '/menu'), `de ${path}`).toBe(true)
    }
    expect(worker.updateServiceWorker).not.toHaveBeenCalled()
  })

  it('sem rede, navegar não recarrega: a página cairia no casco offline', async () => {
    const worker = fakeWorker()
    state.online.value = false
    await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    worker.needRefresh.value = true
    expect(await navigate('/menu', '/sacola')).toBe(true)
    expect(worker.updateServiceWorker).not.toHaveBeenCalled()
  })

  it('o toque em Atualizar recarrega onde está', async () => {
    const worker = fakeWorker()
    worker.needRefresh.value = true
    const wrapper = await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    await wrapper.get(`${prompt} button`).trigger('click')
    const target = { assign: vi.fn(), reload: vi.fn() }
    reloadAfterPwaUpdate(target)
    expect(target.reload).toHaveBeenCalledOnce()
    expect(target.assign).not.toHaveBeenCalled()
  })

  it('desmontado, solta o gancho do roteador', async () => {
    fakeWorker()
    const wrapper = await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    expect(state.beforeEach).toHaveLength(1)
    wrapper.unmount()
    expect(state.beforeEach).toHaveLength(0)
  })
})
