// Transforms puros do fluxo de endereço (ADDRESS-UX-PLAN): rascunho canônico,
// máscara/detecção de CEP, parsing de sugestão do Places e do ViaCEP,
// validação de campos, foco guiado e seleção (salvo × novo) para o checkout.

import type { SavedAddressProjection, StructuredAddressProjection } from '~/types/shopman'

// A REGRA do formulário (rascunho, CEP, Google, ViaCEP, validação, ponto no mapa)
// mora em `addressForm.ts`, o módulo gêmeo que o PDV também usa. Aqui ficam só as
// peças da loja: seleção (salvo × novo), etiqueta e reidratação do checkout.
import {
  composedAddressLine,
  draftSummaryLine,
  maskCepInput,
  type AddressDraft
} from './addressForm'

export {
  BR_STATES,
  addressDraftErrors,
  cepDigits,
  composedAddressLine,
  draftFromGooglePlace,
  draftFromViaCep,
  draftSummaryLine,
  emptyAddressDraft,
  looksLikeCep,
  maskCepInput,
  mergeCepLookup,
  mergeReverseGeocode,
  nextFocusAfterSuggestion,
  stillFailingErrors,
  viaCepSummary
} from './addressForm'
export type {
  AddressCoordinatesSource,
  AddressDraft,
  CepFilledFields,
  GoogleAddressComponent,
  GooglePlaceFields,
  ViaCepPayload
} from './addressForm'

export function structuredFromDraft (draft: AddressDraft): StructuredAddressProjection {
  // A linha formatada é recomposta dos campos atuais — o formatted do Google
  // fica obsoleto assim que o cliente edita número/complemento.
  const structured: StructuredAddressProjection = {
    formatted_address: composedAddressLine(draft) || draft.formatted_address,
    route: draft.route.trim(),
    street_number: draft.street_number.trim(),
    neighborhood: draft.neighborhood.trim(),
    city: draft.city.trim(),
    state_code: draft.state_code.trim(),
    postal_code: maskCepInput(draft.postal_code)
  }
  if (draft.latitude != null && draft.longitude != null) {
    structured.latitude = draft.latitude
    structured.longitude = draft.longitude
  }
  if (draft.place_id) structured.place_id = draft.place_id
  if (draft.coordinates_source) structured.coordinates_source = draft.coordinates_source
  return structured
}

export function draftFromSavedAddress (address: SavedAddressProjection): AddressDraft {
  return {
    formatted_address: address.formatted_address || '',
    route: address.route || '',
    street_number: address.street_number || '',
    complement: address.complement || '',
    neighborhood: address.neighborhood || '',
    city: address.city || '',
    state_code: address.state_code || '',
    postal_code: maskCepInput(address.postal_code || ''),
    latitude: address.latitude ?? null,
    longitude: address.longitude ?? null,
    place_id: address.place_id || '',
    coordinates_source: 'saved',
    delivery_instructions: address.delivery_instructions || ''
  }
}

// ── Seleção (checkout) ─────────────────────────────────────────────────

export interface AddressSelection {
  savedAddressId: number | null
  formattedAddress: string
  structured: StructuredAddressProjection
  complement: string
  deliveryInstructions: string
}

export function selectionFromSavedAddress (address: SavedAddressProjection): AddressSelection {
  const draft = draftFromSavedAddress(address)
  return {
    savedAddressId: address.id,
    formattedAddress: address.formatted_address || draftSummaryLine(draft),
    structured: structuredFromDraft(draft),
    complement: address.complement || '',
    deliveryInstructions: address.delivery_instructions || ''
  }
}

export function selectionFromDraft (draft: AddressDraft, savedAddressId: number | null = null): AddressSelection {
  return {
    savedAddressId,
    formattedAddress: composedAddressLine(draft) || draft.formatted_address,
    structured: structuredFromDraft(draft),
    complement: draft.complement.trim(),
    deliveryInstructions: draft.delivery_instructions.trim()
  }
}

// Reidratação do rascunho do checkout: reconstrói o AddressDraft a partir da
// seleção restaurada, para o form do picker reabrir preenchido (endereço NOVO
// digitado antes de sair da página não pode nascer vazio de novo).
export function draftFromSelection (selection: AddressSelection): AddressDraft {
  const structured = selection.structured || {}
  return {
    formatted_address: structured.formatted_address || selection.formattedAddress || '',
    route: structured.route || '',
    street_number: structured.street_number || '',
    complement: selection.complement || '',
    neighborhood: structured.neighborhood || '',
    city: structured.city || '',
    state_code: structured.state_code || '',
    postal_code: maskCepInput(structured.postal_code || ''),
    latitude: structured.latitude ?? null,
    longitude: structured.longitude ?? null,
    place_id: structured.place_id || '',
    coordinates_source: structured.coordinates_source || null,
    delivery_instructions: selection.deliveryInstructions || ''
  }
}

// Seleção vinda do localStorage (rascunho do checkout): dado externo, valida
// forma antes de virar estado. Sem id salvo E sem linha formatada não há
// seleção que valha restaurar.
export function parseStoredAddressSelection (raw: unknown): AddressSelection | null {
  if (!raw || typeof raw !== 'object') return null
  const value = raw as Record<string, unknown>
  const savedAddressId = typeof value.savedAddressId === 'number' ? value.savedAddressId : null
  const formattedAddress = typeof value.formattedAddress === 'string' ? value.formattedAddress : ''
  if (!savedAddressId && !formattedAddress.trim()) return null
  const structured = (value.structured && typeof value.structured === 'object')
    ? value.structured as StructuredAddressProjection
    : {} as StructuredAddressProjection
  return {
    savedAddressId,
    formattedAddress,
    structured,
    complement: typeof value.complement === 'string' ? value.complement : '',
    deliveryInstructions: typeof value.deliveryInstructions === 'string' ? value.deliveryInstructions : ''
  }
}

// Cascata de pré-seleção resolvida pelo servidor (padrão → geo → último →
// mais usado). O cliente só respeita o id; cai para o primeiro salvo se o
// id não estiver mais na lista.
export function resolvePreselectedAddress (
  savedAddresses: SavedAddressProjection[],
  preselectedId: number | null | undefined
): SavedAddressProjection | null {
  if (!savedAddresses.length) return null
  return savedAddresses.find(address => address.id === preselectedId) || savedAddresses[0] || null
}

// ── Etiqueta DEPOIS de salvar ──────────────────────────────────────────


export type AddressLabelKey = 'home' | 'work' | 'other'

export const ADDRESS_LABEL_OPTIONS: Array<{ key: AddressLabelKey, label: string, icon: string }> = [
  { key: 'home', label: 'Casa', icon: 'lucide:house' },
  { key: 'work', label: 'Trabalho', icon: 'lucide:briefcase-business' },
  { key: 'other', label: 'Outro…', icon: 'lucide:tag' }
]

export function labelPatchPayload (key: AddressLabelKey, custom = ''): { label: AddressLabelKey, label_custom: string } {
  return { label: key, label_custom: key === 'other' ? custom.trim() : '' }
}

// Nome legível da etiqueta escolhida — usado na confirmação de transparência
// ("Endereço salvo como Casa") depois que o pedido fecha.
export function addressLabelDisplay (key: AddressLabelKey, custom = ''): string {
  if (key === 'other') return custom.trim() || 'Outro'
  return key === 'work' ? 'Trabalho' : 'Casa'
}

export function savedAddressDisplayLabel (address: Pick<SavedAddressProjection, 'label' | 'label_key' | 'label_custom'>): string {
  if (address.label_key === 'other' && address.label_custom) return address.label_custom
  return address.label || 'Endereço'
}

// A frase da busca por CEP sem resultado (beta SMS-01). "Não achamos" só quando o
// serviço disse que o CEP não existe; quando a consulta nem aconteceu, a falha é
// da loja e a frase não manda conferir números que estão certos.
export function cepSearchIssue (unavailable: boolean): string {
  return unavailable
    ? 'Não conseguimos consultar o CEP agora. Toque em "Preencher manualmente" e escreva o endereço.'
    : 'Não achamos esse CEP. Confira os números ou toque em "Preencher manualmente" e escreva o endereço.'
}

// O formulário do picker aberto com algo que o checkout ainda não recebeu (beta
// SMS-15). Enquanto isso, o "Continuar" do card não pode seguir com o endereço
// ANTIGO: a edição sumia sem aviso. Editar um salvo conta como pendente até
// salvar ou fechar; endereço novo, quando difere da seleção em vigor.
export interface PickerDraftPendingInput {
  context: 'checkout' | 'account'
  mode: 'saved' | 'search' | 'form'
  editingSaved: boolean
  draft: AddressDraft
  selection: AddressSelection | null | undefined
}

export function pickerDraftPending ({ context, mode, editingSaved, draft, selection }: PickerDraftPendingInput): boolean {
  if (context !== 'checkout' || mode !== 'form') return false
  if (editingSaved) return true
  if (!selection) return false
  const next = selectionFromDraft(draft, selection.savedAddressId)
  return next.formattedAddress !== selection.formattedAddress ||
    next.complement !== selection.complement ||
    next.deliveryInstructions !== selection.deliveryInstructions
}
