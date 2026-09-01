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

export function parseCheckoutDraft (raw: string | null | undefined, nowMs = Date.now()): ParsedCheckoutDraft {
  if (!raw) return { draft: null, stale: false }
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return { draft: null, stale: false }
  }
  if (!parsed || typeof parsed !== 'object') return { draft: null, stale: false }
  const value = parsed as Record<string, unknown>
  const fresh = typeof value.savedAt === 'number' && (nowMs - value.savedAt) < CHECKOUT_DRAFT_TTL
  if (!fresh) return { draft: null, stale: true }
  const state = (value.state && typeof value.state === 'object')
    ? value.state as Partial<CheckoutFormState>
    : null
  if (!state) return { draft: null, stale: false }
  const steps = checkoutSteps(state.fulfillment_type === 'delivery' ? 'delivery' : 'pickup')
  const activeStep = steps.includes(value.activeStep as CheckoutStep)
    ? value.activeStep as CheckoutStep
    : null
  return {
    draft: {
      state,
      activeStep,
      pendingAddressLabel: parsePendingLabel(value.pendingAddressLabel),
      addressSelection: parseStoredAddressSelection(value.addressSelection),
      notesOpen: typeof state.notes === 'string' && !!state.notes.trim()
    },
    stale: false
  }
}
