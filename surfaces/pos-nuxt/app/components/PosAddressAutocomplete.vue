<script setup lang="ts">
// "Buscar endereço ou CEP" do Recebimento: o MESMO passo da loja (AddressPicker):
// Places API (New) via AutocompleteSuggestion + ViaCEP quando a consulta parece
// CEP. É só a BUSCA: a sugestão escolhida preenche os campos do endereço, que
// moram abaixo dela (rua, número, complemento, bairro, CEP, cidade, UF). A lista de sugestões é
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
  /** Enter sem sugestão a escolher: o operador terminou este campo. */
  advance: [];
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
// A busca que não acha nada precisa DIZER (como na loja): sem isto a lista fecha,
// a tela fica igual, e o operador conclui que a casa não entrega ali.
const searchIssue = ref("");

let searchTimer: ReturnType<typeof setTimeout> | null = null;
let searchSeq = 0;
let sessionToken: unknown = null;
function onInput(value: string) {
  emit("update:modelValue", value);
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => void runSearch(value), 300);
}

async function runSearch(value: string) {
  const seq = ++searchSeq;
  const trimmed = value.trim();
  const isCep = looksLikeCep(trimmed);
  if (trimmed.length < 3 || (!isAvailable.value && !isCep)) {
    suggestions.value = [];
    listOpen.value = false;
    searchIssue.value = "";
    return;
  }
  searching.value = true;
  searchIssue.value = "";
  let results: AddressSuggestion[] = [];
  try {
    if (isAvailable.value) results = await placesSuggestions(trimmed);
    if (isCep && !results.length) {
      const cep = await viaCepSuggestion(trimmed);
      if (cep) results = [cep];
    }
  } finally {
    if (seq === searchSeq) {
      suggestions.value = results;
      highlighted.value = results.length ? 0 : -1;
      listOpen.value = results.length > 0;
      searchIssue.value = results.length || error.value
        ? ""
        : isCep
          ? "Não achamos esse CEP. Confira os números, ou preencha os campos abaixo."
          : "Nenhum endereço com esse nome. Tente a rua com o número, ou o CEP.";
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
    // Digitar à mão continua funcionando, e o CEP ainda busca pelo ViaCEP
    // (`runSearch` tenta os dois caminhos): a saída é real, não consolo.
    error.value = "A busca do Google não respondeu. Digite o CEP, ou preencha os campos abaixo.";
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
  // A busca cumpriu o papel: o endereço foi para os campos, e a caixa esvazia
  // para a próxima (como a loja, que troca a busca pelo formulário). A busca que
  // ainda estava a caminho não reabre a lista em cima do endereço escolhido.
  if (searchTimer) clearTimeout(searchTimer);
  searchSeq += 1;
  searching.value = false;
  emit("update:modelValue", "");
  searchIssue.value = "";
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
    error.value = "Não deu para abrir este endereço. Escolha outro da lista, ou preencha os campos abaixo.";
  } finally {
    resolving.value = false;
  }
}

// Enter com a lista FECHADA. Nada digitado: o operador segue para os campos. CEP:
// não espera a busca de 300 ms, busca já e, se resolveu, aceita o endereço (o pai
// leva o foco ao próximo campo vazio). Rua: busca já e abre a lista (como a loja).
// Sem a busca do Google, rua digitada aqui não tem onde ser procurada: segue
// para os campos.
async function onEnterWithoutList() {
  // O que está NO CAMPO, não a prop: digitar e dar Enter no mesmo instante chega
  // aqui antes de a prop voltar do pai.
  const value = (getInputElement()?.value ?? props.modelValue).trim();
  if (searchTimer) clearTimeout(searchTimer);
  if (looksLikeCep(value)) {
    await runSearch(value);
    const first = suggestions.value[0];
    if (first) await accept(first);
    return;
  }
  if (!value || !isAvailable.value) {
    emit("advance");
    return;
  }
  await runSearch(value);
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && event.isComposing) return;
  if (!listOpen.value || !suggestions.value.length) {
    if (event.key === "Enter") {
      event.preventDefault();
      void onEnterWithoutList();
    }
    return;
  }
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
      <NuxtInput
        ref="inputRef"
        data-focus-control
        :model-value="modelValue"
        class="w-full"
        icon="i-lucide-search"
        :loading="searching || resolving"
        trailing
        autocomplete="off"
        role="combobox"
        :aria-expanded="listOpen"
        aria-label="Buscar endereço ou CEP"
        :placeholder="isAvailable ? 'Rua, número ou CEP' : 'CEP'"
        @update:model-value="onInput(String($event || ''))"
        @keydown="onKeydown"
        @blur="onBlur"
      />
      <!-- Sugestões DENTRO do modal (posição absoluta sob o campo) -->
      <ul
        v-if="listOpen && suggestions.length"
        class="absolute inset-x-0 top-full z-50 mt-1 max-h-64 overflow-y-auto rounded-md bg-default p-1 shadow-md ring ring-default"
        role="listbox"
        aria-label="Sugestões de endereço"
      >
        <li v-for="(suggestion, idx) in suggestions" :key="suggestion.id" role="option" :aria-selected="idx === highlighted">
          <NuxtButton
            color="neutral"
            variant="ghost"
            class="justify-start flex w-full flex-col items-start gap-0.5 rounded-md px-2.5 py-2 text-left text-sm transition font-normal"
            :class="idx === highlighted ? 'bg-elevated' : ''"
            @pointerdown.prevent
            @click="accept(suggestion)"
            @pointerenter="highlighted = idx"
          >
            <span class="font-medium">{{ suggestion.main }}</span>
            <span v-if="suggestion.secondary" class="text-xs text-muted">{{ suggestion.secondary }}</span>
          </NuxtButton>
        </li>
      </ul>
    </div>
    <p v-if="searchIssue" class="text-xs text-error" role="alert" data-pos-address-search-issue>{{ searchIssue }}</p>
    <p v-else-if="!isAvailable" class="text-xs text-muted">Digite o CEP para preencher, ou preencha os campos abaixo.</p>
    <p v-else-if="error" class="text-xs text-warning">{{ error }}</p>
  </div>
</template>
