// Rascunho do checkout (localStorage): sair do navegador — ou ir ao cardápio
// adicionar itens — e voltar NÃO pode perder o que já foi preenchido. Aqui vive
// o parse puro do rascunho: validade (TTL), forma dos campos e a seleção de
// endereço serializada (que reidrata o AddressPicker). A página só aplica.
import { parseStoredAddressSelection, type AddressLabelKey, type AddressSelection } from '~/presentation/address'
import { checkoutSteps, type CheckoutStep } from '~/utils/checkoutFlow'
import type { CheckoutFormState } from '~/utils/checkoutPayload'

export const CHECKOUT_DRAFT_KEY = 'shopman-checkout-draft'
export const CHECKOUT_DRAFT_TTL = 6 * 60 * 60 * 1000

const ADDRESS_LABEL_KEYS: readonly AddressLabelKey[] = ['home', 'work', 'other']

export interface RestoredCheckoutDraft {
  attemptKey: string | null
  state: Partial<CheckoutFormState>
  activeStep: CheckoutStep | null
  pendingAddressLabel: { key: AddressLabelKey, custom: string } | null
  addressSelection: AddressSelection | null
  // Observação restaurada reabre o toggle: texto restaurado com o toggle
  // fechado seria dado invisível viajando no payload.
  notesOpen: boolean
}

export interface ParsedCheckoutDraft {
  draft: RestoredCheckoutDraft | null
  // Rascunho existia mas venceu o TTL — a página deve apagá-lo.
  stale: boolean
}

function parsePendingLabel (raw: unknown): { key: AddressLabelKey, custom: string } | null {
  if (!raw || typeof raw !== 'object') return null
  const value = raw as Record<string, unknown>
  const key = value.key
  if (typeof key !== 'string' || !ADDRESS_LABEL_KEYS.includes(key as AddressLabelKey)) return null
  return { key: key as AddressLabelKey, custom: typeof value.custom === 'string' ? value.custom : '' }
}

export function parseCheckoutDraft (raw: string | null | undefined, nowMs = Date.now(), context = ''): ParsedCheckoutDraft {
  if (!raw) return { draft: null, stale: false }
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return { draft: null, stale: false }
  }
  if (!parsed || typeof parsed !== 'object') return { draft: null, stale: false }
  const value = parsed as Record<string, unknown>
  if (!context || value.version !== 2 || value.context !== context) return { draft: null, stale: true }
  const fresh = typeof value.savedAt === 'number' && Number.isFinite(value.savedAt) && nowMs >= value.savedAt && (nowMs - value.savedAt) < CHECKOUT_DRAFT_TTL
  if (!fresh) return { draft: null, stale: true }
  const rawState = (value.state && typeof value.state === 'object')
    ? value.state as Partial<CheckoutFormState>
    : null
  if (!rawState || Array.isArray(rawState)) return { draft: null, stale: true }
  const state: Partial<CheckoutFormState> = {}
  const textFields = ['name', 'phone', 'delivery_address', 'delivery_complement', 'delivery_instructions', 'delivery_date', 'delivery_time_slot', 'payment_method', 'change_for', 'notes', 'recipient_name', 'recipient_phone', 'gift_message'] as const
  for (const key of textFields) {
    const v = rawState[key]
    if (v !== undefined && (typeof v !== 'string' || v.length > 2000)) return { draft: null, stale: true }
    if (typeof v === 'string') state[key] = v
  }
  for (const key of ['is_gift', 'gift_hide_values', 'save_as_default'] as const) {
    const v = rawState[key]
    if (v !== undefined && typeof v !== 'boolean') return { draft: null, stale: true }
    if (typeof v === 'boolean') state[key] = v
  }
  if (rawState.fulfillment_type !== undefined) {
    if (!['pickup', 'delivery'].includes(rawState.fulfillment_type)) return { draft: null, stale: true }
    state.fulfillment_type = rawState.fulfillment_type
  }
  const addressId = rawState.saved_address_id
  if (addressId !== undefined && addressId !== null && (!Number.isInteger(addressId) || addressId <= 0)) return { draft: null, stale: true }
  if (addressId !== undefined) state.saved_address_id = addressId
  const structured = rawState.delivery_address_structured
  if (structured && typeof structured === 'object' && !Array.isArray(structured)) {
    state.delivery_address_structured = {}
    for (const [key, v] of Object.entries(structured)) {
      if (['latitude', 'longitude'].includes(key)) {
        if (typeof v !== 'number' || !Number.isFinite(v)) return { draft: null, stale: true }
      } else if (typeof v !== 'string' || v.length > 2000) return { draft: null, stale: true }
      Object.assign(state.delivery_address_structured, { [key]: v })
    }
  }
  const steps = checkoutSteps(state.fulfillment_type === 'delivery' ? 'delivery' : 'pickup')
  const activeStep = steps.includes(value.activeStep as CheckoutStep)
    ? value.activeStep as CheckoutStep
    : null
  return {
    draft: {
      attemptKey: typeof value.attemptKey === 'string' && value.attemptKey.length <= 128 ? value.attemptKey : null,
      state,
      activeStep,
      pendingAddressLabel: parsePendingLabel(value.pendingAddressLabel),
      addressSelection: parseStoredAddressSelection(value.addressSelection),
      notesOpen: typeof state.notes === 'string' && !!state.notes.trim()
    },
    stale: false
  }
}
