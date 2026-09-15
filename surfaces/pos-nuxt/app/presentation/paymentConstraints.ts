import type { POSPaymentConstraintProjection, POSPaymentConstraintsProjection } from '~/types/pos'

export function pixProviderTestConstraint (
  constraints: POSPaymentConstraintsProjection | null | undefined
): POSPaymentConstraintProjection | null {
  const pix = constraints?.pix
  if (!pix || pix.provider !== 'efi' || pix.mode !== 'provider_test' || !pix.is_test) return null
  if (!Number.isFinite(pix.max_amount_q) || pix.max_amount_q <= 0) return null
  return pix
}

export function exceedsPaymentConstraint (
  amountQ: number | null | undefined,
  constraint: POSPaymentConstraintProjection | null | undefined
): boolean {
  return Boolean(constraint && Number.isFinite(amountQ) && Number(amountQ) > constraint.max_amount_q)
}
