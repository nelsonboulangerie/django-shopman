import { describe, expect, it } from 'vitest'
import {
  canPayForReal,
  canSimulatePayment,
  paymentMethodLabel,
  showsPaymentBlock
} from '~/presentation/payment'

// PAYMENT-TRACKING-MERGE apagou a tela de pagamento: estado terminal, poll e tom
// do alerta agora vivem no acompanhamento (o promise carrega tudo). O que sobra
// aqui é o rótulo do método e as regras de quando o bloco/caixa de teste aparecem.
describe('payment presentation — method label', () => {
  it('labels payment methods warmly instead of raw enums', () => {
    expect(paymentMethodLabel('pix')).toBe('Pix')
    expect(paymentMethodLabel('card')).toBe('Cartão de crédito')
    expect(paymentMethodLabel('cash')).toBe('Pagamento')
    expect(paymentMethodLabel(null)).toBe('Pagamento')
  })
})

const pixComCodigo = { payment_method: 'pix', pix_copy_paste: '000201...' }
const pixSemCodigo = { payment_method: 'pix' }
const cartaoComLink = { payment_method: 'card', checkout_url: 'https://pay.stripe.com/x' }
// O `payment_mock` não gera página de gateway: cartão em staging chega assim.
const cartaoMock = { payment_method: 'card', mock_payment_enabled: true }

describe('payment presentation — pagar de verdade', () => {
  it('exige código no Pix e link do gateway no cartão', () => {
    expect(canPayForReal(pixComCodigo)).toBe(true)
    expect(canPayForReal(pixSemCodigo)).toBe(false)
    expect(canPayForReal(cartaoComLink)).toBe(true)
    expect(canPayForReal(cartaoMock)).toBe(false)
  })
})

describe('payment presentation — captura simulada', () => {
  it('obedece ao backend, que já decidiu por pedido', () => {
    // `mock_payment_enabled` só vem true com ambiente de teste + intent vivo +
    // status capturável. Recalcular aqui criaria um segundo dono da pergunta.
    expect(canSimulatePayment(cartaoMock)).toBe(true)
    expect(canSimulatePayment({ ...pixComCodigo, mock_payment_enabled: true })).toBe(true)
    expect(canSimulatePayment({ ...pixSemCodigo, mock_payment_enabled: false })).toBe(false)
  })

  it('nunca aparece quando o backend não liberou (produção)', () => {
    expect(canSimulatePayment({ ...cartaoMock, mock_payment_enabled: false })).toBe(false)
    expect(canSimulatePayment(pixComCodigo)).toBe(false)
    expect(canSimulatePayment(cartaoComLink)).toBe(false)
  })
})

describe('payment presentation — bloco inline', () => {
  it('mostra o bloco no cartão mock, mesmo sem link do gateway', () => {
    // Regressão: o cartão em staging não renderizava bloco nenhum — o testador
    // via "pagamento autorizado" e esperava, sem nada para tocar.
    expect(showsPaymentBlock(cartaoMock)).toBe(true)
  })

  it('nunca mostra cartão sem link nem captura simulada (produção)', () => {
    expect(showsPaymentBlock({ payment_method: 'card' })).toBe(false)
  })

  it('mantém Pix e cartão com link como antes', () => {
    expect(showsPaymentBlock(pixComCodigo)).toBe(true)
    expect(showsPaymentBlock(pixSemCodigo)).toBe(true)
    expect(showsPaymentBlock(cartaoComLink)).toBe(true)
    expect(showsPaymentBlock({ payment_method: '' })).toBe(false)
  })
})
