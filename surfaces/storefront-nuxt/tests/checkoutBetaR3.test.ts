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

describe('motivo da retirada (beta SMS-10)', () => {
  it('o motivo de prontidão é um só e ignora os motivos de cada turno', async () => {
    const { pickupReadinessReason } = await import('../app/utils/checkoutFlow')
    expect(pickupReadinessReason([
      { enabled: false, reason: 'Horário já passou' },
      { enabled: false, reason: 'Brioche sai às 15:00.' },
      { enabled: true, reason: '' }
    ])).toBe('Brioche sai às 15:00.')
    expect(pickupReadinessReason([{ enabled: false, reason: 'Loja fechada hoje' }])).toBe('')
    expect(finalizar).toContain('data-checkout-pickup-readiness')
  })
})

describe('linha da taxa de entrega (beta SMS-21)', () => {
  it('sem separador solto entre o endereço e a taxa', () => {
    expect(finalizar).not.toContain('&nbsp;· taxa de')
    expect(finalizar).toContain(': taxa de {{ cart.delivery_fee_display }}')
  })
})
