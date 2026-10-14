// O FORMULÁRIO DE ENDEREÇO DE ENTREGA da casa: as regras que a loja online
// (storefront-nuxt, AddressPicker) e o PDV (pos-nuxt, PosFulfillmentModal) seguem
// juntos. Decisão do dono (13/10/2026): o endereço que o balcão digita passa pelos
// mesmos passos e pelas mesmas regras do site: CEP ou busca, sugestão, ponto no
// mapa, campos, validação.
//
// ⚠️ ARQUIVO GÊMEO. Existe byte a byte igual em
//   surfaces/storefront-nuxt/app/presentation/addressForm.ts
//   surfaces/pos-nuxt/app/presentation/addressForm.ts
// e os testes `addressFormTwin` dos dois apps reprovam a menor diferença. Cada app
// builda sozinho (o storefront no App Platform só enxerga a própria pasta), então o
// módulo não pode morar fora deles; e o storefront não estende o operator-kit.
// Mude os dois no mesmo commit.
//
// Puro: sem `~/`, sem Vue, sem fetch. A voz de cada superfície fica fora daqui; o
// que está aqui é a regra (o que conta como CEP, o que vem do Google e do ViaCEP, o
// que falta para o endereço estar completo, o que o ponto do mapa sobrescreve).

export type AddressCoordinatesSource = 'pin' | 'geocoded' | 'saved'

export interface AddressDraft {
  formatted_address: string
  route: string
  street_number: string
  complement: string
  neighborhood: string
  city: string
  state_code: string
  postal_code: string
  latitude: number | null
  longitude: number | null
  place_id: string
  coordinates_source: AddressCoordinatesSource | null
  delivery_instructions: string
}

/** O que o servidor devolve ao descrever um ponto (reverse geocode). */
export interface AddressDescription {
  formatted_address?: string
  route?: string
  street_number?: string
  neighborhood?: string
  city?: string
  state_code?: string
  postal_code?: string
  latitude?: number | null
  longitude?: number | null
  place_id?: string | null
}

export function emptyAddressDraft (): AddressDraft {
  return {
    formatted_address: '',
    route: '',
    street_number: '',
    complement: '',
    neighborhood: '',
    city: '',
    state_code: '',
    postal_code: '',
    latitude: null,
    longitude: null,
    place_id: '',
    coordinates_source: null,
    delivery_instructions: ''
  }
}

// ── CEP ────────────────────────────────────────────────────────────────

export function cepDigits (value: string): string {
  return (value || '').replace(/\D/g, '').slice(0, 8)
}

export function maskCepInput (value: string): string {
  const digits = cepDigits(value)
  if (digits.length <= 5) return digits
  return `${digits.slice(0, 5)}-${digits.slice(5)}`
}

// 8 dígitos numéricos (com ou sem hífen/ponto/espaço) parecem CEP: gatilho do
// ViaCEP quando o Places não responde bem.
export function looksLikeCep (query: string): boolean {
  const compact = (query || '').replace(/[\s.-]/g, '')
  return /^\d{8}$/.test(compact)
}

export interface ViaCepPayload {
  erro?: boolean | string
  logradouro?: string
  bairro?: string
  localidade?: string
  uf?: string
  cep?: string
}

export function draftFromViaCep (payload: ViaCepPayload | null | undefined, queriedCep: string): Partial<AddressDraft> | null {
  if (!payload || payload.erro) return null
  const postal = maskCepInput(payload.cep || queriedCep)
  const route = (payload.logradouro || '').trim()
  const neighborhood = (payload.bairro || '').trim()
  const city = (payload.localidade || '').trim()
  const stateCode = (payload.uf || '').trim().toUpperCase()
  if (!city || !stateCode) return null
  return {
    route,
    neighborhood,
    city,
    state_code: stateCode,
    postal_code: postal,
    formatted_address: viaCepSummary(payload)
  }
}

export function viaCepSummary (payload: ViaCepPayload): string {
  const cityState = [payload.localidade, (payload.uf || '').toUpperCase()].filter(Boolean).join('/')
  return [payload.logradouro, payload.bairro, cityState].map(part => (part || '').trim()).filter(Boolean).join(', ')
}

// ── Google Places ──────────────────────────────────────────────────────

export interface GoogleAddressComponent {
  longText?: string | null
  shortText?: string | null
  types?: string[]
}

export interface GooglePlaceFields {
  id?: string | null
  formattedAddress?: string | null
  addressComponents?: GoogleAddressComponent[] | null
  latitude?: number | null
  longitude?: number | null
}

export function googleComponentText (components: GoogleAddressComponent[], types: string[], short = false): string {
  const wanted = new Set(types)
  for (const component of components) {
    if ((component.types || []).some(type => wanted.has(type))) {
      const text = short ? component.shortText : component.longText
      if (text) return String(text).trim()
    }
  }
  return ''
}

// Consultas de CEP devolvem faixa ("1-494") como street_number: não é um número
// de porta; melhor deixar vazio e o foco guiado pedir o número.
function cleanStreetNumber (value: string): string {
  return /^\d+\s*-\s*\d+$/.test(value.trim()) ? '' : value
}

export function draftFromGooglePlace (place: GooglePlaceFields): Partial<AddressDraft> {
  const components = place.addressComponents || []
  return {
    formatted_address: place.formattedAddress || '',
    route: googleComponentText(components, ['route']),
    street_number: cleanStreetNumber(googleComponentText(components, ['street_number'])),
    neighborhood: googleComponentText(components, ['sublocality_level_1', 'sublocality', 'neighborhood']),
    city: googleComponentText(components, ['administrative_area_level_2', 'locality']),
    state_code: googleComponentText(components, ['administrative_area_level_1'], true),
    postal_code: maskCepInput(googleComponentText(components, ['postal_code'])),
    latitude: place.latitude ?? null,
    longitude: place.longitude ?? null,
    place_id: place.id || '',
    coordinates_source: place.latitude != null && place.longitude != null ? 'geocoded' : null
  }
}

// Reverse geocode do servidor (POST /api/v1/geocode/reverse) já devolve as
// chaves canônicas. O pin manda em tudo que é do lugar; número só se o reverse
// trouxe um (pin no meio do quarteirão não apaga o número digitado).
// Complemento e instruções são de quem informou o endereço: nunca sobrescrever.
export function mergeReverseGeocode (draft: AddressDraft, result: AddressDescription): AddressDraft {
  return {
    ...draft,
    formatted_address: result.formatted_address || draft.formatted_address,
    route: result.route || draft.route,
    street_number: result.street_number || draft.street_number,
    neighborhood: result.neighborhood || draft.neighborhood,
    city: result.city || draft.city,
    state_code: result.state_code || draft.state_code,
    postal_code: maskCepInput(result.postal_code || draft.postal_code),
    latitude: result.latitude ?? draft.latitude,
    longitude: result.longitude ?? draft.longitude,
    place_id: result.place_id || draft.place_id
  }
}

// ── Fluxo guiado e validação ───────────────────────────────────────────

// Sugestão aceita: foco pula para o número; se a sugestão já trouxe o número,
// pula direto para o complemento.
export function nextFocusAfterSuggestion (draft: Pick<AddressDraft, 'street_number'>): 'street_number' | 'complement' {
  return draft.street_number.trim() ? 'complement' : 'street_number'
}

export type AddressRequiredField = 'route' | 'street_number' | 'neighborhood' | 'city' | 'state_code' | 'postal_code'

// Endereço completo é o que a entrega e a nota de entrega pedem: rua, número
// (ou "s/n"), bairro, cidade, UF e CEP de 8 dígitos. Complemento e instruções
// são opcionais.
export function addressDraftErrors (draft: AddressDraft): Record<string, string> {
  const errors: { [field in AddressRequiredField]?: string } = {}
  if (!draft.route.trim()) errors.route = 'Informe a rua.'
  if (!draft.street_number.trim()) errors.street_number = 'Informe o número (ou "s/n").'
  if (!draft.neighborhood.trim()) errors.neighborhood = 'Informe o bairro.'
  if (!draft.city.trim()) errors.city = 'Informe a cidade.'
  if (!draft.state_code.trim()) errors.state_code = 'UF.'
  if (cepDigits(draft.postal_code).length !== 8) errors.postal_code = 'CEP com 8 dígitos.'
  return errors as Record<string, string>
}

export function composedAddressLine (draft: AddressDraft): string {
  const street = [draft.route.trim(), draft.street_number.trim()].filter(Boolean).join(', ')
  const cityState = [draft.city.trim(), draft.state_code.trim()].filter(Boolean).join('/')
  return [street, draft.neighborhood.trim(), cityState].filter(Boolean).join(' - ')
}

// Linha exibida para a sugestão aceita / ponto confirmado.
export function draftSummaryLine (draft: AddressDraft): string {
  return composedAddressLine(draft) || draft.formatted_address
}

// UFs brasileiras para o seletor de estado (mais seguro e rápido que texto livre).
export const BR_STATES: readonly string[] = [
  'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', 'MG',
  'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'
]

// ── Ponto no mapa ──────────────────────────────────────────────────────

export interface AddressPoint {
  lat: number
  lng: number
}

export function distanceMetres (first: AddressPoint, second: AddressPoint): number {
  const radians = (degrees: number) => degrees * Math.PI / 180
  const latitudeDelta = radians(second.lat - first.lat)
  const longitudeDelta = radians(second.lng - first.lng)
  const firstLatitude = radians(first.lat)
  const secondLatitude = radians(second.lat)
  const haversine = Math.sin(latitudeDelta / 2) ** 2
    + Math.cos(firstLatitude) * Math.cos(secondLatitude) * Math.sin(longitudeDelta / 2) ** 2
  return 2 * 6371000 * Math.asin(Math.sqrt(haversine))
}

export function pointMoved (initial: AddressPoint, current: AddressPoint, thresholdM = 2): boolean {
  return distanceMetres(initial, current) > thresholdM
}

/**
 * O reverse geocode DESCREVE o ponto; nunca substitui o ponto que foi confirmado
 * no mapa. Os campos de quem informou o endereço sobrevivem como no resto do
 * fluxo.
 */
export function mergeConfirmedPoint (
  draft: AddressDraft,
  reverse: AddressDescription | null,
  point: AddressPoint,
  source: AddressCoordinatesSource = 'pin'
): AddressDraft {
  const described = reverse ? mergeReverseGeocode(draft, reverse) : { ...draft }
  return {
    ...described,
    latitude: point.lat,
    longitude: point.lng,
    coordinates_source: source
  }
}
