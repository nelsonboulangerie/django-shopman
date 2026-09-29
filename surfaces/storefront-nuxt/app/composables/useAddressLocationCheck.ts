import { computed, getCurrentScope, onScopeDispose, ref, watch, type ComputedRef } from 'vue'
import type { AddressCoordinatesSource } from '~/presentation/address'
import {
  classifyLocationConsistency,
  locationSelectionFingerprint,
  type AddressLocationDivergenceConfig,
  type CurrentLocationFix,
  type LocationCheckTarget,
  type LocationConsistencyStatus
} from '~/presentation/addressLocationConsistency'
import type { AddressPoint } from '~/presentation/addressMap'
import type { AddressEventName } from './useStorefrontTelemetry'

export type AddressLocationCheckState = 'idle' | 'pending' | LocationConsistencyStatus | 'failed'

export interface AddressLocationCheckTarget {
  kind: LocationCheckTarget
  point: AddressPoint | null
  source: AddressCoordinatesSource | null
}

type AddressEventReporter = (event: AddressEventName, properties: Record<string, string | boolean>) => void

interface AddressLocationCheckOptions {
  config: ComputedRef<AddressLocationDivergenceConfig>
  target: ComputedRef<AddressLocationCheckTarget | null>
  report?: AddressEventReporter
}

function failureReason (error: unknown): 'denied' | 'timeout' | 'unavailable' {
  const code = (error as GeolocationPositionError | undefined)?.code
  if (code === 1) return 'denied'
  if (code === 3) return 'timeout'
  return 'unavailable'
}

function failureMessage (reason: ReturnType<typeof failureReason>): string {
  if (reason === 'denied') return 'A localização não foi liberada. Seu endereço continua selecionado.'
  if (reason === 'timeout') return 'A localização demorou para responder. Seu endereço continua selecionado.'
  return 'Não conseguimos conferir agora. Seu endereço continua selecionado.'
}

export function useAddressLocationCheck (options: AddressLocationCheckOptions) {
  const telemetry = options.report || useStorefrontTelemetry().addressEvent
  const state = ref<AddressLocationCheckState>('idle')
  const statusMessage = ref('')
  const currentFix = ref<CurrentLocationFix | null>(null)
  let sequence = 0

  const fingerprint = computed(() => {
    const target = options.target.value
    return target
      ? `${target.kind}:${locationSelectionFingerprint(target.point, target.source)}`
      : 'none'
  })

  function reset () {
    sequence += 1
    state.value = 'idle'
    statusMessage.value = ''
    currentFix.value = null
  }

  watch([fingerprint, () => options.config.value.mode], reset)

  async function request () {
    const config = options.config.value
    const target = options.target.value
    if (config.mode === 'off' || !target || state.value === 'pending') return

    const requestSequence = ++sequence
    const requestFingerprint = fingerprint.value
    state.value = 'pending'
    statusMessage.value = ''
    telemetry('address.location_check.requested', { target: target.kind, mode: config.mode })

    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      state.value = 'failed'
      statusMessage.value = 'Este navegador não informa sua localização. Seu endereço continua selecionado.'
      telemetry('address.location_check.failed', { target: target.kind, reason: 'unsupported' })
      return
    }

    try {
      const position = await new Promise<GeolocationPosition>((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          enableHighAccuracy: true,
          timeout: 10_000,
          maximumAge: config.maximum_age_ms
        })
      })
      if (requestSequence !== sequence || requestFingerprint !== fingerprint.value) return

      const fix: CurrentLocationFix = {
        point: { lat: position.coords.latitude, lng: position.coords.longitude },
        accuracyM: position.coords.accuracy,
        capturedAtMs: Number.isFinite(position.timestamp) && position.timestamp > 0
          ? position.timestamp
          : Date.now()
      }
      currentFix.value = fix
      const result = classifyLocationConsistency(target.point, target.source, fix, config)
      state.value = result.status
      statusMessage.value = result.reason === 'low_accuracy'
        ? 'Não deu para comparar com segurança. Você pode tentar de novo ou seguir com o endereço escolhido.'
        : result.reason === 'missing_target'
          ? 'Este endereço não tem um ponto preciso para comparar. Você pode seguir normalmente.'
          : ''
      telemetry('address.location_check.resolved', {
        target: target.kind,
        status: result.status,
        accuracy_bucket: result.accuracyBucket,
        policy_version: result.policyVersion
      })
      if (config.mode === 'visible' && result.status === 'diverged') {
        telemetry('address.location_mismatch.shown', {
          target: target.kind,
          accuracy_bucket: result.accuracyBucket,
          policy_version: result.policyVersion
        })
      }
    } catch (error) {
      if (requestSequence !== sequence || requestFingerprint !== fingerprint.value) return
      const reason = failureReason(error)
      state.value = 'failed'
      statusMessage.value = failureMessage(reason)
      telemetry('address.location_check.failed', { target: target.kind, reason })
    }
  }

  function recordAction (action: 'keep' | 'use_current' | 'review_map' | 'dismiss') {
    const target = options.target.value
    if (target) telemetry('address.location_mismatch.action', { action, target: target.kind })
  }

  function keep (action: 'keep' | 'dismiss' = 'keep') {
    recordAction(action)
    state.value = 'compatible'
    statusMessage.value = 'Certo. Vamos entregar no endereço escolhido.'
  }

  if (getCurrentScope()) onScopeDispose(reset)

  return {
    state,
    statusMessage,
    currentFix,
    request,
    reset,
    keep,
    recordAction
  }
}
