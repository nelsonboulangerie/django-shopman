// Loja viva (WP-L04): a casa abre e fecha sem evento. A tela relê o estado logo
// depois da virada do horário que o servidor mandou.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mockNuxtImport } from '@nuxt/test-utils/runtime'
import { nextTick, ref } from 'vue'
import { resetLiveStoreForTests } from '~/composables/useLiveStore'
import {
  SHOP_BOUNDARY_GRACE_MS,
  SHOP_BOUNDARY_RETRY_MS,
  msUntilClock,
  nextShopBoundaryMs,
  useLiveShopStatus
} from '~/composables/useLiveShopStatus'
import type { ShopStatusProjection } from '~/types/shopman'

mockNuxtImport('useShopmanApiPath', () => () => (path: string) => path)

const MINUTE = 60_000

function status (overrides: Partial<ShopStatusProjection> = {}): ShopStatusProjection {
  return {
    is_open: true,
    label: 'Aberta',
    message: null,
    next_opening: null,
    opens_at: '07:00',
    closes_at: '19:00',
    ...overrides
  }
}

describe('msUntilClock', () => {
  const now = new Date(2026, 10, 19, 18, 30, 0)

  it('conta até a hora de hoje que ainda não chegou', () => {
    expect(msUntilClock('19:00', now)).toBe(30 * MINUTE)
  })

  it('hora que já passou é a de amanhã', () => {
    expect(msUntilClock('07:00', now)).toBe((12 * 60 + 30) * MINUTE)
  })

  it('a hora exata de agora é a de amanhã, não zero', () => {
    expect(msUntilClock('18:30', now)).toBe(24 * 60 * MINUTE)
  })

  it('hora ilegível ou ausente não agenda nada', () => {
    expect(msUntilClock(null, now)).toBeNull()
    expect(msUntilClock('', now)).toBeNull()
    expect(msUntilClock('às 7h', now)).toBeNull()
    expect(msUntilClock('25:00', now)).toBeNull()
  })
})

describe('nextShopBoundaryMs', () => {
  const now = new Date(2026, 10, 19, 18, 30, 0)

  it('aberta: a próxima virada é o fechamento', () => {
    expect(nextShopBoundaryMs(status(), now)).toBe(30 * MINUTE)
  })

  it('fechada: a próxima virada é a abertura', () => {
    expect(nextShopBoundaryMs(status({ is_open: false }), now)).toBe((12 * 60 + 30) * MINUTE)
  })

  it('sem estado ou sem a hora da virada, nada', () => {
    expect(nextShopBoundaryMs(null, now)).toBeNull()
    expect(nextShopBoundaryMs(status({ closes_at: null }), now)).toBeNull()
  })
})

describe('useLiveShopStatus', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 10, 19, 18, 30, 0))
    resetLiveStoreForTests()
  })

  afterEach(() => {
    resetLiveStoreForTests()
    vi.useRealTimers()
  })

  it('relê logo depois do fechamento, e de novo um minuto adiante', () => {
    const refresh = vi.fn()
    const live = useLiveShopStatus(() => status(), refresh)!
    live.arm()

    vi.advanceTimersByTime(30 * MINUTE + SHOP_BOUNDARY_GRACE_MS - 1)
    expect(refresh).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(refresh).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(SHOP_BOUNDARY_RETRY_MS)
    expect(refresh).toHaveBeenCalledTimes(2)
    live.clear()
  })

  it('quando o estado muda, a próxima virada é rearmada', async () => {
    const current = ref(status())
    const refresh = vi.fn()
    const live = useLiveShopStatus(() => current.value, refresh)!
    live.arm()

    // O servidor disse que fechou: a próxima virada passa a ser a abertura.
    current.value = status({ is_open: false, label: 'Fechada' })
    await nextTick()
    vi.advanceTimersByTime(30 * MINUTE + SHOP_BOUNDARY_GRACE_MS + SHOP_BOUNDARY_RETRY_MS)
    expect(refresh).not.toHaveBeenCalled()

    vi.advanceTimersByTime(12 * 60 * MINUTE)
    expect(refresh).toHaveBeenCalledTimes(2)
    live.clear()
  })

  it('releitura que falha não derruba a página', async () => {
    const refresh = vi.fn().mockRejectedValue(new Error('502'))
    const live = useLiveShopStatus(() => status(), refresh)!
    live.arm()

    await vi.advanceTimersByTimeAsync(30 * MINUTE + SHOP_BOUNDARY_GRACE_MS)

    expect(refresh).toHaveBeenCalledTimes(1)
    live.clear()
  })
})
