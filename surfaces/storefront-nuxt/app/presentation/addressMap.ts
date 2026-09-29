import { mergeReverseGeocode, type AddressCoordinatesSource, type AddressDraft } from './address'
import type { StructuredAddressProjection } from '~/types/shopman'

export type AddressAccuracyBucket = 'good' | 'medium' | 'low' | 'unknown'

export interface AddressPoint {
  lat: number
  lng: number
}

export function accuracyBucket (accuracyM: number | null | undefined): AddressAccuracyBucket {
  if (typeof accuracyM !== 'number' || !Number.isFinite(accuracyM) || accuracyM < 0) return 'unknown'
  if (accuracyM <= 80) return 'good'
  if (accuracyM <= 250) return 'medium'
  return 'low'
}

export function accuracyMessage (accuracyM: number | null | undefined): string {
  const bucket = accuracyBucket(accuracyM)
  if (bucket === 'good') return 'Localização com boa precisão. Confira o ponto antes de continuar.'
  if (bucket === 'medium') return 'O ponto pode estar alguns metros fora. Confira no mapa.'
  if (bucket === 'low') return 'A localização está imprecisa. Mova o mapa até o ponto certo ou tente localizar novamente.'
  return 'Confira o ponto no mapa antes de continuar.'
}

export function distanceMetres (first: AddressPoint, second: AddressPoint): number {
  const radians = (degrees: number) => degrees * Math.PI / 180
  const latitudeDelta = radians(second.lat - first.lat)
  const longitudeDelta = radians(second.lng - first.lng)
  const firstLatitude = radians(first.lat)
  const secondLatitude = radians(second.lat)
  const haversine = Math.sin(latitudeDelta / 2) ** 2
    + Math.cos(firstLatitude) * Math.cos(secondLatitude) * Math.sin(longitudeDelta / 2) ** 2
  return 2 * 6371000 * Math.asin(Math.sqrt(haversine))
}

export function pointMoved (initial: AddressPoint, current: AddressPoint, thresholdM = 2): boolean {
  return distanceMetres(initial, current) > thresholdM
}

/**
 * Reverse geocoding describes the point; it never gets to replace the point
 * that the customer actually confirmed. Customer-authored fields survive the
 * same way they do in the existing address flow.
 */
export function mergeConfirmedPoint (
  draft: AddressDraft,
  reverse: StructuredAddressProjection | null,
  point: AddressPoint,
  source: AddressCoordinatesSource = 'pin'
): AddressDraft {
  const described = reverse ? mergeReverseGeocode(draft, reverse) : { ...draft }
  return {
    ...described,
    latitude: point.lat,
    longitude: point.lng,
    coordinates_source: source
  }
}

