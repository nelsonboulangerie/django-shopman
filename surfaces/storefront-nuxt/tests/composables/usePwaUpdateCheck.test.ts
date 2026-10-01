// A sonda de versão nova (porte dos testes de sonda do
// `operator-kit/tests/composables/usePwaAutoUpdate.test.ts`). A loja não aplica
// sozinha: o último teste prova que a sonda nunca chama `updateServiceWorker`.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import { bindPwaUpdateRegistration } from '~/composables/usePwaUpdate'
import { usePwaUpdateCheck } from '~/composables/usePwaUpdateCheck'
import { PWA_UPDATE_CHECK_MS } from '~/presentation/pwaRuntime'

function fakeWorker () {
  const needRefresh = ref(false)
  const updateServiceWorker = vi.fn().mockResolvedValue(undefined)
  const checkForUpdate = vi.fn().mockResolvedValue(true)
  bindPwaUpdateRegistration({ needRefresh, updateServiceWorker, checkForUpdate })
  return { needRefresh, updateServiceWorker, checkForUpdate }
}

async function mountCheck () {
  let state!: ReturnType<typeof usePwaUpdateCheck>
  const wrapper = await mountSuspended(defineComponent({
    setup () {
      state = usePwaUpdateCheck()
      return () => h('span')
    }
  }))
  await nextTick()
  return { state, wrapper }
}

beforeEach(() => {
  // `shouldAdvanceTime`: o `mountSuspended` espera por timer real para resolver o
  // Suspense; com o relógio inteiramente parado o mount trava.
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  bindPwaUpdateRegistration(null)
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('sonda de versão nova', () => {
  it('pergunta ao servidor no boot e a cada 30 min', async () => {
    const worker = fakeWorker()
    const { wrapper } = await mountCheck()

    expect(worker.checkForUpdate).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(PWA_UPDATE_CHECK_MS)
    expect(worker.checkForUpdate).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(PWA_UPDATE_CHECK_MS)
    expect(worker.checkForUpdate).toHaveBeenCalledTimes(3)

    wrapper.unmount()
  })

  it('pergunta ao voltar do segundo plano e ao ganhar foco, com piso entre rajadas', async () => {
    const worker = fakeWorker()
    const { wrapper } = await mountCheck()
    worker.checkForUpdate.mockClear()

    await vi.advanceTimersByTimeAsync(90_000)
    document.dispatchEvent(new Event('visibilitychange'))
    await nextTick()
    expect(worker.checkForUpdate).toHaveBeenCalledTimes(1)

    window.dispatchEvent(new Event('focus'))
    await nextTick()
    expect(worker.checkForUpdate).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(90_000)
    window.dispatchEvent(new Event('focus'))
    await nextTick()
    expect(worker.checkForUpdate).toHaveBeenCalledTimes(2)

    wrapper.unmount()
  })

  it('pergunta assim que a rede volta, sem esperar o piso', async () => {
    const worker = fakeWorker()
    const { wrapper } = await mountCheck()
    worker.checkForUpdate.mockClear()

    window.dispatchEvent(new Event('online'))
    await nextTick()
    expect(worker.checkForUpdate).toHaveBeenCalledTimes(1)

    wrapper.unmount()
  })

  it('para de perguntar quando o componente é desmontado', async () => {
    const worker = fakeWorker()
    const { wrapper } = await mountCheck()
    wrapper.unmount()
    worker.checkForUpdate.mockClear()

    await vi.advanceTimersByTimeAsync(PWA_UPDATE_CHECK_MS * 3)
    window.dispatchEvent(new Event('focus'))
    expect(worker.checkForUpdate).not.toHaveBeenCalled()
  })

  it('nunca aplica sozinha: com versão nova em espera e a loja parada, só sonda', async () => {
    const worker = fakeWorker()
    const { state, wrapper } = await mountCheck()
    worker.needRefresh.value = true
    await nextTick()

    await vi.advanceTimersByTimeAsync(PWA_UPDATE_CHECK_MS * 2)
    expect(state.needRefresh.value).toBe(true)
    expect(worker.updateServiceWorker).not.toHaveBeenCalled()

    wrapper.unmount()
  })
})
