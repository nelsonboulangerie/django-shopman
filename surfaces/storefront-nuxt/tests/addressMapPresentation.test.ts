import { describe, expect, it } from 'vitest'
import { emptyAddressDraft } from '../app/presentation/address'
import {
  accuracyBucket,
  accuracyMessage,
  distanceMetres,
  mergeConfirmedPoint,
  pointMoved
} from '../app/presentation/addressMap'

describe('address map accuracy', () => {
  it('uses the documented inclusive buckets and rejects invalid measurements', () => {
    expect(accuracyBucket(80)).toBe('good')
    expect(accuracyBucket(80.01)).toBe('medium')
    expect(accuracyBucket(250)).toBe('medium')
    expect(accuracyBucket(250.01)).toBe('low')
    expect(accuracyBucket(Number.NaN)).toBe('unknown')
    expect(accuracyBucket(-1)).toBe('unknown')
    expect(accuracyMessage(300)).toContain('imprecisa')
  })
})

describe('confirmed delivery point', () => {
  it('detects material movement without treating map jitter as a customer edit', () => {
    const first = { lat: -23.3103, lng: -51.1628 }
    expect(distanceMetres(first, first)).toBe(0)
    expect(pointMoved(first, { lat: -23.310301, lng: -51.1628 })).toBe(false)
    expect(pointMoved(first, { lat: -23.311, lng: -51.1628 })).toBe(true)
  })

  it('keeps the exact confirmed point even when reverse returns a provider centroid', () => {
    const draft = {
      ...emptyAddressDraft(),
      street_number: '123',
      complement: 'Fundos',
      delivery_instructions: 'Portaria'
    }
    const confirmed = { lat: -23.31034567, lng: -51.16281234 }
    const merged = mergeConfirmedPoint(draft, {
      route: 'Rua Nova',
      street_number: '',
      latitude: -23.31,
      longitude: -51.16
    }, confirmed)

    expect(merged.latitude).toBe(confirmed.lat)
    expect(merged.longitude).toBe(confirmed.lng)
    expect(merged.coordinates_source).toBe('pin')
    expect(merged.street_number).toBe('123')
    expect(merged.complement).toBe('Fundos')
    expect(merged.delivery_instructions).toBe('Portaria')
  })
})

