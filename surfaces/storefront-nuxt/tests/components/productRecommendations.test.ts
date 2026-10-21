import { describe, it, expect, vi } from 'vitest'
import { ref, nextTick } from 'vue'
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import ProductRecommendations from '~/components/ProductRecommendations.vue'

const mocks = vi.hoisted(() => ({ execute: vi.fn(), clear: vi.fn(), intersect: null as unknown as (entries: { isIntersecting: boolean }[]) => void }))
vi.mock('@vueuse/core', async importOriginal => ({
  ...await importOriginal<typeof import('@vueuse/core')>(),
  useIntersectionObserver: (_target: unknown, callback: typeof mocks.intersect) => { mocks.intersect = callback; return { stop: vi.fn() } }
}))
mockNuxtImport('useFetch', () => () => ({ data: ref(null), status: ref('idle'), error: ref(null), execute: mocks.execute, clear: mocks.clear }))

describe('recomendações por proximidade da seção', () => {
  it('não bloqueia a PDP e só lê ao se aproximar, inclusive depois de trocar SKU', async () => {
    mocks.execute.mockClear()
    mocks.clear.mockClear()
    const wrapper = await mountSuspended(ProductRecommendations, { props: { sku: 'A' } })
    expect(mocks.execute).not.toHaveBeenCalled()
    mocks.intersect([{ isIntersecting: false }])
    expect(mocks.execute).not.toHaveBeenCalled()
    mocks.intersect([{ isIntersecting: true }])
    expect(mocks.execute).toHaveBeenCalledTimes(1)
    await wrapper.setProps({ sku: 'B' })
    await nextTick()
    expect(mocks.clear).toHaveBeenCalledTimes(1)
    expect(mocks.execute).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
})
