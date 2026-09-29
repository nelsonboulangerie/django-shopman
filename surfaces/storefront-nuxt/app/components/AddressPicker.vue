<script setup lang="ts">
// Componente único de endereço (ADDRESS-UX-PLAN) — usado pelo checkout e pela
// conta. Busca unificada (Places + fallback silencioso ViaCEP), "usar minha
// localização" com confirmação visual protegida por flag, ajuste fino no mapa
// e etiqueta perguntada DEPOIS de salvar. Lógica pura em presentation/address.
import {
  ADDRESS_LABEL_OPTIONS,
  BR_STATES,
  addressDraftErrors,
  composedAddressLine,
  draftFromGooglePlace,
  draftFromSavedAddress,
  draftFromSelection,
  draftFromViaCep,
  draftSummaryLine,
  emptyAddressDraft,
  labelPatchPayload,
  looksLikeCep,
  maskCepInput,
  mergeReverseGeocode,
  nextFocusAfterSuggestion,
  resolvePreselectedAddress,
  savedAddressDisplayLabel,
  selectionFromDraft,
  selectionFromSavedAddress,
  type AddressDraft,
  type AddressLabelKey,
  type AddressSelection,
  type ViaCepPayload
} from '~/presentation/address'
import {
  accuracyBucket,
  accuracyMessage,
  distanceMetres,
  mergeConfirmedPoint,
  pointMoved,
  type AddressPoint
} from '~/presentation/addressMap'
import type {
  AddressLocationDivergenceConfig,
  CurrentLocationFix
} from '~/presentation/addressLocationConsistency'
import type { AddressLocationCheckTarget } from '~/composables/useAddressLocationCheck'
import type { SavedAddressProjection, StructuredAddressProjection } from '~/types/shopman'

interface PickerSuggestion {
  id: string
  kind: 'place' | 'cep'
  main: string
  secondary: string
  prediction?: google.maps.places.PlacePrediction
  cepPartial?: Partial<AddressDraft>
}

// Refs de UiInput/UiInputGroupInput: componente com o elemento nativo em
// `inputRef` (exposed) ou no `$el` da raiz.
type FocusableInput = { inputRef?: { value?: HTMLInputElement | null }, $el?: HTMLElement } | null

const props = withDefaults(defineProps<{
  context: 'checkout' | 'account'
  savedAddresses?: SavedAddressProjection[]
  preselectedId?: number | null
  editingAddress?: SavedAddressProjection | null
  initialIsDefault?: boolean
  // Seleção já feita (v-model, checkout): no REMOUNT (voltar do cardápio com o
  // rascunho restaurado, alternar entrega↔retirada) o picker nasce dela em vez
  // de re-selecionar o preselected — endereço salvo re-marca o rádio, endereço
  // novo reabre o form preenchido. Sem isso, o watcher immediate atropelava o
  // que o cliente já tinha escolhido/digitado.
  selection?: AddressSelection | null
}>(), {
  savedAddresses: () => [],
  preselectedId: null,
  editingAddress: null,
  initialIsDefault: false,
  selection: null
})

const emit = defineEmits<{
  'update:selection': [selection: AddressSelection | null]
  // Checkout: endereço pronto (salvo + etiqueta respondida) — pode avançar.
  confirmed: []
  // Conta: criação/edição concluída — o pai fecha o sheet e atualiza a lista.
  done: []
  // Checkout: um endereço salvo foi editado in-loco — o pai re-busca a lista.
  'addresses-changed': []
}>()

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const maps = useGoogleMaps()
const session = useShopSession()
const telemetry = useStorefrontTelemetry()

type PickerMode = 'saved' | 'search' | 'form'

const isEditing = computed(() => !!props.editingAddress)
// Edição in-loco de um salvo no checkout (corrigir número/complemento sem sair).
const editingSavedId = ref<number | null>(null)
const isEditingForm = computed(() => isEditing.value || editingSavedId.value != null)
const mode = ref<PickerMode>(initialMode())
const draft = reactive<AddressDraft>(initialDraft())
const fieldErrors = ref<Record<string, string>>({})
const acceptedLine = ref(initialAcceptedLine())
// Nasce da seleção reidratada (rascunho): com o id já marcado, o watcher de
// preseleção abaixo respeita a escolha restaurada em vez de re-selecionar.
const selectedSavedId = ref<number | null>(props.context === 'checkout' ? (props.selection?.savedAddressId ?? null) : null)

const query = ref('')
const searching = ref(false)
const suggestions = ref<PickerSuggestion[]>([])
const searchOpen = ref(false)
// A busca que não acha nada precisa DIZER. Sem isto, a lista fecha, a tela fica
// idêntica, e quem digitou o CEP conclui que a loja não atende o endereço dele —
// que é a conclusão mais cara possível. Vive aqui, e não em `saveIssue`, porque
// `saveIssue` só é renderizado no modo `form`.
const searchIssue = ref('')

const locating = ref(false)
const geoIssue = ref('')
const geoCandidate = ref<AddressDraft | null>(null)

const saving = ref(false)
const saveIssue = ref('')
const pendingCreatedId = ref<number | null>(null)
const labelOpen = ref(false)

const accountLabel = ref<AddressLabelKey>((props.editingAddress?.label_key as AddressLabelKey) || 'home')
const accountLabelCustom = ref(props.editingAddress?.label_custom || '')
const isDefault = ref(props.editingAddress ? !!props.editingAddress.is_default : props.initialIsDefault)

const mapOpen = ref(false)
const mapLoading = ref(false)
const mapIssue = ref('')
const mapEl = ref<HTMLElement | null>(null)
let mapInstance: google.maps.Map | null = null
let mapAccuracyCircle: google.maps.Circle | null = null
let mapComparisonMarker: google.maps.Marker | null = null
let mapSession = 0
let mapPendingReverse: Promise<StructuredAddressProjection | null> | null = null
type MapOrigin = 'place' | 'gps' | 'adjust'
const mapOrigin = ref<MapOrigin>('adjust')
const mapReturnMode = ref<PickerMode>('form')
const mapInitialPoint = ref<AddressPoint | null>(null)
const mapAccuracyM = ref<number | null>(null)
const mapMoved = ref(false)
const mapComparisonFix = ref<CurrentLocationFix | null>(null)
const mapRecoveryPath = ref<'use_current' | 'review_map' | null>(null)
const mapDraftSnapshot = ref<{ draft: AddressDraft, acceptedLine: string } | null>(null)
const mapApplied = ref(false)
const draftOriginatedFromCurrentLocation = ref(false)

const routeInput = ref<FocusableInput>(null)
const numberInput = ref<FocusableInput>(null)
const complementInput = ref<FocusableInput>(null)
const neighborhoodInput = ref<FocusableInput>(null)
const cepInput = ref<FocusableInput>(null)
const cityInput = ref<FocusableInput>(null)
const searchInput = ref<FocusableInput>(null)

let searchTimer: ReturnType<typeof setTimeout> | null = null
let searchSeq = 0
let placesSessionToken: google.maps.places.AutocompleteSessionToken | null = null

const labelOptions = ADDRESS_LABEL_OPTIONS
const brStates = BR_STATES
const hasSaved = computed(() => props.context === 'checkout' && props.savedAddresses.length > 0)
// Card branco só quando o picker vai DIRETO no fundo cinza (checkout, inline).
// Na conta ele abre dentro de um sheet (já é superfície branca) → sem card,
// pra não virar card-dentro-de-card. Os campos são brancos (bg-white do UiInput) + borda.
const surfaceChrome = computed(() => (props.context === 'checkout' ? 'rounded-lg border bg-card p-4' : ''))
const canAdjustOnMap = computed(() => maps.enabled.value && draft.latitude != null && draft.longitude != null)
const mapConfirmationEnabled = computed(() => (
  props.context === 'checkout'
  && !!maps.enabled.value
  && !!session.publicConfig.value?.address_map_confirmation_enabled
))
const draftLine = computed(() => draftSummaryLine(draft as AddressDraft))
const mapAccuracyText = computed(() => accuracyMessage(mapAccuracyM.value))
const mapAccuracyKind = computed(() => accuracyBucket(mapAccuracyM.value))
const locationConfig = computed<AddressLocationDivergenceConfig>(() => {
  if (props.context !== 'checkout') return offLocationConfig()
  return session.publicConfig.value?.address_location_divergence || offLocationConfig()
})
const locationCheckTarget = computed<AddressLocationCheckTarget | null>(() => {
  if (props.context !== 'checkout' || draftOriginatedFromCurrentLocation.value) return null
  if (mode.value === 'saved') {
    const address = props.savedAddresses.find(candidate => candidate.id === selectedSavedId.value)
    if (!address) return null
    const point = validAddressPoint(address.latitude, address.longitude)
    return { kind: 'saved', point, source: 'saved' }
  }
  if (mode.value !== 'form' || !acceptedLine.value) return null
  return {
    kind: editingSavedId.value ? 'saved' : 'search',
    point: validAddressPoint(draft.latitude, draft.longitude),
    source: draft.coordinates_source
  }
})
const {
  state: locationCheckState,
  statusMessage: locationCheckStatus,
  currentFix: locationCheckFix,
  request: requestLocationCheck,
  reset: resetLocationCheck,
  keep: keepCheckedAddress,
  recordAction: recordLocationCheckAction
} = useAddressLocationCheck({ config: locationConfig, target: locationCheckTarget })

// Alterar a identidade postal invalida a conferência anterior mesmo quando o
// pin ainda não mudou. Complemento e instruções não mudam o ponto da entrega.
watch(
  () => [draft.route, draft.street_number, draft.postal_code] as const,
  () => resetLocationCheck()
)

function offLocationConfig (): AddressLocationDivergenceConfig {
  return {
    mode: 'off',
    threshold_m: 500,
    max_accuracy_m: 250,
    maximum_age_ms: 30_000,
    policy_version: 'v1'
  }
}

function validAddressPoint (latitude: number | null | undefined, longitude: number | null | undefined): AddressPoint | null {
  if (typeof latitude !== 'number' || typeof longitude !== 'number') return null
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null
  if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) return null
  return { lat: latitude, lng: longitude }
}

// Seleção reidratada de endereço NOVO (sem id salvo): o form reabre preenchido.
function rehydratedNewSelection (): AddressSelection | null {
  if (props.context !== 'checkout' || !props.selection || props.selection.savedAddressId) return null
  return props.selection
}

function initialMode (): PickerMode {
  if (props.editingAddress) return 'form'
  if (rehydratedNewSelection()) return 'form'
  if (props.context === 'checkout' && props.savedAddresses.length) return 'saved'
  return 'search'
}

function initialDraft (): AddressDraft {
  if (props.editingAddress) return draftFromSavedAddress(props.editingAddress)
  const restored = rehydratedNewSelection()
  if (restored) return draftFromSelection(restored)
  return emptyAddressDraft()
}

function initialAcceptedLine (): string {
  if (props.editingAddress) return props.editingAddress.formatted_address || ''
  return rehydratedNewSelection()?.formattedAddress || ''
}

// ── Salvos (checkout) ──────────────────────────────────────────────────

function pickSaved (id: number) {
  const address = props.savedAddresses.find(candidate => candidate.id === id)
  draftOriginatedFromCurrentLocation.value = false
  selectedSavedId.value = id
  emit('update:selection', address ? selectionFromSavedAddress(address) : null)
}

watch(() => [props.savedAddresses, props.preselectedId] as const, () => {
  if (props.context !== 'checkout' || mode.value !== 'saved') return
  if (selectedSavedId.value && props.savedAddresses.some(address => address.id === selectedSavedId.value)) return
  const preselected = resolvePreselectedAddress(props.savedAddresses, props.preselectedId)
  if (preselected) pickSaved(preselected.id)
}, { immediate: true, deep: true })

function startNewAddress () {
  selectedSavedId.value = null
  emit('update:selection', null)
  resetDraft()
  mode.value = 'search'
  void focusSearch()
}

function backToSaved () {
  mode.value = 'saved'
  const preselected = resolvePreselectedAddress(props.savedAddresses, selectedSavedId.value ?? props.preselectedId)
  if (preselected) pickSaved(preselected.id)
}

// Editar um endereço salvo sem sair do checkout (corrigir número/complemento).
function startEditSaved (address: SavedAddressProjection) {
  editingSavedId.value = address.id
  Object.assign(draft, draftFromSavedAddress(address))
  accountLabel.value = (address.label_key as AddressLabelKey) || 'home'
  accountLabelCustom.value = address.label_custom || ''
  isDefault.value = !!address.is_default
  acceptedLine.value = address.formatted_address || ''
  fieldErrors.value = {}
  saveIssue.value = ''
  mode.value = 'form'
}

function cancelEdit () {
  editingSavedId.value = null
  backToSaved()
}

// X de dismiss do form: conta fecha o sheet; edição de salvo cancela; novo
// endereço do checkout volta aos salvos (ou à busca, se não houver salvos).
function dismissForm () {
  if (props.context === 'account') { emit('done'); return }
  if (editingSavedId.value) { cancelEdit(); return }
  if (hasSaved.value) backToSaved()
  else backToSearch()
}

function resetDraft () {
  Object.assign(draft, emptyAddressDraft())
  fieldErrors.value = {}
  acceptedLine.value = ''
  saveIssue.value = ''
  searchIssue.value = ''
  geoCandidate.value = null
  geoIssue.value = ''
  draftOriginatedFromCurrentLocation.value = false
  query.value = ''
  suggestions.value = []
}

// ── Busca unificada ────────────────────────────────────────────────────

// Refs de UiInput/UiInputGroupInput apontam para o componente; o elemento
// nativo é o próprio $el (root do UiInput) ou o exposed inputRef.
function focusUiInput (target: FocusableInput) {
  const el = target?.$el
  const native = target?.inputRef?.value
    || (el?.tagName === 'INPUT' ? (el as HTMLInputElement) : el?.querySelector?.('input'))
  native?.focus?.({ preventScroll: true })
}

function focusNextInput (target: FocusableInput) {
  focusUiInput(target)
}

function finishTextEntry (event: KeyboardEvent) {
  (event.currentTarget as HTMLInputElement | null)?.blur?.()
}

async function focusSearch () {
  await nextTick()
  focusUiInput(searchInput.value)
}

function onQueryInput (event: Event) {
  const input = event.target as HTMLInputElement | null
  if (input) query.value = input.value
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { void runSearch(query.value) }, 300)
}

async function runSearch (value: string) {
  const seq = ++searchSeq
  const trimmed = value.trim()
  const isCep = looksLikeCep(trimmed)
  if (trimmed.length < 3) {
    suggestions.value = []
    searchOpen.value = false
    searchIssue.value = ''
    return
  }
  searching.value = true
  searchIssue.value = ''
  let results: PickerSuggestion[] = []
  try {
    if (maps.enabled.value && !isCep) results = await placesSuggestions(trimmed)
    if (maps.enabled.value && isCep && !results.length) results = await placesSuggestions(trimmed)
    if (isCep && !results.length) {
      const cepSuggestion = await viaCepSuggestion(trimmed)
      if (cepSuggestion) results = [cepSuggestion]
    }
  } finally {
    if (seq === searchSeq) {
      suggestions.value = results
      searchOpen.value = results.length > 0
      searchIssue.value = results.length
        ? ''
        : isCep
          ? 'Não achamos esse CEP. Confira os números — ou toque em "Preencher manualmente" e escreva o endereço.'
          : 'Nenhum endereço com esse nome. Tente a rua com o número, ou o CEP. Se preferir, preencha manualmente.'
      searching.value = false
    }
  }
}

async function placesSuggestions (input: string): Promise<PickerSuggestion[]> {
  try {
    const placesLib = await maps.importLibrary<google.maps.PlacesLibrary>('places')
    if (!placesLib?.AutocompleteSuggestion) return []
    placesSessionToken = placesSessionToken || new placesLib.AutocompleteSessionToken()
    const request: google.maps.places.AutocompleteRequest = {
      input,
      sessionToken: placesSessionToken,
      includedRegionCodes: ['br'],
      language: 'pt-BR'
    }
    if (maps.shopLocation.value) {
      request.locationBias = { center: maps.shopLocation.value, radius: 30000 }
    }
    const { suggestions: raw } = await placesLib.AutocompleteSuggestion.fetchAutocompleteSuggestions(request)
    return (raw || [])
      .filter((entry): entry is google.maps.places.AutocompleteSuggestion & { placePrediction: google.maps.places.PlacePrediction } => Boolean(entry?.placePrediction))
      .map((entry): PickerSuggestion => ({
        id: `place-${entry.placePrediction.placeId}`,
        kind: 'place',
        main: entry.placePrediction.mainText?.text || entry.placePrediction.text?.text || '',
        secondary: entry.placePrediction.secondaryText?.text || '',
        prediction: entry.placePrediction
      }))
  } catch {
    return []
  }
}

async function viaCepSuggestion (value: string): Promise<PickerSuggestion | null> {
  try {
    const cep = value.replace(/\D/g, '')
    const payload = await $fetch<ViaCepPayload>(`https://viacep.com.br/ws/${cep}/json/`)
    const partial = draftFromViaCep(payload, cep)
    if (!partial) return null
    return {
      id: `cep-${cep}`,
      kind: 'cep',
      main: partial.formatted_address || maskCepInput(cep),
      secondary: `CEP ${maskCepInput(cep)}`,
      cepPartial: partial
    }
  } catch {
    return null
  }
}

async function acceptSuggestion (suggestion: PickerSuggestion) {
  searchOpen.value = false
  searchIssue.value = ''
  draftOriginatedFromCurrentLocation.value = false
  if (suggestion.kind === 'cep' && suggestion.cepPartial) {
    applyPartial(suggestion.cepPartial)
    return
  }
  if (!suggestion.prediction) return
  try {
    searching.value = true
    const place = suggestion.prediction.toPlace()
    await place.fetchFields({ fields: ['addressComponents', 'formattedAddress', 'location', 'id'] })
    placesSessionToken = null
    const location = place.location
    const latitude = location ? location.lat() : null
    const longitude = location ? location.lng() : null
    const partial = draftFromGooglePlace({
      id: place.id,
      formattedAddress: place.formattedAddress,
      addressComponents: place.addressComponents,
      latitude,
      longitude
    })
    if (mapConfirmationEnabled.value && latitude != null && longitude != null) {
      replaceDraft(partial)
      await openMapAdjust('place', null, 'search')
    } else {
      applyPartial(partial)
    }
  } catch {
    // `applyPartial` não chegou a rodar, então `mode` continua 'search' — e o
    // `saveIssue` só aparece no modo `form`. A recusa vai para o card da busca.
    searchIssue.value = 'Não deu para abrir este endereço. Escolha outro resultado da lista, ou toque em "Preencher manualmente".'
  } finally {
    searching.value = false
  }
}

function applyPartial (partial: Partial<AddressDraft>, fromCurrentLocation = false) {
  replaceDraft(partial)
  draftOriginatedFromCurrentLocation.value = fromCurrentLocation
  mode.value = 'form'
  void focusGuided()
}

function replaceDraft (partial: Partial<AddressDraft>) {
  const preserved = { complement: draft.complement, delivery_instructions: draft.delivery_instructions }
  Object.assign(draft, emptyAddressDraft(), preserved, partial)
  draft.postal_code = maskCepInput(draft.postal_code)
  acceptedLine.value = draftLine.value
  fieldErrors.value = {}
  geoCandidate.value = null
}

async function focusGuided () {
  await nextTick()
  const target = nextFocusAfterSuggestion(draft) === 'street_number' ? numberInput.value : complementInput.value
  focusUiInput(target)
}

async function startManualEntry () {
  resetDraft()
  mode.value = 'form'
  await nextTick()
  focusUiInput(routeInput.value)
}

function backToSearch () {
  mode.value = 'search'
  void focusSearch()
}

// ── "Usar minha localização" — banner de candidato, nunca silencioso ───

async function locateMe () {
  telemetry.addressEvent('address.location.requested', { origin: 'checkout' })
  if (!import.meta.client || !navigator.geolocation) {
    // Quem não informa a posição é o navegador (ou o contexto inseguro), não o
    // aparelho: acusar o telefone manda o cliente procurar defeito onde não há.
    geoIssue.value = 'Este navegador não informa sua localização. Busque pela rua ou pelo CEP aqui em cima.'
    telemetry.addressEvent('address.location.denied', { reason: 'unsupported' })
    return
  }
  const startedAt = performance.now()
  locating.value = true
  geoIssue.value = ''
  searchIssue.value = ''
  geoCandidate.value = null
  // Some a busca digitada e suas sugestões: a resposta agora é o candidato
  // de localização — duas respostas na tela ao mesmo tempo confundem.
  query.value = ''
  suggestions.value = []
  searchOpen.value = false
  try {
    const coords = await new Promise<GeolocationCoordinates>((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(position => resolve(position.coords), reject, {
        enableHighAccuracy: true,
        timeout: 10000
      })
    })
    const point = { lat: coords.latitude, lng: coords.longitude }
    telemetry.addressEvent('address.location.resolved', {
      accuracy_bucket: accuracyBucket(coords.accuracy),
      latency_bucket: latencyBucket(performance.now() - startedAt)
    })
    const reverse = $fetch<StructuredAddressProjection>(apiPath('/api/v1/geocode/reverse/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { lat: coords.latitude, lng: coords.longitude }
    })
    if (mapConfirmationEnabled.value) {
      const sessionId = mapSession + 1
      mapPendingReverse = reverse.catch(() => null)
      replaceDraft({
        latitude: coords.latitude,
        longitude: coords.longitude,
        coordinates_source: 'pin'
      })
      await openMapAdjust('gps', coords.accuracy, 'search')
      try {
        const result = await mapPendingReverse
        if (result && mapOpen.value && mapSession === sessionId) {
          Object.assign(draft, mergeConfirmedPoint(draft as AddressDraft, result, point, 'pin'))
          acceptedLine.value = draftLine.value
        } else if (!result) {
          telemetry.addressEvent('address.map.fallback', { origin: 'gps', reason: 'reverse' })
        }
      } catch { /* o wrapper acima degrada para null; defesa para mocks não conformes */ }
    } else {
      const result = await reverse
      geoCandidate.value = {
        ...mergeReverseGeocode(emptyAddressDraft(), result),
        coordinates_source: 'pin'
      }
    }
  } catch (e) {
    // Três causas, três gestos diferentes: uma frase só mandaria o cliente tentar
    // o que não resolve o caso dele.
    const code = (e as GeolocationPositionError | undefined)?.code
    telemetry.addressEvent('address.location.denied', {
      reason: code === 1 ? 'denied' : code === 3 ? 'timeout' : 'unavailable'
    })
    geoIssue.value = code === 1
      ? 'Você não liberou a localização para a loja. Dá para liberar nas configurações do navegador — ou buscar pela rua ou pelo CEP aqui em cima.'
      : code === 3
        ? 'Demorou demais para achar você. Tente de novo, ou busque pela rua ou pelo CEP aqui em cima.'
        : errorDetail(e, 'Não conseguimos achar onde você está. Busque pela rua ou pelo CEP aqui em cima.')
  } finally {
    locating.value = false
  }
}

function useGeoCandidate () {
  if (!geoCandidate.value) return
  applyPartial({ ...geoCandidate.value }, true)
}

async function useCurrentLocationFromMismatch () {
  const fix = locationCheckFix.value
  if (!fix) return
  recordLocationCheckAction('use_current')
  mapDraftSnapshot.value = {
    draft: { ...(draft as AddressDraft) },
    acceptedLine: acceptedLine.value
  }
  mapRecoveryPath.value = 'use_current'
  mapComparisonFix.value = null
  const reverse = $fetch<StructuredAddressProjection>(apiPath('/api/v1/geocode/reverse/'), {
    method: 'POST',
    headers: await csrfHeaders(),
    credentials: 'include',
    body: fix.point
  })
  const reverseResult = reverse.catch(() => null)
  mapPendingReverse = reverseResult
  replaceDraft({
    latitude: fix.point.lat,
    longitude: fix.point.lng,
    coordinates_source: 'pin'
  })
  draftOriginatedFromCurrentLocation.value = true
  const sessionId = mapSession + 1
  await openMapAdjust('gps', fix.accuracyM, mode.value)
  const result = await reverseResult
  if (result && mapOpen.value && mapSession === sessionId) {
    Object.assign(draft, mergeConfirmedPoint(draft as AddressDraft, result, fix.point, 'pin'))
    acceptedLine.value = draftLine.value
  }
}

async function reviewLocationMismatchOnMap () {
  const fix = locationCheckFix.value
  if (!fix) return
  recordLocationCheckAction('review_map')
  if (mode.value === 'saved') {
    const address = props.savedAddresses.find(candidate => candidate.id === selectedSavedId.value)
    if (!address) return
    Object.assign(draft, draftFromSavedAddress(address))
    acceptedLine.value = address.formatted_address || draftLine.value
  }
  if (!canAdjustOnMap.value) return
  mapRecoveryPath.value = 'review_map'
  mapComparisonFix.value = fix
  await openMapAdjust('adjust', null, mode.value, fix)
}

// ── Ajustar/confirmar no mapa (bottom-sheet ~85%, pin central) ─────────

async function openMapAdjust (
  origin: MapOrigin = 'adjust',
  accuracyM: number | null = null,
  returnMode: PickerMode = 'form',
  comparisonFix: CurrentLocationFix | null = null
) {
  if (!canAdjustOnMap.value) return
  const sessionId = ++mapSession
  if (origin !== 'gps') mapPendingReverse = null
  const startedAt = performance.now()
  mapOrigin.value = origin
  mapReturnMode.value = returnMode
  mapComparisonFix.value = comparisonFix
  mapApplied.value = false
  mapAccuracyM.value = typeof accuracyM === 'number' && Number.isFinite(accuracyM) ? accuracyM : null
  mapMoved.value = false
  mapInitialPoint.value = { lat: draft.latitude as number, lng: draft.longitude as number }
  mapOpen.value = true
  mapLoading.value = true
  mapIssue.value = ''
  await nextTick()
  try {
    const mapsLib = await maps.importLibrary<google.maps.MapsLibrary>('maps')
    if (!mapsLib?.Map || !mapEl.value) {
      mapIssue.value = 'O mapa não está disponível agora.'
      telemetry.addressEvent('address.map.fallback', { origin, reason: 'unsupported' })
      return
    }
    const center = { lat: draft.latitude as number, lng: draft.longitude as number }
    mapInstance = new mapsLib.Map(mapEl.value, {
      center,
      zoom: comparisonFix ? comparisonZoom(distanceMetres(center, comparisonFix.point)) : 17,
      minZoom: 8,
      disableDefaultUI: true,
      zoomControl: true,
      gestureHandling: 'greedy',
      clickableIcons: false,
      styles: [
        { elementType: 'geometry', stylers: [{ saturation: -70 }, { lightness: 8 }] },
        { elementType: 'labels.icon', stylers: [{ saturation: -100 }] },
        { featureType: 'poi', stylers: [{ visibility: 'off' }] },
        { featureType: 'transit', stylers: [{ visibility: 'off' }] }
      ]
    })
    const accuracyCenter = comparisonFix?.point || center
    const accuracyRadius = comparisonFix?.accuracyM ?? mapAccuracyM.value
    if (accuracyRadius != null && accuracyRadius > 0) {
      mapAccuracyCircle = new mapsLib.Circle({
        map: mapInstance,
        center: accuracyCenter,
        radius: accuracyRadius,
        clickable: false,
        fillColor: '#7c3aed',
        fillOpacity: 0.08,
        strokeColor: '#7c3aed',
        strokeOpacity: 0.35,
        strokeWeight: 1
      })
    }
    if (comparisonFix) {
      mapComparisonMarker = new google.maps.Marker({
        map: mapInstance,
        position: comparisonFix.point,
        title: 'Sua localização atual',
        label: { text: 'Você', color: '#ffffff', fontSize: '11px', fontWeight: '700' },
        icon: {
          path: google.maps.SymbolPath.CIRCLE,
          fillColor: '#7c3aed',
          fillOpacity: 1,
          strokeColor: '#ffffff',
          strokeOpacity: 1,
          strokeWeight: 2,
          scale: 14,
          labelOrigin: new google.maps.Point(0, 0)
        },
        zIndex: 2
      })
    }
    mapInstance.addListener('center_changed', () => {
      if (sessionId !== mapSession || !mapInitialPoint.value) return
      const current = mapCenter()
      if (!current) return
      mapMoved.value = pointMoved(mapInitialPoint.value, current)
      if (!mapComparisonFix.value) mapAccuracyCircle?.setCenter(current)
    })
    telemetry.addressEvent('address.map.ready', {
      origin,
      latency_bucket: latencyBucket(performance.now() - startedAt)
    })
  } catch {
    mapIssue.value = 'O mapa não está disponível agora.'
    telemetry.addressEvent('address.map.fallback', { origin, reason: 'provider' })
  } finally {
    mapLoading.value = false
  }
}

async function confirmMapAdjust () {
  const point = mapCenter()
  if (!point) {
    mapOpen.value = false
    return
  }
  const moved = !!mapInitialPoint.value && pointMoved(mapInitialPoint.value, point)
  mapLoading.value = true
  try {
    let result: StructuredAddressProjection | null = null
    if (!moved && mapOrigin.value === 'gps' && mapPendingReverse) {
      result = await mapPendingReverse
    } else if (moved) {
      result = await $fetch<StructuredAddressProjection>(apiPath('/api/v1/geocode/reverse/'), {
        method: 'POST',
        headers: await csrfHeaders(),
        credentials: 'include',
        body: point
      })
    }
    const source = mapOrigin.value === 'place' && !moved ? 'geocoded' : 'pin'
    Object.assign(draft, mergeConfirmedPoint({ ...(draft as AddressDraft) }, result, point, source))
    telemetry.addressEvent('address.map.confirmed', {
      origin: mapOrigin.value,
      accuracy_bucket: mapAccuracyKind.value,
      moved
    })
    acceptedLine.value = draftLine.value
    draftOriginatedFromCurrentLocation.value = mapOrigin.value === 'gps'
    mapApplied.value = true
    if (mapRecoveryPath.value) {
      telemetry.addressEvent('address.location_mismatch.recovered', {
        path: mapRecoveryPath.value,
        zone_result: 'deferred'
      })
    }
    mapOpen.value = false
    mode.value = 'form'
    await focusGuided()
  } catch (e) {
    mapIssue.value = errorDetail(e, 'Não foi possível confirmar o ponto. Tente de novo.')
  } finally {
    mapLoading.value = false
  }
}

watch(mapOpen, open => {
  if (!open) {
    if (!mapApplied.value) restoreMapDraftSnapshot()
    if (mapInstance && window.google?.maps?.event) window.google.maps.event.clearInstanceListeners(mapInstance)
    mapInstance = null
    mapAccuracyCircle?.setMap(null)
    mapAccuracyCircle = null
    mapComparisonMarker?.setMap(null)
    mapComparisonMarker = null
    mapPendingReverse = null
    mapIssue.value = ''
    mapComparisonFix.value = null
    mapRecoveryPath.value = null
    mapDraftSnapshot.value = null
    mapApplied.value = false
  }
})

onBeforeUnmount(() => {
  mapSession += 1
  if (mapInstance && window.google?.maps?.event) window.google.maps.event.clearInstanceListeners(mapInstance)
  mapAccuracyCircle?.setMap(null)
  mapComparisonMarker?.setMap(null)
})

function restoreMapDraftSnapshot () {
  const snapshot = mapDraftSnapshot.value
  if (!snapshot) return
  Object.assign(draft, emptyAddressDraft(), snapshot.draft)
  acceptedLine.value = snapshot.acceptedLine
  draftOriginatedFromCurrentLocation.value = false
}

function comparisonZoom (distanceM: number): number {
  if (distanceM <= 300) return 16
  if (distanceM <= 1_000) return 14
  if (distanceM <= 5_000) return 12
  if (distanceM <= 20_000) return 10
  return 8
}

function mapCenter (): AddressPoint | null {
  const center = mapInstance?.getCenter?.()
  return center ? { lat: center.lat(), lng: center.lng() } : null
}

function cancelMap () {
  mode.value = mapReturnMode.value
  mapOpen.value = false
}

function moveMapWithKeyboard (event: KeyboardEvent) {
  const delta = 32
  const movement: Record<string, [number, number]> = {
    ArrowLeft: [-delta, 0],
    ArrowRight: [delta, 0],
    ArrowUp: [0, -delta],
    ArrowDown: [0, delta]
  }
  const offset = movement[event.key]
  if (!offset || !mapInstance) return
  event.preventDefault()
  mapInstance.panBy(offset[0], offset[1])
}

function retryLocationFromMap () {
  mapOpen.value = false
  void locateMe()
}

function latencyBucket (milliseconds: number): 'fast' | 'normal' | 'slow' {
  if (milliseconds <= 1000) return 'fast'
  if (milliseconds <= 4000) return 'normal'
  return 'slow'
}

// ── Salvar + etiqueta DEPOIS ───────────────────────────────────────────

function onCepInput () {
  draft.postal_code = maskCepInput(draft.postal_code)
}

function addressApiPayload (): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    formatted_address: composedAddressLine(draft as AddressDraft) || draft.formatted_address,
    route: draft.route.trim(),
    street_number: draft.street_number.trim(),
    neighborhood: draft.neighborhood.trim(),
    city: draft.city.trim(),
    state_code: draft.state_code.trim().toUpperCase(),
    postal_code: maskCepInput(draft.postal_code),
    complement: draft.complement.trim(),
    delivery_instructions: draft.delivery_instructions.trim(),
    place_id: draft.place_id || null
  }
  if (draft.latitude != null && draft.longitude != null) {
    payload.coordinates = [draft.latitude, draft.longitude]
  }
  return payload
}

function validateDraft (): boolean {
  fieldErrors.value = addressDraftErrors(draft as AddressDraft)
  return !Object.keys(fieldErrors.value).length
}

async function confirmDraft () {
  if (saving.value || !validateDraft()) return
  saveIssue.value = ''
  if (props.context === 'account') {
    await saveAccountAddress()
    return
  }
  if (editingSavedId.value) {
    await saveCheckoutEdit()
    return
  }
  // Checkout: NÃO grava no perfil aqui — só carrega o endereço no pedido. O
  // perfil é gravado pelo checkout APÓS o pedido confirmar (a etiqueta vem
  // nesse momento), para endereços fora de zona/abandonados nunca virarem
  // lixo no perfil do cliente.
  emit('update:selection', selectionFromDraft({ ...(draft as AddressDraft) }, null))
  emit('confirmed')
}

// PATCH de um salvo editado no checkout: persiste, re-seleciona com os dados
// novos (selection imediata) e pede ao pai pra re-buscar a lista de salvos.
async function saveCheckoutEdit () {
  const id = editingSavedId.value
  if (!id) return
  saving.value = true
  try {
    await $fetch(apiPath(`/api/v1/account/addresses/${encodeURIComponent(id)}/`), {
      method: 'PATCH',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: {
        ...addressApiPayload(),
        ...labelPatchPayload(accountLabel.value, accountLabelCustom.value),
        is_default: isDefault.value
      }
    })
    selectedSavedId.value = id
    emit('update:selection', selectionFromDraft({ ...(draft as AddressDraft) }, id))
    emit('addresses-changed')
    editingSavedId.value = null
    mode.value = 'saved'
  } catch (e) {
    saveIssue.value = errorDetail(e, 'Não foi possível salvar o endereço agora.')
  } finally {
    saving.value = false
  }
}

async function saveAccountAddress () {
  saving.value = true
  try {
    if (isEditing.value && props.editingAddress) {
      await $fetch(apiPath(`/api/v1/account/addresses/${encodeURIComponent(props.editingAddress.id)}/`), {
        method: 'PATCH',
        headers: await csrfHeaders(),
        credentials: 'include',
        body: {
          ...addressApiPayload(),
          ...labelPatchPayload(accountLabel.value, accountLabelCustom.value),
          is_default: isDefault.value
        }
      })
      emit('done')
      return
    }
    const created = await $fetch<SavedAddressProjection>(apiPath('/api/v1/account/addresses/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: {
        ...addressApiPayload(),
        label: 'other',
        label_custom: '',
        is_default: isDefault.value
      }
    })
    pendingCreatedId.value = created?.id ?? null
    labelOpen.value = true
  } catch (e) {
    saveIssue.value = errorDetail(e, 'Não foi possível salvar o endereço agora.')
  } finally {
    saving.value = false
  }
}

// Etiqueta de um endereço novo na conta — resolvida pelo AddressLabelSheet
// (escolha, custom ou "agora não" por gesto). Concluído → fecha o sheet pai.
function onLabelResolved () {
  pendingCreatedId.value = null
  emit('done')
}
</script>

<template>
  <div class="space-y-4" data-address-picker>
    <!-- ── Endereços salvos (checkout) ─────────────────────────────── -->
    <template v-if="mode === 'saved'">
      <UiRadioGroup
        :model-value="selectedSavedId"
        class="grid gap-2"
        data-address-saved-list
        @update:model-value="pickSaved(Number($event))"
      >
        <UiFieldLabel v-for="address in savedAddresses" :key="address.id" :for="`address-saved-${address.id}`" class="bg-card has-data-[state=checked]:bg-card has-data-[state=checked]:ring-1 has-data-[state=checked]:ring-primary">
          <UiField orientation="horizontal">
            <UiRadioGroupItem
              :id="`address-saved-${address.id}`"
              :value="address.id"
              :data-focus-control="address.id === selectedSavedId ? '' : undefined"
            />
            <UiFieldContent>
              <UiFieldTitle>
                <Icon name="lucide:map-pin-house" class="size-4" />
                {{ savedAddressDisplayLabel(address) }}
                <UiBadge v-if="address.is_default" variant="secondary">Padrão</UiBadge>
              </UiFieldTitle>
              <UiFieldDescription>
                {{ address.formatted_address }}<template v-if="address.complement"> · {{ address.complement }}</template>
              </UiFieldDescription>
            </UiFieldContent>
            <UiButton
              variant="ghost"
              size="sm"
              icon="lucide:pencil"
              class="-my-1 shrink-0 self-start text-muted-foreground hover:text-foreground"
              aria-label="Editar este endereço"
              data-address-edit-saved
              @click.stop.prevent="startEditSaved(address)"
            />
          </UiField>
        </UiFieldLabel>
      </UiRadioGroup>
      <AddressLocationDivergence
        :mode="locationConfig.mode"
        :state="locationCheckState"
        :status-message="locationCheckStatus"
        :can-review-map="!!locationCheckTarget?.point"
        :can-use-current="!!locationCheckFix"
        @request="requestLocationCheck"
        @keep="keepCheckedAddress('keep')"
        @dismiss="keepCheckedAddress('dismiss')"
        @use-current="useCurrentLocationFromMismatch"
        @review-map="reviewLocationMismatchOnMap"
      />
      <UiButton variant="ghost" size="sm" icon="lucide:plus" class="-ml-2" data-address-new @click="startNewAddress">
        Novo endereço
      </UiButton>
    </template>

    <!-- ── Busca unificada (card dedicado, ações fullwidth) ──────────── -->
    <template v-else-if="mode === 'search'">
      <div class="shop-stack-block" :class="surfaceChrome" data-address-search-card>
        <div class="flex items-center justify-between gap-2">
          <UiLabel for="address-search">Buscar endereço ou CEP</UiLabel>
          <UiButton
            v-if="hasSaved"
            variant="ghost"
            size="sm"
            icon="lucide:x"
            class="-my-1 -mr-2 text-muted-foreground hover:text-foreground"
            aria-label="Fechar e voltar aos endereços salvos"
            data-address-dismiss
            @click="backToSaved"
          />
        </div>
        <UiInputGroup class="h-11">
          <UiInputGroupAddon align="inline-start">
            <Icon v-if="!searching" name="lucide:search" />
            <Icon v-else name="lucide:loader-circle" class="animate-spin" />
          </UiInputGroupAddon>
          <UiInputGroupInput
            id="address-search"
            ref="searchInput"
            v-model="query"
            type="text"
            autocomplete="off"
            autocapitalize="words"
            enterkeyhint="search"
            placeholder="Rua, número ou CEP"
            data-address-search
            data-focus-control
            @input="onQueryInput"
            @keydown.enter.prevent="runSearch(query)"
          />
        </UiInputGroup>
        <!-- Sugestões inline (fluxo de bloco) — sem overlay/clipping. -->
        <ul
          v-if="searchOpen"
          class="divide-y overflow-hidden rounded-md border bg-card"
          data-address-suggestions
        >
          <li v-for="suggestion in suggestions" :key="suggestion.id">
            <UiButton
              variant="ghost"
              class="h-auto min-h-11 w-full flex-col items-start gap-1 whitespace-normal rounded-none px-3 py-2 text-left font-normal"
              @click="acceptSuggestion(suggestion)"
            >
              <span class="w-full text-sm font-semibold">{{ suggestion.main }}</span>
              <span v-if="suggestion.secondary" class="w-full text-xs text-muted-foreground">{{ suggestion.secondary }}</span>
            </UiButton>
          </li>
        </ul>
        <p v-if="searchIssue" class="text-sm text-destructive" data-address-search-issue>{{ searchIssue }}</p>
        <p v-if="geoIssue" class="text-sm text-destructive">{{ geoIssue }}</p>

        <UiButton
          variant="outline"
          size="lg"
          class="w-full justify-center"
          :loading="locating"
          icon="lucide:locate-fixed"
          data-address-locate
          @click="locateMe"
        >
          Usar minha localização
        </UiButton>

        <!-- Candidato da localização: confirmação explícita, nunca silencioso. -->
        <div v-if="geoCandidate" class="shop-stack-tight rounded-md border bg-card p-3" data-address-geo-candidate>
          <div class="flex items-start gap-2">
            <Icon name="lucide:map-pin" class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <div class="min-w-0">
              <p class="text-sm font-semibold">Você está aqui?</p>
              <p class="mt-0.5 text-sm text-muted-foreground">{{ draftSummaryLine(geoCandidate) }}</p>
            </div>
          </div>
          <div class="flex flex-wrap gap-2">
            <UiButton size="sm" class="min-h-10" @click="useGeoCandidate">Usar este endereço</UiButton>
            <UiButton size="sm" variant="ghost" class="min-h-10" @click="geoCandidate = null">Agora não</UiButton>
          </div>
        </div>

        <UiButton variant="ghost" size="lg" class="w-full justify-center" data-address-manual @click="startManualEntry">
          Preencher manualmente
        </UiButton>
      </div>
    </template>

    <!-- ── Campos estruturados ─────────────────────────────────────── -->
    <template v-else>
      <div class="space-y-4" :class="surfaceChrome" data-address-form-card>
      <div class="flex items-center justify-between gap-2">
        <p class="text-sm font-semibold">{{ isEditingForm ? 'Editar endereço' : 'Novo endereço' }}</p>
        <UiButton
          variant="ghost"
          size="sm"
          icon="lucide:x"
          class="-my-1 -mr-2 text-muted-foreground hover:text-foreground"
          aria-label="Fechar"
          data-address-form-dismiss
          @click="dismissForm"
        />
      </div>
      <div v-if="acceptedLine" class="space-y-1" data-address-accepted>
        <div class="flex items-start gap-2">
          <Icon name="lucide:map-pin" class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <p class="min-w-0 flex-1 text-sm font-semibold">{{ acceptedLine }}</p>
        </div>
        <UiButton
          v-if="canAdjustOnMap"
          variant="ghost"
          size="sm"
          icon="lucide:map"
          class="-ml-2 text-muted-foreground hover:text-foreground"
          data-address-adjust-map
          @click="openMapAdjust()"
        >
          Ajustar no mapa
        </UiButton>
      </div>

      <AddressLocationDivergence
        :mode="locationConfig.mode"
        :state="locationCheckState"
        :status-message="locationCheckStatus"
        :can-review-map="!!locationCheckTarget?.point"
        :can-use-current="!!locationCheckFix"
        @request="requestLocationCheck"
        @keep="keepCheckedAddress('keep')"
        @dismiss="keepCheckedAddress('dismiss')"
        @use-current="useCurrentLocationFromMismatch"
        @review-map="reviewLocationMismatchOnMap"
      />

      <UiAlert v-if="saveIssue" variant="destructive">
        <UiAlertTitle>Revise o endereço</UiAlertTitle>
        <UiAlertDescription>{{ saveIssue }}</UiAlertDescription>
      </UiAlert>

      <div class="grid grid-cols-1 gap-4">
        <div class="space-y-2">
          <UiLabel for="address-route">Rua</UiLabel>
          <UiInput
            id="address-route"
            ref="routeInput"
            v-model="draft.route"
            autocomplete="address-line1"
            enterkeyhint="next"
            class="h-11"
            @keydown.enter.prevent="focusNextInput(numberInput)"
          />
          <UiFieldError v-if="fieldErrors.route" :errors="fieldErrors.route" />
        </div>
        <div class="grid grid-cols-[7rem_minmax(0,1fr)] gap-4">
          <div class="space-y-2">
            <UiLabel for="address-number">Número</UiLabel>
            <UiInput
              id="address-number"
              ref="numberInput"
              v-model="draft.street_number"
              enterkeyhint="next"
              class="h-11"
              @keydown.enter.prevent="focusNextInput(complementInput)"
            />
            <UiFieldError v-if="fieldErrors.street_number" :errors="fieldErrors.street_number" />
          </div>
          <div class="space-y-2">
            <UiLabel for="address-complement">Complemento</UiLabel>
            <UiInput
              id="address-complement"
              ref="complementInput"
              v-model="draft.complement"
              enterkeyhint="next"
              class="h-11"
              placeholder="Apto, bloco, referência"
              @keydown.enter.prevent="focusNextInput(neighborhoodInput)"
            />
          </div>
        </div>
        <div class="grid grid-cols-[minmax(0,1fr)_8rem] gap-4">
          <div class="space-y-2">
            <UiLabel for="address-neighborhood">Bairro</UiLabel>
            <UiInput
              id="address-neighborhood"
              ref="neighborhoodInput"
              v-model="draft.neighborhood"
              autocomplete="address-level3"
              enterkeyhint="next"
              class="h-11"
              @keydown.enter.prevent="focusNextInput(cepInput)"
            />
            <UiFieldError v-if="fieldErrors.neighborhood" :errors="fieldErrors.neighborhood" />
          </div>
          <div class="space-y-2">
            <UiLabel for="address-cep">CEP</UiLabel>
            <UiInput
              id="address-cep"
              ref="cepInput"
              v-model="draft.postal_code"
              inputmode="numeric"
              autocomplete="postal-code"
              enterkeyhint="next"
              class="h-11"
              placeholder="00000-000"
              @input="onCepInput"
              @keydown.enter.prevent="focusNextInput(cityInput)"
            />
            <UiFieldError v-if="fieldErrors.postal_code" :errors="fieldErrors.postal_code" />
          </div>
        </div>
        <div class="grid grid-cols-[minmax(0,1fr)_6rem] gap-4">
          <div class="space-y-2">
            <UiLabel for="address-city">Cidade</UiLabel>
            <UiInput
              id="address-city"
              ref="cityInput"
              v-model="draft.city"
              autocomplete="address-level2"
              enterkeyhint="done"
              class="h-11"
              @keydown.enter.prevent="finishTextEntry"
            />
            <UiFieldError v-if="fieldErrors.city" :errors="fieldErrors.city" />
          </div>
          <div class="space-y-2">
            <UiLabel for="address-state">UF</UiLabel>
            <UiSelect v-model="draft.state_code">
              <UiSelectTrigger id="address-state" class="w-full" />
              <UiSelectContent>
                <UiSelectItem v-for="uf in brStates" :key="uf" :value="uf">{{ uf }}</UiSelectItem>
              </UiSelectContent>
            </UiSelect>
            <UiFieldError v-if="fieldErrors.state_code" :errors="fieldErrors.state_code" />
          </div>
        </div>
        <div class="space-y-2">
          <UiLabel for="address-instructions">Instruções de entrega</UiLabel>
          <UiInput
            id="address-instructions"
            v-model="draft.delivery_instructions"
            enterkeyhint="done"
            class="h-11"
            placeholder="Portaria, interfone, melhor acesso"
            @keydown.enter.prevent="finishTextEntry"
          />
        </div>
      </div>

      <!-- Etiqueta editável inline na edição (conta ou salvo do checkout). -->
      <template v-if="isEditingForm">
        <div class="space-y-2">
          <UiLabel>Etiqueta</UiLabel>
          <div class="flex flex-wrap gap-2">
            <UiButton
              v-for="option in labelOptions"
              :key="option.key"
              size="sm"
              class="min-h-10"
              :variant="accountLabel === option.key ? 'default' : 'outline'"
              :icon="option.icon"
              @click="accountLabel = option.key"
            >
              {{ option.key === 'other' ? 'Outro' : option.label }}
            </UiButton>
          </div>
          <UiInput
            v-if="accountLabel === 'other'"
            v-model="accountLabelCustom"
            placeholder="Ex: Casa da mãe"
            aria-label="Nome da etiqueta"
          />
        </div>
      </template>

      <UiFieldLabel v-if="context === 'account' || editingSavedId" for="address-default" class="w-full">
        <div class="-mx-4 flex w-full items-center gap-4 border-y px-4 py-3 sm:mx-0 sm:px-0">
          <div class="min-w-0 flex-1">
            <p class="text-sm font-semibold">Usar como padrão</p>
            <p class="mt-0.5 text-xs font-normal leading-5 text-muted-foreground">Este endereço aparece primeiro na próxima compra.</p>
          </div>
          <UiSwitch id="address-default" v-model="isDefault" />
        </div>
      </UiFieldLabel>

      <div class="space-y-2">
        <UiButton size="lg" class="w-full justify-center" :loading="saving" icon="lucide:check" data-address-confirm @click="confirmDraft">
          {{ isEditingForm ? 'Salvar alterações' : (context === 'account' ? 'Salvar endereço' : 'Usar este endereço') }}
        </UiButton>
        <UiButton
          v-if="editingSavedId"
          variant="outline"
          size="lg"
          class="w-full justify-center"
          @click="cancelEdit"
        >
          Cancelar
        </UiButton>
        <UiButton
          v-else-if="!isEditing"
          variant="outline"
          size="lg"
          class="w-full justify-center"
          @click="backToSearch"
        >
          Buscar outro endereço
        </UiButton>
      </div>
      </div>
    </template>

    <!-- ── Confirmar no mapa: bottom-sheet ~85%, pin central ──────────── -->
    <BottomSheet
      v-model:open="mapOpen"
      content-class="h-[85dvh]"
      :title="mapComparisonFix ? 'Confira os dois pontos' : (mapConfirmationEnabled && mapOrigin !== 'adjust' ? 'É aqui que vamos entregar?' : 'Ajustar no mapa')"
      :description="mapComparisonFix ? 'O pin marca a entrega; o círculo mostra onde você está.' : 'Mova o mapa até o pin ficar no ponto certo.'"
      data-address-map-sheet
    >
      <div class="relative h-full">
        <div
          ref="mapEl"
          class="absolute inset-0"
          tabindex="0"
          role="application"
          aria-label="Mapa do ponto de entrega. Use as setas para mover o mapa sob o pin."
          @keydown="moveMapWithKeyboard"
        />
        <div class="pointer-events-none absolute inset-0 grid place-items-center" aria-hidden="true">
          <div class="flex -translate-y-4 flex-col items-center gap-1">
            <div class="rounded-full bg-primary p-2 text-primary-foreground shadow-lg ring-4 ring-background/80">
              <Icon name="lucide:map-pin" class="size-6" />
            </div>
            <span v-if="mapComparisonFix" class="rounded-full bg-card px-2 py-0.5 text-xs font-semibold text-foreground shadow">Entrega</span>
          </div>
        </div>
        <div v-if="mapLoading" class="absolute inset-0 grid place-items-center bg-background/60">
          <Icon name="lucide:loader-circle" class="size-6 animate-spin text-muted-foreground" />
        </div>
        <p v-if="mapIssue" class="absolute inset-x-4 top-3 rounded-md border bg-card px-3 py-2 text-sm text-destructive shadow-sm">
          {{ mapIssue }}
        </p>
      </div>
      <template #footer>
        <div class="shop-stack-tight w-full">
          <div aria-live="polite" class="space-y-1 text-left">
            <p v-if="draftLine" class="text-sm font-semibold">{{ draftLine }}</p>
            <p v-if="mapComparisonFix" class="text-xs text-muted-foreground">
              O pin marca o ponto de entrega. O círculo roxo com “Você” mostra sua localização atual e a precisão disponível.
            </p>
            <p v-else class="text-xs text-muted-foreground">{{ mapAccuracyText }}</p>
            <p v-if="mapMoved" class="text-xs font-semibold text-primary">Ponto ajustado.</p>
          </div>
          <UiButton
            v-if="mapOrigin === 'gps' && mapAccuracyKind === 'low'"
            variant="ghost"
            class="w-full"
            icon="lucide:locate-fixed"
            @click="retryLocationFromMap"
          >
            Tentar localizar novamente
          </UiButton>
          <div class="grid grid-cols-2 gap-2">
            <UiButton variant="outline" class="w-full" @click="cancelMap">Voltar</UiButton>
            <UiButton class="w-full" :loading="mapLoading" @click="confirmMapAdjust">
              {{ mapConfirmationEnabled && mapOrigin !== 'adjust' ? 'É aqui' : 'Confirmar' }}
            </UiButton>
          </div>
        </div>
      </template>
    </BottomSheet>

    <!-- ── Etiqueta DEPOIS de salvar (conta) — componente compartilhado ── -->
    <AddressLabelSheet v-model:open="labelOpen" :address-id="pendingCreatedId" @resolved="onLabelResolved" />
  </div>
</template>
