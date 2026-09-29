import { distanceMetres, type AddressPoint } from './addressMap'
import type { AddressCoordinatesSource } from './address'

export type AddressLocationDivergenceMode = 'off' | 'measure' | 'visible'
export type LocationConsistencyStatus = 'compatible' | 'diverged' | 'inconclusive' | 'unavailable'
export type LocationConsistencyReason = 'missing_target' | 'invalid_fix' | 'stale_fix' | 'low_accuracy'
export type LocationCheckTarget = 'saved' | 'search'

export interface AddressLocationDivergenceConfig {
  mode: AddressLocationDivergenceMode
  threshold_m: number
  max_accuracy_m: number
  maximum_age_ms: number
  policy_version: string
}

export interface CurrentLocationFix {
  point: AddressPoint
  accuracyM: number
  capturedAtMs: number
}

export interface LocationConsistencyResult {
  status: LocationConsistencyStatus
  accuracyBucket: 'good' | 'medium' | 'low' | 'unknown'
  reason?: LocationConsistencyReason
  policyVersion: string
}

const TARGET_UNCERTAINTY_M: Record<AddressCoordinatesSource, number> = {
  pin: 30,
  geocoded: 80,
  saved: 150
}

function validPoint (point: AddressPoint | null | undefined): point is AddressPoint {
  return !!point
    && Number.isFinite(point.lat)
    && Number.isFinite(point.lng)
    && point.lat >= -90
    && point.lat <= 90
    && point.lng >= -180
    && point.lng <= 180
}

function fixAccuracyBucket (accuracyM: number): LocationConsistencyResult['accuracyBucket'] {
  if (!Number.isFinite(accuracyM) || accuracyM <= 0) return 'unknown'
  if (accuracyM <= 80) return 'good'
  if (accuracyM <= 250) return 'medium'
  return 'low'
}

export function classifyLocationConsistency (
  target: AddressPoint | null | undefined,
  targetSource: AddressCoordinatesSource | null | undefined,
  fix: CurrentLocationFix,
  config: AddressLocationDivergenceConfig,
  nowMs = Date.now()
): LocationConsistencyResult {
  const base = {
    accuracyBucket: fixAccuracyBucket(fix.accuracyM),
    policyVersion: config.policy_version
  }
  if (!validPoint(target) || !targetSource) {
    return { ...base, status: 'unavailable', reason: 'missing_target' }
  }
  if (!validPoint(fix.point) || !Number.isFinite(fix.accuracyM) || fix.accuracyM <= 0) {
    return { ...base, status: 'inconclusive', reason: 'invalid_fix' }
  }
  if (
    !Number.isFinite(fix.capturedAtMs)
    || fix.capturedAtMs > nowMs + 5_000
    || nowMs - fix.capturedAtMs > config.maximum_age_ms + 5_000
  ) {
    return { ...base, status: 'inconclusive', reason: 'stale_fix' }
  }
  if (fix.accuracyM > config.max_accuracy_m) {
    return { ...base, status: 'inconclusive', reason: 'low_accuracy' }
  }

  const lowerBoundM = Math.max(
    0,
    distanceMetres(target, fix.point) - fix.accuracyM - TARGET_UNCERTAINTY_M[targetSource]
  )
  return {
    ...base,
    status: lowerBoundM >= config.threshold_m ? 'diverged' : 'compatible'
  }
}

/**
 * Fingerprint lives only in component memory. It intentionally excludes the
 * formatted address, CEP, customer id and saved-address id.
 */
export function locationSelectionFingerprint (
  target: AddressPoint | null | undefined,
  source: AddressCoordinatesSource | null | undefined
): string {
  if (!validPoint(target) || !source) return 'unavailable'
  return `${source}:${target.lat.toFixed(6)}:${target.lng.toFixed(6)}`
}
