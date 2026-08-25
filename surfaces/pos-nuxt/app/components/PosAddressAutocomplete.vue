<script setup lang="ts">
// Busca de endereço do checkout de entrega — o MESMO mecanismo do storefront
// (AddressPicker): Places API (New) via AutocompleteSuggestion + fallback
// silencioso ViaCEP quando a consulta parece CEP. A lista de sugestões é
// renderizada AQUI DENTRO (nada de .pac-container no <body>): dentro do modal
// de Recebimento o dropdown do widget legado nascia fora do dialog — invisível
// ou inclicável sob o focus-trap do reka-ui. Lógica pura em presentation/address.
import type { POSAddressAutocompleteProjection, StructuredAddressProjection } from "~/types/pos";
import type { GooglePlacePrediction, GooglePlace } from "~/types/googleMaps";
import {
  looksLikeCep,
  structuredFromPlaceFields,
  structuredFromViaCep,
  type ViaCepPayload,
} from "~/presentation/address";

interface AddressSuggestion {
  id: string;
  main: string;
  secondary: string;
  prediction?: GooglePlacePrediction;
  cepAddress?: StructuredAddressProjection;
}

const props = defineProps<{
  modelValue: string;
  capability: POSAddressAutocompleteProjection | null;
}>();

const emit = defineEmits<{
  "update:modelValue": [string];
  selected: [StructuredAddressProjection];
}>();

// O template ref pode ser o elemento nativo OU a instância do UiInput (que expõe
// `inputRef`); getInputElement() normaliza para o <input> real.
type AddressInputRef = HTMLInputElement | { inputRef?: HTMLInputElement; $el?: HTMLElement };
const inputRef = ref<AddressInputRef | null>(null);
function getInputElement(): HTMLInputElement | null {
  const refValue = inputRef.value;
  if (!refValue) return null;
  if (refValue instanceof HTMLInputElement) return refValue;
  if (refValue.inputRef) return refValue.inputRef;
  if (refValue.$el) return (refValue.$el as HTMLElement).querySelector?.("input") || null;
  return null;
}

const capabilityRef = computed(() => props.capability);
const { isAvailable, ensureLoaded } = usePosGoogleMaps(capabilityRef);

const suggestions = ref<AddressSuggestion[]>([]);
const listOpen = ref(false);
const highlighted = ref(-1);
const searching = ref(false);
const resolving = ref(false);
const error = ref("");

let searchTimer: ReturnType<typeof setTimeout> | null = null;
let searchSeq = 0;
let sessionToken: unknown = null;
// A seleção reescreve o input; sem esta trava o watch reabria a busca em cima
// do endereço recém-escolhido.
let suppressNextSearch = false;

function onInput(value: string) {
  emit("update:modelValue", value);
  if (suppressNextSearch) {
    suppressNextSearch = false;
    return;
  }
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => void runSearch(value), 300);
}

async function runSearch(value: string) {
  const seq = ++searchSeq;
  const trimmed = value.trim();
  if (trimmed.length < 3) {
    suggestions.value = [];
    listOpen.value = false;
    return;
  }
  searching.value = true;
  let results: AddressSuggestion[] = [];
  try {
    if (isAvailable.value) results = await placesSuggestions(trimmed);
    if (looksLikeCep(trimmed) && !results.length) {
      const cep = await viaCepSuggestion(trimmed);
      if (cep) results = [cep];
    }
  } finally {
    if (seq === searchSeq) {
      suggestions.value = results;
      highlighted.value = results.length ? 0 : -1;
      listOpen.value = results.length > 0;
      searching.value = false;
    }
  }
}

async function placesSuggestions(input: string): Promise<AddressSuggestion[]> {
  try {
    const places = await ensureLoaded();
    if (!places.AutocompleteSuggestion) return [];
    sessionToken = sessionToken || (places.AutocompleteSessionToken ? new places.AutocompleteSessionToken() : undefined);
    const config = props.capability;
    const request: Parameters<typeof places.AutocompleteSuggestion.fetchAutocompleteSuggestions>[0] = {
      input,
      sessionToken: sessionToken || undefined,
      includedRegionCodes: config?.countries?.length ? config.countries : ["br"],
      language: config?.language || "pt-BR",
      region: config?.region || "BR",
    };
    if (config?.shop_latitude != null && config?.shop_longitude != null) {
      request.locationBias = {
        center: { lat: config.shop_latitude, lng: config.shop_longitude },
        radius: config.bias_radius_m || 15000,
      };
    }
    const { suggestions: raw } = await places.AutocompleteSuggestion.fetchAutocompleteSuggestions(request);
    error.value = "";
    return (raw || [])
      .map((entry) => entry?.placePrediction)
      .filter((prediction): prediction is GooglePlacePrediction => Boolean(prediction))
      .map((prediction) => ({
        id: `place-${prediction.placeId || prediction.text?.text || ""}`,
        main: prediction.mainText?.text || prediction.text?.text || "",
        secondary: prediction.secondaryText?.text || "",
        prediction,
      }));
  } catch {
    error.value = "Busca automática indisponível.";
    return [];
  }
}

async function viaCepSuggestion(value: string): Promise<AddressSuggestion | null> {
  try {
    const cep = value.replace(/\D/g, "");
    const payload = await $fetch<ViaCepPayload>(`https://viacep.com.br/ws/${cep}/json/`);
    const address = structuredFromViaCep(payload, cep);
    if (!address) return null;
    return {
      id: `cep-${cep}`,
      main: address.formatted_address || cep,
      secondary: `CEP ${address.postal_code}`,
      cepAddress: address,
    };
  } catch {
    return null;
  }
}

function applyAddress(address: StructuredAddressProjection) {
  suppressNextSearch = true;
  emit("update:modelValue", address.formatted_address || address.route || "");
  emit("selected", address);
  suggestions.value = [];
  listOpen.value = false;
  highlighted.value = -1;
}

async function accept(suggestion: AddressSuggestion) {
  if (suggestion.cepAddress) {
    applyAddress(suggestion.cepAddress);
    return;
  }
  if (!suggestion.prediction) return;
  resolving.value = true;
  try {
    const place: GooglePlace = suggestion.prediction.toPlace();
    await place.fetchFields({ fields: ["addressComponents", "formattedAddress", "location", "id"] });
    sessionToken = null;
    applyAddress(structuredFromPlaceFields({
      id: place.id,
      formattedAddress: place.formattedAddress,
      addressComponents: place.addressComponents,
      latitude: place.location ? place.location.lat() : null,
      longitude: place.location ? place.location.lng() : null,
    }));
  } catch {
    error.value = "Não foi possível carregar este endereço. Tente outra busca.";
  } finally {
    resolving.value = false;
  }
}

function onKeydown(event: KeyboardEvent) {
  if (!listOpen.value || !suggestions.value.length) return;
  if (event.key === "ArrowDown") {
    event.preventDefault();
    highlighted.value = (highlighted.value + 1) % suggestions.value.length;
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    highlighted.value = (highlighted.value - 1 + suggestions.value.length) % suggestions.value.length;
  } else if (event.key === "Enter") {
    event.preventDefault();
    const suggestion = suggestions.value[highlighted.value] ?? suggestions.value[0];
    if (suggestion) void accept(suggestion);
  } else if (event.key === "Escape") {
    // Fecha SÓ a lista; sem o stop, o Esc também fechava o modal por cima dela.
    event.preventDefault();
    event.stopPropagation();
    listOpen.value = false;
  }
}

function onBlur() {
  // Deixa o clique na sugestão acontecer antes de recolher a lista.
  window.setTimeout(() => { listOpen.value = false; }, 150);
}

function focus() {
  getInputElement()?.focus();
}
defineExpose({ focus });

onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer);
});
</script>

<template>
  <div class="grid gap-1">
    <div class="relative">
      <Icon name="lucide:map-pin" class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
      <UiInput
        ref="inputRef"
        :model-value="modelValue"
        class="pl-9"
        autocomplete="off"
        role="combobox"
        :aria-expanded="listOpen"
        aria-label="Buscar endereço"
        :placeholder="isAvailable ? 'Rua e número, ou CEP' : 'Rua e número'"
        @update:model-value="onInput(String($event || ''))"
        @keydown="onKeydown"
        @blur="onBlur"
      />
      <Icon v-if="searching || resolving" name="lucide:loader-circle" class="absolute right-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-muted-foreground" />
      <!-- Sugestões DENTRO do modal (posição absoluta sob o campo) -->
      <ul
        v-if="listOpen && suggestions.length"
        class="absolute inset-x-0 top-full z-50 mt-1 max-h-64 overflow-y-auto rounded-md border bg-card p-1 shadow-md"
        role="listbox"
        aria-label="Sugestões de endereço"
      >
        <li v-for="(suggestion, idx) in suggestions" :key="suggestion.id" role="option" :aria-selected="idx === highlighted">
          <button
            type="button"
            class="flex w-full flex-col items-start gap-0.5 rounded-md px-2.5 py-2 text-left text-sm transition"
            :class="idx === highlighted ? 'bg-accent' : 'hover:bg-accent/60'"
            @pointerdown.prevent
            @click="accept(suggestion)"
            @pointerenter="highlighted = idx"
          >
            <span class="font-medium">{{ suggestion.main }}</span>
            <span v-if="suggestion.secondary" class="text-xs text-muted-foreground">{{ suggestion.secondary }}</span>
          </button>
        </li>
      </ul>
    </div>
    <p v-if="!isAvailable" class="text-xs text-muted-foreground">Digite o endereço manualmente, ou informe o CEP para preencher.</p>
    <p v-else-if="error" class="text-xs text-amber-700 dark:text-amber-400">{{ error }}</p>
  </div>
</template>
