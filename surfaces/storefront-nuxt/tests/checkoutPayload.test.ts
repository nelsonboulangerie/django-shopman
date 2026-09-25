import { describe, expect, it } from 'vitest'
import { buildCheckoutPayload, type CheckoutFormState } from '../app/utils/checkoutPayload'

const deliveryState: CheckoutFormState = {
  name: '  Maria Silva ',
  phone: ' 55 43 98123-4567 ',
  fulfillment_type: 'delivery',
  saved_address_id: 12,
  delivery_address: ' Rua das Flores, 10 ',
  delivery_address_structured: {
    formatted_address: 'Rua das Flores, 10',
    route: 'Rua das Flores',
    street_number: '10',
    neighborhood: 'Centro',
    city: 'Londrina',
    state_code: 'PR',
    postal_code: '86000-000',
    latitude: -23.31,
    longitude: -51.16,
    place_id: 'place-123'
  },
  delivery_complement: ' Ap 4 ',
  delivery_instructions: ' Portaria ',
  delivery_date: '2026-05-16',
  delivery_time_slot: 'slot-1',
  payment_method: 'pix',
  notes: ' Sem talher ',
  is_gift: false,
  recipient_name: '',
  recipient_phone: '',
  gift_message: '',
  gift_hide_values: false,
  save_as_default: true,
  change_for: '',
  fiscal_tax_id: '529.982.247-25'
}

describe('checkout payload contract', () => {
  it('serializes canonical checkout fields with stable idempotency key', () => {
    const payload = buildCheckoutPayload(deliveryState, 'checkout-fixed', true)

    expect(payload).toMatchObject({
      idempotency_key: 'checkout-fixed',
      name: 'Maria Silva',
      phone: '55 43 98123-4567',
      fulfillment_type: 'delivery',
      saved_address_id: 12,
      delivery_address: 'Rua das Flores, 10',
      delivery_complement: 'Ap 4',
      delivery_instructions: 'Portaria',
      delivery_date: '2026-05-16',
      delivery_time_slot: 'slot-1',
      payment_method: 'pix',
      notes: 'Sem talher',
      save_as_default: true,
      use_loyalty: true
    })
    expect(payload.delivery_address_structured.place_id).toBe('place-123')
  })

  it('propagates save_as_default opt-out (desmarcado → false)', () => {
    const payload = buildCheckoutPayload(
      { ...deliveryState, save_as_default: false },
      'checkout-optout',
      false
    )

    expect(payload.save_as_default).toBe(false)
  })

  it('does not leak delivery address data for pickup payloads', () => {
    const payload = buildCheckoutPayload(
      { ...deliveryState, fulfillment_type: 'pickup' },
      'checkout-pickup',
      false
    )

    expect(payload.saved_address_id).toBeNull()
    expect(payload.delivery_address).toBe('')
    expect(payload.delivery_address_structured).toEqual({})
    expect(payload.delivery_complement).toBe('')
    expect(payload.delivery_instructions).toBe('')
  })

  it('sends the delivery tax id as digits, and only on delivery', () => {
    const delivery = buildCheckoutPayload(deliveryState, 'k', false)
    expect(delivery.fiscal_tax_id).toBe('52998224725')

    const pickup = buildCheckoutPayload({ ...deliveryState, fulfillment_type: 'pickup' }, 'k', false)
    expect(pickup.fiscal_tax_id).toBe('')
  })

  it('has no save-to-profile flag: the tax id only travels with the order', () => {
    const payload = buildCheckoutPayload(deliveryState, 'k', false)
    expect(Object.keys(payload).filter(key => key.startsWith('save_'))).toEqual(['save_as_default'])
  })
})
