import type { PaymentConstraintProjection, PaymentConstraintsProjection } from '~/types/shopman'

export function pixProviderTestConstraint (
  constraints: PaymentConstraintsProjection | null | undefined
): PaymentConstraintProjection | null {
  const pix = constraints?.pix
  if (!pix || pix.provider !== 'efi' || pix.mode !== 'provider_test' || !pix.is_test) return null
  if (!Number.isFinite(pix.max_amount_q) || pix.max_amount_q <= 0) return null
  return pix
}

export function exceedsPaymentConstraint (
  amountQ: number | null | undefined,
  constraint: PaymentConstraintProjection | null | undefined
): boolean {
  return Boolean(constraint && Number.isFinite(amountQ) && Number(amountQ) > constraint.max_amount_q)
}
