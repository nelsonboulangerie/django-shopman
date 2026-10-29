// U6 (laudo 23/10): o checkout incerto confere de novo com espera crescente até
// achar o pedido ou chegar ao teto, em vez de perguntar uma vez só.
import { describe, expect, it, vi } from 'vitest'
import { CHECKOUT_RECOVERY_DELAYS_MS, startCheckoutRecovery } from '../app/utils/checkoutRecovery'

const instant = (waits: number[]) => (ms: number) => { waits.push(ms); return Promise.resolve() }

describe('startCheckoutRecovery', () => {
  it('confere até o pedido aparecer e para ali', async () => {
    const waits: number[] = []
    const attempt = vi.fn()
      .mockResolvedValueOnce(false)
      .mockRejectedValueOnce(new Error('rede'))
      .mockResolvedValueOnce(true)
    const loop = startCheckoutRecovery(attempt, CHECKOUT_RECOVERY_DELAYS_MS, instant(waits))

    await expect(loop.done).resolves.toBe(true)
    expect(attempt).toHaveBeenCalledTimes(3)
    expect(waits).toEqual([2_000, 4_000, 8_000])
  })

  it('a espera cresce e tem teto: desiste depois da última conferência', async () => {
    const waits: number[] = []
    const attempt = vi.fn().mockResolvedValue(false)
    const loop = startCheckoutRecovery(attempt, CHECKOUT_RECOVERY_DELAYS_MS, instant(waits))

    await expect(loop.done).resolves.toBe(false)
    expect(attempt).toHaveBeenCalledTimes(CHECKOUT_RECOVERY_DELAYS_MS.length)
    expect(waits).toEqual([...CHECKOUT_RECOVERY_DELAYS_MS])
    for (let i = 1; i < waits.length; i++) expect(waits[i]!).toBeGreaterThanOrEqual(waits[i - 1]!)
    // Teto: ~1min30, não um laço sem fim.
    expect(waits.reduce((a, b) => a + b, 0)).toBeLessThanOrEqual(120_000)
  })

  it('cancelar interrompe as conferências que faltam', async () => {
    let release: () => void = () => {}
    const wait = () => new Promise<void>((resolve) => { release = resolve })
    const attempt = vi.fn().mockResolvedValue(false)
    const loop = startCheckoutRecovery(attempt, [10, 10, 10], wait)

    loop.cancel()
    release()
    await expect(loop.done).resolves.toBe(false)
    expect(attempt).not.toHaveBeenCalled()
  })
})
