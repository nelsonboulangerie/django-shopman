import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mountSuspended, registerEndpoint } from '@nuxt/test-utils/runtime'
import { flushPromises } from '@vue/test-utils'
import { useWhatsappReturn } from '~/composables/useWhatsappReturn'

const STORAGE_KEY = 'shopman:wa-return'
let claim = vi.fn(async () => ({ status: 'pending' }))

registerEndpoint('/api/v1/auth/whatsapp/claim/', {
  method: 'POST',
  handler: () => claim()
})

async function mountReturn (onDone = vi.fn()) {
  let result!: ReturnType<typeof useWhatsappReturn>
  const Host = defineComponent({
    setup () {
      result = useWhatsappReturn(onDone)
      return () => h('div')
    }
  })
  const wrapper = await mountSuspended(Host)
  return { result, wrapper, onDone }
}

describe('useWhatsappReturn — recuperação da volta', () => {
  beforeEach(() => {
    sessionStorage.clear()
    claim = vi.fn(async () => ({ status: 'pending' }))
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true })
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
  })

  it('persiste prazo e restaura a espera da mesma aba', async () => {
    const first = await mountReturn()
    first.result.arm()

    const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '{}')
    expect(saved.version).toBe(1)
    expect(saved.expiresAt).toBeGreaterThan(saved.startedAt)
    await first.wrapper.unmount()

    const restored = await mountReturn()
    await flushPromises()
    expect(restored.result.waiting.value).toBe(true)
    expect(claim).toHaveBeenCalledOnce()
    await restored.wrapper.unmount()
  })

  it('expõe falha de rede e deixa a conferência manual recuperável', async () => {
    claim = vi.fn(async () => { throw new Error('offline') })
    const mounted = await mountReturn()
    mounted.result.arm()

    await mounted.result.checkNow()

    expect(mounted.result.state.value).toBe('offline-or-error')
    expect(mounted.result.waiting.value).toBe(true)
    expect(sessionStorage.getItem(STORAGE_KEY)).not.toBeNull()
    await mounted.wrapper.unmount()
  })

  it('restaura a demora sem pedir que a pessoa envie outra mensagem', async () => {
    const now = Date.now()
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      version: 1,
      startedAt: now - 60_000,
      expiresAt: now + 60_000
    }))

    const mounted = await mountReturn()
    await flushPromises()

    expect(mounted.result.state.value).toBe('slow')
    await mounted.wrapper.unmount()
  })

  it('não consulta quando o visibilitychange é a saída para o WhatsApp', async () => {
    const mounted = await mountReturn()
    mounted.result.arm()
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })

    document.dispatchEvent(new Event('visibilitychange'))
    await flushPromises()

    expect(claim).not.toHaveBeenCalled()
    await mounted.wrapper.unmount()
  })

  it('restaura a expiração explicitamente, em vez de apagar o contexto', async () => {
    const now = Date.now()
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      version: 1,
      startedAt: now - 11 * 60_000,
      expiresAt: now - 60_000
    }))

    const mounted = await mountReturn()

    expect(mounted.result.state.value).toBe('expired')
    expect(sessionStorage.getItem(STORAGE_KEY)).not.toBeNull()
    await mounted.wrapper.unmount()
  })

  it('encerra a espera e limpa a persistência quando o login chega', async () => {
    claim = vi.fn(async () => ({ status: 'done', is_authenticated: true }))
    const mounted = await mountReturn()
    mounted.result.arm()

    await mounted.result.checkNow()

    expect(claim).toHaveBeenCalledOnce()
    expect(mounted.onDone).toHaveBeenCalledOnce()
    expect(mounted.result.state.value).toBe('idle')
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull()
    await mounted.wrapper.unmount()
  })
})
