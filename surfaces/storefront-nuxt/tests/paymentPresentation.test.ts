import { describe, expect, it } from 'vitest'
import { paymentMethodLabel } from '~/presentation/payment'

// PAYMENT-TRACKING-MERGE apagou a tela de pagamento: estado terminal, poll e tom
// do alerta agora vivem no acompanhamento (o promise carrega tudo). O único
// helper puro que sobra do pagamento é o rótulo acolhedor do método.
describe('payment presentation — method label', () => {
  it('labels payment methods warmly instead of raw enums', () => {
    expect(paymentMethodLabel('pix')).toBe('Pix')
    expect(paymentMethodLabel('card')).toBe('Cartão de crédito')
    expect(paymentMethodLabel('cash')).toBe('Pagamento')
    expect(paymentMethodLabel(null)).toBe('Pagamento')
  })
})
