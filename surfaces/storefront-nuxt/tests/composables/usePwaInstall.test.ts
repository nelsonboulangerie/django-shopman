import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import {
  isPwaInviteRouteExcluded,
  usePwaInstall
} from '~/composables/usePwaInstall'

const NOW = Date.UTC(2026, 8, 14)

function mockBrowser ({
  ios = false,
  standalone = false
}: { ios?: boolean, standalone?: boolean } = {}) {
  Object.defineProperty(navigator, 'userAgent', {
    configurable: true,
    value: ios ? 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit Safari' : 'Mozilla/5.0 (Linux; Android 15) Chrome'
  })
  Object.defineProperty(navigator, 'platform', {
    configurable: true,
    value: ios ? 'iPhone' : 'Linux armv8l'
  })
  vi.stubGlobal('matchMedia', vi.fn(() => ({
    matches: standalone,
    media: '(display-mode: standalone)',
    addEventListener: vi.fn(),
    removeEventListener: vi.fn()
  })))
}

async function mountInstall () {
  let state!: ReturnType<typeof usePwaInstall>
  const Harness = defineComponent({
    setup () {
      state = usePwaInstall({ now: () => NOW })
      return () => h('span')
    }
  })
  const wrapper = await mountSuspended(Harness)
  await nextTick()
  return { state, wrapper }
}

beforeEach(() => {
  localStorage.clear()
  mockBrowser()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('usePwaInstall', () => {
  it('captures the Android install prompt and installs only after a user action', async () => {
    const { state, wrapper } = await mountInstall()
    const prompt = vi.fn().mockResolvedValue(undefined)
    const event = new Event('beforeinstallprompt') as Event & {
      prompt: () => Promise<void>
      userChoice: Promise<{ outcome: 'accepted', platform: string }>
    }
    event.prompt = prompt
    event.userChoice = Promise.resolve({ outcome: 'accepted', platform: 'web' })

    window.dispatchEvent(event)
    await nextTick()
    expect(state.canInstall.value).toBe(true)
    expect(prompt).not.toHaveBeenCalled()

    await expect(state.install()).resolves.toBe(true)
    expect(prompt).toHaveBeenCalledOnce()
    expect(state.isStandalone.value).toBe(true)
    wrapper.unmount()
  })

  it('recognizes iOS browser mode without claiming programmatic install', async () => {
    mockBrowser({ ios: true })
    const { state, wrapper } = await mountInstall()

    expect(state.isIos.value).toBe(true)
    expect(state.isStandalone.value).toBe(false)
    expect(state.canInstall.value).toBe(false)
    wrapper.unmount()
  })

  it('recognizes standalone mode', async () => {
    mockBrowser({ standalone: true })
    const { state, wrapper } = await mountInstall()

    expect(state.isStandalone.value).toBe(true)
    expect(state.canInstall.value).toBe(false)
    wrapper.unmount()
  })

  it('silences the invite for seven days after it is shown', async () => {
    const { state, wrapper } = await mountInstall()
    state.markShown()

    expect(state.dismissedUntil.value).toBe(NOW + 7 * 24 * 60 * 60 * 1000)
    expect(state.isDismissed.value).toBe(true)
    expect(localStorage.getItem('storefront-pwa-install-dismissed-until')).toBe(String(state.dismissedUntil.value))
    wrapper.unmount()
  })

  it('excludes checkout and order tracking routes', () => {
    expect(isPwaInviteRouteExcluded('/finalizar')).toBe(true)
    expect(isPwaInviteRouteExcluded('/pedido/PED-123')).toBe(true)
    expect(isPwaInviteRouteExcluded('/menu')).toBe(false)
  })
})
