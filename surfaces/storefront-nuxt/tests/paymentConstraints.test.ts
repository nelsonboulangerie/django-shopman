import { describe, expect, it } from 'vitest'
import { exceedsPaymentConstraint, pixProviderTestConstraint } from '~/presentation/paymentConstraints'

const providerTest = {
  pix: {
    provider: 'efi',
    environment: 'sandbox',
    mode: 'provider_test',
    is_test: true,
    max_amount_q: 1000,
    max_amount_display: 'R$ 10,00',
    message: 'Limite temporário do Pix.'
  }
}

describe('payment constraints — Pix Efí', () => {
  it('só ativa pelo contrato explícito do backend', () => {
    expect(pixProviderTestConstraint(providerTest)?.max_amount_q).toBe(1000)
    expect(pixProviderTestConstraint({ pix: { ...providerTest.pix, mode: 'live', is_test: false } })).toBeNull()
    expect(pixProviderTestConstraint({ pix: { ...providerTest.pix, provider: 'mock' } })).toBeNull()
    expect(pixProviderTestConstraint(undefined)).toBeNull()
  })

  it('aceita R$ 10,00 e bloqueia somente acima do teto', () => {
    const constraint = pixProviderTestConstraint(providerTest)
    expect(exceedsPaymentConstraint(999, constraint)).toBe(false)
    expect(exceedsPaymentConstraint(1000, constraint)).toBe(false)
    expect(exceedsPaymentConstraint(1001, constraint)).toBe(true)
  })
})
