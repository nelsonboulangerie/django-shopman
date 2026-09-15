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

describe('payment constraints — Pix Efí no PDV', () => {
  it('não tenta inferir sandbox fora do contrato canônico', () => {
    expect(pixProviderTestConstraint(providerTest)?.provider).toBe('efi')
    expect(pixProviderTestConstraint({ pix: { ...providerTest.pix, is_test: false } })).toBeNull()
    expect(pixProviderTestConstraint({})).toBeNull()
  })

  it('mantém a borda inclusiva do provedor', () => {
    const constraint = pixProviderTestConstraint(providerTest)
    expect(exceedsPaymentConstraint(1000, constraint)).toBe(false)
    expect(exceedsPaymentConstraint(1001, constraint)).toBe(true)
  })
})
