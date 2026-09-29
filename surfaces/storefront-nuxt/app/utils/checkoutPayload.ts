import { newRemoteMutationKey } from './remoteMutations'
import { taxIdDigits } from '~/presentation/taxId'
import type { StructuredAddressProjection } from '~/types/shopman'

export type FulfillmentType = 'pickup' | 'delivery'

export interface CheckoutFormState {
  name: string
  phone: string
  fulfillment_type: FulfillmentType
  saved_address_id: number | null
  delivery_address: string
  delivery_address_structured: StructuredAddressProjection
  delivery_complement: string
  delivery_instructions: string
  delivery_date: string
  delivery_time_slot: string
  payment_method: string
  change_for: string
  notes: string
  is_gift: boolean
  recipient_name: string
  recipient_phone: string
  gift_message: string
  gift_hide_values: boolean
  // "Lembrar destas escolhas": pré-marcado (opt-out). O endereço novo entra na
  // agenda do cliente sempre; este toggle controla só os padrões (qual endereço
  // vem escolhido, forma de pagamento, horário).
  save_as_default: boolean
  // CPF/CNPJ na nota (vira `fiscal.tax_id` no pedido). Na entrega é
  // obrigatório; na retirada é o "CPF na nota?" do balcão, e só vai se a pessoa
  // ligou `fiscal_tax_id_on_pickup`. Nunca vai para o rascunho do localStorage:
  // documento não fica guardado no aparelho.
  fiscal_tax_id: string
  fiscal_tax_id_on_pickup: boolean
  // A pessoa respondeu SIM a "guardar no seu cadastro?" (só perguntado quando
  // o cadastro dela ainda não tem documento). Desmarcado por padrão.
  save_fiscal_tax_id: boolean
}

export interface CheckoutSubmitPayload extends Omit<CheckoutFormState, 'fiscal_tax_id_on_pickup'> {
  idempotency_key: string
  use_loyalty: boolean
  // Total (centavos) exibido ao cliente no momento do confirmar — o servidor
  // rejeita o commit se a repricing final divergir (cobrança surpresa, nunca).
  expected_revision?: number
  expected_total_q: number | null
}

export function createCheckoutAttemptKey (): string {
  return newRemoteMutationKey('checkout')
}

/** O documento que vai na nota: o da entrega, ou o da retirada que a pessoa pediu. */
export function noteTaxId (state: Pick<CheckoutFormState, 'fulfillment_type' | 'fiscal_tax_id' | 'fiscal_tax_id_on_pickup'>): string {
  if (state.fulfillment_type === 'delivery') return taxIdDigits(state.fiscal_tax_id)
  return state.fiscal_tax_id_on_pickup ? taxIdDigits(state.fiscal_tax_id) : ''
}

export function buildCheckoutPayload (
  state: CheckoutFormState,
  idempotencyKey: string,
  useLoyalty: boolean,
  expectedTotalQ: number | null = null,
  expectedRevision?: number
): CheckoutSubmitPayload {
  return {
    ...(expectedRevision !== undefined ? { expected_revision: expectedRevision } : {}),
    idempotency_key: idempotencyKey,
    name: state.name.trim(),
    phone: state.phone.trim(),
    fulfillment_type: state.fulfillment_type,
    saved_address_id: state.fulfillment_type === 'delivery' ? state.saved_address_id : null,
    delivery_address: state.fulfillment_type === 'delivery' ? state.delivery_address.trim() : '',
    delivery_address_structured: state.fulfillment_type === 'delivery' ? state.delivery_address_structured : {},
    delivery_complement: state.fulfillment_type === 'delivery' ? state.delivery_complement.trim() : '',
    delivery_instructions: state.fulfillment_type === 'delivery' ? state.delivery_instructions.trim() : '',
    delivery_date: state.delivery_date,
    delivery_time_slot: state.delivery_time_slot,
    payment_method: state.payment_method,
    // Troco só faz sentido em dinheiro + entrega; caso contrário vai vazio.
    change_for: (state.payment_method === 'cash' && state.fulfillment_type === 'delivery')
      ? state.change_for.trim()
      : '',
    notes: state.notes.trim(),
    is_gift: state.is_gift,
    recipient_name: state.is_gift ? state.recipient_name.trim() : '',
    recipient_phone: state.is_gift ? state.recipient_phone.trim() : '',
    gift_message: state.is_gift ? state.gift_message.trim() : '',
    gift_hide_values: state.is_gift ? state.gift_hide_values : false,
    save_as_default: state.save_as_default,
    // Só dígitos viajam; na retirada, só se a pessoa pediu CPF na nota.
    fiscal_tax_id: noteTaxId(state),
    save_fiscal_tax_id: !!noteTaxId(state) && state.save_fiscal_tax_id,
    use_loyalty: useLoyalty,
    expected_total_q: expectedTotalQ
  }
}
