// O aviso de versão nova da loja: persistente, nunca descartável, nunca automático,
// calado onde a recarga perderia algo em curso. Porte do
// `operator-kit/tests/components/OperatorPwaUpdatePrompt.test.ts`.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref, type Ref } from 'vue'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import PwaUpdatePrompt from '~/components/PwaUpdatePrompt.vue'
import { bindPwaUpdateRegistration } from '~/composables/usePwaUpdate'
import type { PwaCopyProjection } from '~/types/shopman'

const state = vi.hoisted(() => ({
  path: undefined as unknown as Ref<string>,
  online: undefined as unknown as Ref<boolean>
}))

mockNuxtImport('useRoute', () => () => ({
  get path () { return state.path.value }
}))

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
  update_title: entry('Nova versão disponível'),
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
})

afterEach(() => {
  bindPwaUpdateRegistration(null)
  vi.clearAllMocks()
})

describe('PwaUpdatePrompt', () => {
  it('aparece somente quando há worker em espera, com a copy da casa', async () => {
    const worker = fakeWorker()
    const wrapper = await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    expect(wrapper.find(prompt).exists()).toBe(false)

    worker.needRefresh.value = true
    await nextTick()
    expect(wrapper.find(prompt).exists()).toBe(true)
    expect(wrapper.text()).toContain('Nova versão disponível')
    expect(wrapper.text()).toContain('Atualizar')
  })

  it('sem copy do servidor, usa o texto padrão', async () => {
    const worker = fakeWorker()
    worker.needRefresh.value = true
    const wrapper = await mountSuspended(PwaUpdatePrompt)
    expect(wrapper.text()).toContain('Nova versão disponível')
  })

  it('não tem botão de fechar: o aviso fica até o cliente atualizar', async () => {
    const worker = fakeWorker()
    worker.needRefresh.value = true
    const wrapper = await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    expect(wrapper.findAll(`${prompt} button`)).toHaveLength(1)
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

  it('cala no checkout, no pedido e no login, e volta na tela seguinte', async () => {
    const worker = fakeWorker()
    worker.needRefresh.value = true
    state.path.value = '/finalizar'
    const wrapper = await mountSuspended(PwaUpdatePrompt, { props: { copy } })
    expect(wrapper.find(prompt).exists()).toBe(false)

    state.path.value = '/pedido/ORD-1'
    await nextTick()
    expect(wrapper.find(prompt).exists()).toBe(false)

    state.path.value = '/entrar'
    await nextTick()
    expect(wrapper.find(prompt).exists()).toBe(false)

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
