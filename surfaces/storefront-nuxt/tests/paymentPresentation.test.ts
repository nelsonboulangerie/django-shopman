import { describe, expect, it } from 'vitest'
import {
  canPayForReal,
  canSimulatePayment,
  isHostedCheckout,
  showsPaymentBlock
} from '~/presentation/payment'

// PAYMENT-TRACKING-MERGE apagou a tela de pagamento: estado terminal, poll e tom
// do alerta agora vivem no acompanhamento (o promise carrega tudo). O que sobra
// aqui são as regras de quando o bloco/caixa de teste aparecem — o RÓTULO do
// método saiu daqui de propósito: o de-para vivia duplicado no cliente e o
// operador que renomeasse "Cartão" no Admin via o checkout obedecer e o
// acompanhamento não. Agora vem pronto em `promise.payment_method_label`.

const pixComCodigo = { payment_method: 'pix', pix_copy_paste: '000201...' }
const pixSemCodigo = { payment_method: 'pix' }
const cartaoComLink = { payment_method: 'card', checkout_url: 'https://pay.stripe.com/x' }
// O `payment_mock` não gera página de gateway: cartão em staging chega assim.
const cartaoMock = { payment_method: 'card', mock_payment_enabled: true }
// Link de pagamento do balcão: pedido remoto anotado no PDV, o cliente paga do
// celular. É a mesma sessão hospedada do cartão, com outro rótulo.
const linkComUrl = { payment_method: 'link', checkout_url: 'https://pay.stripe.com/l' }

describe('payment presentation — sessão hospedada', () => {
  it('cartão e link abrem a URL do gateway; o resto não', () => {
    expect(isHostedCheckout('card')).toBe(true)
    expect(isHostedCheckout('link')).toBe(true)
    expect(isHostedCheckout('pix')).toBe(false)
    expect(isHostedCheckout('cash')).toBe(false)
    expect(isHostedCheckout(null)).toBe(false)
  })
})

describe('payment presentation — pagar de verdade', () => {
  it('exige código no Pix e link do gateway no cartão', () => {
    expect(canPayForReal(pixComCodigo)).toBe(true)
    expect(canPayForReal(pixSemCodigo)).toBe(false)
    expect(canPayForReal(cartaoComLink)).toBe(true)
    expect(canPayForReal(cartaoMock)).toBe(false)
  })

  it('o link do balcão paga de verdade pela mesma URL do gateway', () => {
    // Regressão: o pedido de link chegava com `checkout_url` e a página não
    // desenhava botão nenhum — quem voltava ao pedido não achava onde pagar.
    expect(canPayForReal(linkComUrl)).toBe(true)
    expect(canPayForReal({ payment_method: 'link' })).toBe(false)
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

  it('mostra o bloco do link com URL, e nunca sem URL nem simulador', () => {
    expect(showsPaymentBlock(linkComUrl)).toBe(true)
    expect(showsPaymentBlock({ payment_method: 'link' })).toBe(false)
    expect(showsPaymentBlock({ payment_method: 'link', mock_payment_enabled: true })).toBe(true)
  })
})
