// O registro do service worker e o caminho de `skipWaiting`. Porte da metade de
// registro do `operator-kit` (`pwaRegistration.client.ts` + `usePwaUpdate`).
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { bindPwaUpdateRegistration, usePwaUpdate } from '~/composables/usePwaUpdate'

const sw = vi.hoisted(() => ({
  options: undefined as undefined | { immediate?: boolean, onRegisteredSW?: (url: string, registration: unknown) => void },
  updateServiceWorker: vi.fn().mockResolvedValue(undefined)
}))

vi.mock('virtual:pwa-register/vue', async () => {
  const { ref } = await import('vue')
  return {
    useRegisterSW: (options: typeof sw.options) => {
      sw.options = options
      return {
        needRefresh: ref(false),
        offlineReady: ref(false),
        updateServiceWorker: sw.updateServiceWorker
      }
    }
  }
})

function fakeRegistration () {
  const needRefresh = ref(false)
  const updateServiceWorker = vi.fn().mockResolvedValue(undefined)
  const checkForUpdate = vi.fn().mockResolvedValue(true)
  bindPwaUpdateRegistration({ needRefresh, updateServiceWorker, checkForUpdate })
  return { needRefresh, updateServiceWorker, checkForUpdate }
}

afterEach(() => {
  bindPwaUpdateRegistration(null)
  vi.clearAllMocks()
})

describe('usePwaUpdate', () => {
  it('pede ao Workbox para pular a espera só quando update é chamado', async () => {
    const registration = fakeRegistration()
    const pwa = usePwaUpdate()

    expect(registration.updateServiceWorker).not.toHaveBeenCalled()
    await expect(pwa.update()).resolves.toBe(true)
    expect(registration.updateServiceWorker).toHaveBeenCalledWith(true)
  })

  it('espelha o worker em espera', () => {
    const registration = fakeRegistration()
    const pwa = usePwaUpdate()

    expect(pwa.needRefresh.value).toBe(false)
    registration.needRefresh.value = true
    expect(pwa.needRefresh.value).toBe(true)
  })

  it('sem registro (SSR, navegador sem SW) não estoura: devolve false', async () => {
    const pwa = usePwaUpdate()
    expect(pwa.needRefresh.value).toBe(false)
    await expect(pwa.update()).resolves.toBe(false)
    await expect(pwa.checkForUpdate()).resolves.toBe(false)
  })

  it('sonda recusada pelo navegador vira false, não exceção', async () => {
    const registration = fakeRegistration()
    registration.checkForUpdate.mockRejectedValue(new Error('offline'))
    await expect(usePwaUpdate().checkForUpdate()).resolves.toBe(false)
  })
})

describe('plugin de registro do service worker', () => {
  it('registra no boot e guarda o registro para a sonda perguntar ao servidor', async () => {
    const { default: plugin } = await import('~/plugins/pwaRegistration.client')
    await (plugin as unknown as (nuxtApp: unknown) => unknown)(useNuxtApp())

    expect(sw.options?.immediate).toBe(true)
    const pwa = usePwaUpdate()
    // Antes de o navegador entregar o registro, não há a quem perguntar.
    await expect(pwa.checkForUpdate()).resolves.toBe(false)

    const update = vi.fn().mockResolvedValue(undefined)
    sw.options?.onRegisteredSW?.('/sw.js', { update })
    await expect(pwa.checkForUpdate()).resolves.toBe(true)
    expect(update).toHaveBeenCalledOnce()

    await pwa.update()
    expect(sw.updateServiceWorker).toHaveBeenCalledWith(true)
  })
})
