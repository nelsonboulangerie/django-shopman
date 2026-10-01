// A versão nova da loja é FORÇADA (D9): a navegação recarrega no destino e, fora das
// telas protegidas, um aviso bloqueia a tela até o toque. NUNCA no checkout, no
// pedido nem no login: nem recarga, nem bloqueio. Este arquivo é a trava dessa
// exceção. Porte do `operator-kit/tests/components/OperatorPwaUpdatePrompt.test.ts`.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref, type Ref } from 'vue'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import PwaUpdatePrompt from '~/components/PwaUpdatePrompt.vue'
import { bindPwaUpdateRegistration } from '~/composables/usePwaUpdate'
import type { PwaCopyProjection } from '~/types/shopman'

type AfterEach = (to: { path: string }, from: { path: string }) => void

const state = vi.hoisted(() => ({
  path: undefined as unknown as Ref<string>,
  online: undefined as unknown as Ref<boolean>,
  afterEach: [] as AfterEach[]
}))

mockNuxtImport('useRoute', () => () => ({
  get path () { return state.path.value }
}))

// O roteador real segue servindo o Nuxt; só o `afterEach` é capturado, para o teste
// disparar a navegação sem carregar páginas.
mockNuxtImport('useRouter', original => () => {
  const router = original()
  return new Proxy(router, {
    get (target, key, receiver) {
      if (key !== 'afterEach') return Reflect.get(target, key, receiver)
      return (hook: AfterEach) => {
        state.afterEach.push(hook)
        return () => { state.afterEach = state.afterEach.filter(item => item !== hook) }
      }
    }
  })
})

/** Simula a navegação do cliente: a rota muda e os ganchos `afterEach` rodam. */
async function navigate (from: string, to: string) {
  state.path.value = to
  for (const hook of state.afterEach) hook({ path: to }, { path: from })
  await nextTick()
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
  state.afterEach = []
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

describe('PwaUpdatePrompt: navegação recarrega no destino', () => {
  it('com versão nova, navegar entre telas comuns aplica a versão (recarga no destino)', async () => {
    const worker = fakeWorker()
    await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    worker.needRefresh.value = true
    await navigate('/menu', '/produto/PAO')
    expect(worker.updateServiceWorker).toHaveBeenCalledOnce()
    expect(worker.updateServiceWorker).toHaveBeenCalledWith(true)
  })

  it('sem versão nova, navegar não recarrega', async () => {
    const worker = fakeWorker()
    await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    await navigate('/menu', '/sacola')
    expect(worker.updateServiceWorker).not.toHaveBeenCalled()
  })

  it('NUNCA recarrega entrando ou saindo do checkout, do pedido ou do login', async () => {
    const worker = fakeWorker()
    await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    worker.needRefresh.value = true
    for (const path of PROTECTED) {
      await navigate('/sacola', path)
      await navigate(path, '/menu')
    }
    expect(worker.updateServiceWorker).not.toHaveBeenCalled()
  })

  it('sem rede, navegar não recarrega: a página cairia no casco offline', async () => {
    const worker = fakeWorker()
    state.online.value = false
    await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    worker.needRefresh.value = true
    await navigate('/menu', '/sacola')
    expect(worker.updateServiceWorker).not.toHaveBeenCalled()
  })

  it('desmontado, solta o gancho do roteador', async () => {
    fakeWorker()
    const wrapper = await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    expect(state.afterEach).toHaveLength(1)
    wrapper.unmount()
    expect(state.afterEach).toHaveLength(0)
  })
})
