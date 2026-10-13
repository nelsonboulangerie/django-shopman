// Distância, "o ponto mexeu?" e a fusão do ponto confirmado são regra da casa e
// moram no módulo gêmeo (`addressForm.ts`, o mesmo do PDV). Aqui fica a voz da
// loja para a precisão do GPS do cliente, que o balcão não usa.
export { distanceMetres, mergeConfirmedPoint, pointMoved } from './addressForm'
export type { AddressPoint } from './addressForm'

export type AddressAccuracyBucket = 'good' | 'medium' | 'low' | 'unknown'

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
