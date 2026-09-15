import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import PwaUpdateToast from '~/components/PwaUpdateToast.vue'
import type { PwaCopyProjection } from '~/types/shopman'

const pwaMock = vi.hoisted(() => ({
  updateServiceWorker: vi.fn().mockResolvedValue(undefined),
  needRefresh: undefined as unknown as { value: boolean },
  sonner: vi.fn()
}))

vi.mock('virtual:pwa-register/vue', async () => {
  const { ref } = await import('vue')
  pwaMock.needRefresh = ref(false)
  return {
    useRegisterSW: () => ({
      needRefresh: pwaMock.needRefresh,
      offlineReady: ref(false),
      updateServiceWorker: pwaMock.updateServiceWorker
    })
  }
})

vi.mock('vue-sonner', async (importOriginal) => ({
  ...await importOriginal<typeof import('vue-sonner')>(),
  toast: pwaMock.sonner
}))

const entry = (title = '', message = '') => ({ title, message })
const copy: PwaCopyProjection = {
  offline_title: entry(),
  offline_message: entry(),
  offline_retry_cta: entry(),
  install_title: entry(),
  install_message: entry(),
  install_cta: entry(),
  install_dismiss_cta: entry(),
  ios_title: entry(),
  ios_message: entry(),
  ios_share_step: entry(),
  ios_add_step: entry(),
  ios_done_cta: entry(),
  update_title: entry('Nova versão disponível'),
  update_cta: entry('Atualizar')
}

describe('usePwaUpdate', () => {
  beforeEach(() => {
    pwaMock.needRefresh.value = false
    pwaMock.updateServiceWorker.mockClear()
    pwaMock.sonner.mockClear()
  })

  it('shows a controlled update action when the worker is waiting', async () => {
    await mountSuspended(PwaUpdateToast, { props: { copy } })
    pwaMock.needRefresh.value = true
    await nextTick()

    expect(pwaMock.sonner).toHaveBeenCalledWith('Nova versão disponível', expect.objectContaining({
      action: expect.objectContaining({ label: 'Atualizar' })
    }))
  })

  it('asks Workbox to skip waiting only when update is called', async () => {
    const { usePwaUpdate } = await import('~/composables/usePwaUpdate')
    const pwa = usePwaUpdate()

    expect(pwaMock.updateServiceWorker).not.toHaveBeenCalled()
    await pwa.update()
    expect(pwaMock.updateServiceWorker).toHaveBeenCalledWith(true)
  })
})
