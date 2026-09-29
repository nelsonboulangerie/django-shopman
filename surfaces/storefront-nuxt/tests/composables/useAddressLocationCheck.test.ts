import { computed, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useAddressLocationCheck } from '../../app/composables/useAddressLocationCheck'

const config = computed(() => ({
  mode: 'visible' as const,
  threshold_m: 500,
  max_accuracy_m: 250,
  maximum_age_ms: 30_000,
  policy_version: 'v1'
}))

function geolocationPosition (latitude: number, accuracy = 40): GeolocationPosition {
  return {
    coords: {
      latitude,
      longitude: 0,
      accuracy,
      altitude: null,
      altitudeAccuracy: null,
      heading: null,
      speed: null,
      toJSON: () => ({})
    },
    timestamp: Date.now(),
    toJSON: () => ({})
  }
}

afterEach(() => vi.unstubAllGlobals())

describe('useAddressLocationCheck', () => {
  it('reads geolocation only after request and reports aggregate enums', async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback) => success(geolocationPosition(0.01)))
    vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } })
    const report = vi.fn()
    const check = useAddressLocationCheck({
      config,
      target: computed(() => ({ kind: 'saved' as const, point: { lat: 0, lng: 0 }, source: 'saved' as const })),
      report
    })

    expect(getCurrentPosition).not.toHaveBeenCalled()
    await check.request()

    expect(getCurrentPosition).toHaveBeenCalledOnce()
    expect(check.state.value).toBe('diverged')
    expect(report).toHaveBeenCalledWith('address.location_check.resolved', {
      target: 'saved',
      status: 'diverged',
      accuracy_bucket: 'good',
      policy_version: 'v1'
    })
    expect(JSON.stringify(report.mock.calls)).not.toMatch(/latitude|longitude|distance|0\.01/)
  })

  it('preserves the target on denial and timeout', async () => {
    const report = vi.fn()
    const target = computed(() => ({ kind: 'search' as const, point: { lat: 0, lng: 0 }, source: 'pin' as const }))
    vi.stubGlobal('navigator', {
      geolocation: {
        getCurrentPosition: (_success: PositionCallback, reject: PositionErrorCallback) => reject({ code: 1 } as GeolocationPositionError)
      }
    })
    const denied = useAddressLocationCheck({ config, target, report })
    await denied.request()

    expect(denied.state.value).toBe('failed')
    expect(denied.statusMessage.value).toContain('continua selecionado')
    expect(report).toHaveBeenCalledWith('address.location_check.failed', { target: 'search', reason: 'denied' })
  })

  it('ignores a fix that resolves after the selected target changes', async () => {
    let resolvePosition: PositionCallback | null = null
    vi.stubGlobal('navigator', {
      geolocation: {
        getCurrentPosition: (success: PositionCallback) => { resolvePosition = success }
      }
    })
    const selected = ref({ kind: 'saved' as const, point: { lat: 0, lng: 0 }, source: 'saved' as const })
    const report = vi.fn()
    const check = useAddressLocationCheck({ config, target: computed(() => selected.value), report })
    const pending = check.request()
    selected.value = { ...selected.value, point: { lat: 1, lng: 1 } }
    await nextTick()
    resolvePosition?.(geolocationPosition(0.01))
    await pending

    expect(check.state.value).toBe('idle')
    expect(report).not.toHaveBeenCalledWith('address.location_check.resolved', expect.anything())
  })
})
