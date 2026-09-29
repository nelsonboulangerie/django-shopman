import { describe, expect, it } from 'vitest'
import {
  classifyLocationConsistency,
  locationSelectionFingerprint,
  type AddressLocationDivergenceConfig
} from '../app/presentation/addressLocationConsistency'

const config: AddressLocationDivergenceConfig = {
  mode: 'visible',
  threshold_m: 500,
  max_accuracy_m: 250,
  maximum_age_ms: 30_000,
  policy_version: 'v1'
}

const target = { lat: 0, lng: 0 }
const now = 1_000_000

function metresNorth (metres: number) {
  return { lat: metres / 6_371_000 * 180 / Math.PI, lng: 0 }
}

describe('address location consistency policy', () => {
  it('uses the conservative lower bound at the policy threshold', () => {
    const below = classifyLocationConsistency(target, 'saved', {
      point: metresNorth(729), accuracyM: 80, capturedAtMs: now
    }, config, now)
    const at = classifyLocationConsistency(target, 'saved', {
      point: metresNorth(730), accuracyM: 80, capturedAtMs: now
    }, config, now)

    expect(below.status).toBe('compatible')
    expect(at.status).toBe('diverged')
  })

  it('does not warn for the documented uncertain 650m case', () => {
    const result = classifyLocationConsistency(target, 'saved', {
      point: metresNorth(650), accuracyM: 120, capturedAtMs: now
    }, config, now)

    expect(result.status).toBe('compatible')
    expect(result.accuracyBucket).toBe('medium')
  })

  it('warns for a reliable 900m mismatch', () => {
    const result = classifyLocationConsistency(target, 'saved', {
      point: metresNorth(900), accuracyM: 80, capturedAtMs: now
    }, config, now)

    expect(result.status).toBe('diverged')
    expect(result.policyVersion).toBe('v1')
  })

  it('degrades without blocking for low accuracy, stale fixes and missing targets', () => {
    expect(classifyLocationConsistency(target, 'saved', {
      point: metresNorth(3_000), accuracyM: 600, capturedAtMs: now
    }, config, now)).toMatchObject({ status: 'inconclusive', reason: 'low_accuracy' })

    expect(classifyLocationConsistency(target, 'saved', {
      point: metresNorth(900), accuracyM: 40, capturedAtMs: now - 36_000
    }, config, now)).toMatchObject({ status: 'inconclusive', reason: 'stale_fix' })

    expect(classifyLocationConsistency(null, null, {
      point: metresNorth(900), accuracyM: 40, capturedAtMs: now
    }, config, now)).toMatchObject({ status: 'unavailable', reason: 'missing_target' })
  })

  it('rejects malformed fixes and survives the antimeridian', () => {
    expect(classifyLocationConsistency(target, 'saved', {
      point: { lat: Number.NaN, lng: 0 }, accuracyM: 40, capturedAtMs: now
    }, config, now)).toMatchObject({ status: 'inconclusive', reason: 'invalid_fix' })

    const antimeridian = classifyLocationConsistency(
      { lat: 0, lng: 179.999 },
      'pin',
      { point: { lat: 0, lng: -179.999 }, accuracyM: 30, capturedAtMs: now },
      config,
      now
    )
    expect(antimeridian.status).toBe('compatible')
  })

  it('fingerprints only in-memory geometry, without address identifiers', () => {
    expect(locationSelectionFingerprint(target, 'saved')).toBe('saved:0.000000:0.000000')
    expect(locationSelectionFingerprint(null, null)).toBe('unavailable')
  })
})
