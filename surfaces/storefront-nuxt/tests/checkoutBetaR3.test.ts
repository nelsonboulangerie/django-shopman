import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import {
  checkoutNotesCopy,
  couponAppliedToast,
  couponCardState,
  deliveryZoneRefused,
  rememberChoicesDescription
} from '../app/utils/checkoutFlow'

const finalizar = readFileSync(new URL('../app/pages/finalizar.vue', import.meta.url), 'utf8')

describe('recusa de zona no checkout (beta SMS-05/06)', () => {
  it('entrega fora da área fica no passo do endereço, com ou sem retirada', () => {
    expect(deliveryZoneRefused({ fulfillmentType: 'delivery', pickupSwapOffer: true, deliveryUncovered: false })).toBe(true)
    expect(deliveryZoneRefused({ fulfillmentType: 'delivery', pickupSwapOffer: false, deliveryUncovered: true })).toBe(true)
    expect(deliveryZoneRefused({ fulfillmentType: 'delivery', pickupSwapOffer: false, deliveryUncovered: false, zoneError: true })).toBe(true)
  })

  it('retirada e entrega coberta seguem', () => {
    expect(deliveryZoneRefused({ fulfillmentType: 'pickup', pickupSwapOffer: true, deliveryUncovered: true, zoneError: true })).toBe(false)
    expect(deliveryZoneRefused({ fulfillmentType: 'delivery', pickupSwapOffer: false, deliveryUncovered: false, zoneError: false })).toBe(false)
  })

  it('o passo do endereço confere a recusa antes de avançar', () => {
    const body = finalizar.slice(finalizar.indexOf('async function continueFromAddress'))
    const fn = body.slice(0, body.indexOf('\n}\n'))
    expect(fn.indexOf('zoneRefused.value')).toBeGreaterThan(-1)
    expect(fn.indexOf('zoneRefused.value')).toBeLessThan(fn.indexOf("activeStep.value = 'when'"))
  })

  it('a recusa do envio leva a página até o aviso', () => {
    const branch = finalizar.slice(finalizar.indexOf('if (pickupSwapOffer.value) {'))
    expect(branch.slice(0, branch.indexOf('} else {'))).toContain('revealZoneRefusal()')
    const sheet = finalizar.slice(finalizar.indexOf('function openConfirmSheet'))
    expect(sheet.slice(0, sheet.indexOf('confirmOpen.value = true'))).toContain('zoneRefused.value')
  })
})

describe('copy da retirada (beta PIXEXP-12, SMS-21)', () => {
  it('retirada não fala de interfone, troco nem endereço', () => {
    const copy = checkoutNotesCopy(true)
    for (const text of [copy.description, copy.placeholder, rememberChoicesDescription(true)]) {
      expect(text).not.toMatch(/interfone|troco|endere/i)
    }
  })

  it('entrega não pede troco na observação (o troco tem campo próprio)', () => {
    const copy = checkoutNotesCopy(false)
    expect(copy.description).not.toMatch(/troco/i)
    expect(rememberChoicesDescription(false)).toContain('Endereço')
  })

  it('a tela não guarda mais o texto fixo', () => {
    expect(finalizar).not.toContain('Ponto de referência, interfone, troco')
  })
})

describe('cupom sem desconto (beta SMS-04)', () => {
  it('só diz "aplicado" quando o total caiu', () => {
    const applied = { coupon_code: 'NELSON10', coupon_discount_q: 340, coupon_discount_display: 'R$ 3,40' }
    expect(couponCardState(applied)).toEqual({ status: 'applied', description: 'Desconto de R$ 3,40' })
    expect(couponAppliedToast(applied).kind).toBe('success')

    const zero = { coupon_code: 'PRIMEIRACOMPRA', coupon_discount_q: 0, coupon_discount_display: null }
    expect(couponCardState(zero).status).toBe('no_discount')
    expect(couponAppliedToast(zero)).toEqual({ kind: 'info', message: 'Este cupom não dá desconto nesta sacola.' })
    expect(couponCardState(null).status).toBe('none')
  })

  it('a frase é o motivo que o servidor mandou, nunca um palpite (beta 06/11)', () => {
    const base = { coupon_code: 'PRIMEIRACOMPRA', coupon_discount_q: 0, coupon_discount_display: null }
    const minimum = { ...base, coupon_zero_reason: 'minimum', coupon_missing_display: 'R$ 11,30' }
    expect(couponCardState(minimum)).toEqual({ status: 'no_discount', description: 'Faltam R$ 11,30 para usar este cupom.' })
    expect(couponAppliedToast(minimum)).toEqual({ kind: 'info', message: 'Faltam R$ 11,30 para usar este cupom.' })

    expect(couponCardState({ ...base, coupon_zero_reason: 'items' }).description).toBe('Nenhum item desta sacola recebe o desconto dele.')
    expect(couponCardState({ ...base, coupon_zero_reason: 'already_discounted' }).description).toContain('desconto igual ou maior')
    expect(couponCardState({ ...base, coupon_zero_reason: 'fulfillment', coupon_fulfillment_types: ['delivery'] }).description).toBe('Este cupom vale só para entrega.')
    expect(couponCardState({ ...base, coupon_zero_reason: 'unavailable' }).description).toBe('Este cupom não está mais disponível.')
    // Sem motivo, nenhuma frase inventada.
    expect(couponCardState(base).description).toBe('')
  })
})

describe('rascunho do checkout e hidratação (beta SMS-22)', () => {
  it('na carga direta o rascunho entra depois de montar, nunca durante a hidratação', () => {
    expect(finalizar).toMatch(/useNuxtApp\(\)\.isHydrating\)\s*\{\s*onMounted\(\(\) => \{ watch\(checkout, restoreCheckoutDraft/)
    expect(finalizar).toContain(':key="addressPickerKey"')
  })
})

describe('edição de endereço por confirmar (beta SMS-15)', () => {
  it('o Continuar do endereço espera a edição aberta', () => {
    expect(finalizar).toContain('@draft-pending="addressDraftPending = $event"')
    expect(finalizar).toContain("'Confirme o endereço que você está editando.'")
  })
})

describe('motivo da janela riscada (beta SMS-10)', () => {
  it('o motivo de prontidão sai uma vez, com o aviso do riscado quando há horário livre', async () => {
    const { checkoutWindowsReason } = await import('../app/utils/checkoutFlow')
    expect(checkoutWindowsReason([
      { enabled: false, reason: 'Brioche sai às 15:00.' },
      { enabled: true, reason: '' }
    ])).toBe('Brioche sai às 15:00. Antes disso, os horários ficam riscados.')
    expect(checkoutWindowsReason([{ enabled: false, reason: 'Brioche sai às 15:00.' }])).toBe('Brioche sai às 15:00.')
    expect(checkoutWindowsReason([{ enabled: true, reason: '' }])).toBe('')
    expect(finalizar).toContain('data-checkout-pickup-readiness')
  })
})

describe('horário de retirada de hoje (beta 06/11)', () => {
  it('retirada de hoje usa a grade de meias horas; encomenda, a lista de turnos', async () => {
    const { usesWindowGrid } = await import('../app/utils/checkoutFlow')
    expect(usesWindowGrid({ pickup_grid: 'half_hour' }, 'pickup')).toBe(true)
    expect(usesWindowGrid({ pickup_grid: 'canonical' }, 'pickup')).toBe(false)
    expect(usesWindowGrid({ pickup_grid: 'canonical' }, 'delivery')).toBe(true)
    expect(usesWindowGrid(null, 'pickup')).toBe(false)
  })

  it('dia sem horário diz o recebimento certo, e a tela não esconde o vazio', async () => {
    const { noWindowsMessage } = await import('../app/utils/checkoutFlow')
    expect(noWindowsMessage('pickup')).toBe('Não há horário de retirada nesse dia. Escolha outra data.')
    expect(noWindowsMessage('delivery')).toBe('Não há horário de entrega nesse dia. Escolha outra data.')
    expect(finalizar).toContain('data-checkout-pickup-slots-empty')
    expect(finalizar).toContain("'Horário da retirada'")
  })

  it('hoje encerrado diz por que "Hoje" saiu das datas, em vez de sumir calado', async () => {
    const { noWindowsMessage, todayOverMessage } = await import('../app/utils/checkoutFlow')
    expect(todayOverMessage('pickup')).toBe('Hoje já encerramos as retiradas.')
    expect(todayOverMessage('delivery')).toBe('Hoje já encerramos as entregas.')
    expect(noWindowsMessage('pickup', true)).toBe('Hoje já encerramos as retiradas. Escolha outra data.')
    expect(noWindowsMessage('delivery', true)).toBe('Hoje já encerramos as entregas. Escolha outra data.')
    expect(finalizar).toContain('data-checkout-today-over')
    expect(finalizar).toContain('checkout.value?.today_over')
  })
})

describe('linha da taxa de entrega (beta SMS-21)', () => {
  it('sem separador solto entre o endereço e a taxa', () => {
    expect(finalizar).not.toContain('&nbsp;· taxa de')
    expect(finalizar).toContain(': taxa de {{ cart.delivery_fee_display }}')
  })
})
