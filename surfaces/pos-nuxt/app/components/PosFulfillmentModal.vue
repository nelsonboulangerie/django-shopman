<script setup lang="ts">
// RECEBIMENTO — "como o cliente recebe o pedido": retirada ou entrega, e, sendo
// entrega, onde, quando e quanto.
//
// Morava dentro do PosPaymentWorkspace, e ali só podia ser perguntado no fim,
// na hora de pagar. Mas recebimento é fato do PEDIDO, não do pagamento: entrega
// acrescenta taxa, muda as janelas de horário e depende de um endereço que
// alguém precisa digitar. Perguntado no fim, o total dá um pulo na última tela e
// o operador reexplica a conta com o cliente na frente.
//
// Extraído para poder ser feito no COMEÇO do atendimento (abertura da comanda) e
// revisto no checkout — a mesma caixa, as mesmas palavras, nos dois lugares.
// Continua sendo tela: não resolve taxa nem janela, mostra o que o servidor
// resolveu.
import type {
  POSAddressAutocompleteProjection,
  POSDeliveryFeeWaiverProjection,
  POSFulfillmentOptionProjection,
  SavedAddressProjection,
  StructuredAddressProjection,
} from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";
import { deliveryFeeWaivedInFull, deliveryFeeWaiverNote } from "~/presentation/deliveryFeeWaiver";
import {
  BR_STATES,
  DRAFT_FIELD_OF,
  addressDraftErrors,
  deliveryValuesFromDraft,
  draftFromDeliveryState,
  draftSummaryLine,
  emptyAddressDraft,
  firstInvalidField,
  maskCepInput,
  mergeConfirmedPoint,
  nextEmptyAddressField,
  structuredFromDraft,
  type AddressDraft,
  type AddressPoint,
  type DeliveryAddressField,
} from "~/presentation/address";

const props = defineProps<{
  open: boolean;
  fulfillmentOptions: POSFulfillmentOptionProjection[];
  fulfillmentType: "pickup" | "delivery";
  fulfillmentConfirmed?: boolean;
  /** Endereços que o cliente já usou — atalho para não redigitar. */
  savedAddresses: SavedAddressProjection[];
  addressAutocomplete: POSAddressAutocompleteProjection | null;
  /** O endereço estruturado (CEP, cidade, UF, ponto) que acompanha os campos. */
  deliveryAddressStructured?: StructuredAddressProjection;
  deliveryAddress: string;
  deliveryStreetNumber: string;
  deliveryNeighborhood: string;
  deliveryComplement: string;
  deliveryInstructions: string;
  /** O resumo do "quando", só para o atalho se explicar. */
  scheduleLabel: string;
  deliveryFeeOverride: boolean;
  deliveryFeeOverrideInput: string;
  /** A taxa RESOLVIDA pelo servidor, e de onde ela veio. */
  deliveryFeeQ: number;
  deliveryFeeSource: string;
  /** Frete grátis (ou abatido) pela loja, e por qual regra. Opcional: sem ele, nada a dizer. */
  deliveryFeeWaiver?: POSDeliveryFeeWaiverProjection | null;
  /**
   * Em que pé está a taxa. `resolved`: a review respondeu (e `deliveryFeeSource`
   * diz de onde veio). `calculating`: a review está a caminho. `failed`: a review
   * falhou. `at_payment`: fora do pagamento a review não roda — a taxa só é
   * calculada lá. Sem ela, R$ 0,00 + "Preencha o endereço" aparecia com o
   * endereço preenchido, e as duas coisas eram falsas.
   */
  deliveryFeeStatus?: "resolved" | "calculating" | "failed" | "at_payment";
  deliveryDistanceKm: number | null;
  orderNotes: string;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  "update:fulfillmentType": ["pickup" | "delivery"];
  "update:fulfillmentConfirmed": [boolean];
  "update:deliveryAddress": [string];
  "update:deliveryAddressStructured": [StructuredAddressProjection];
  "update:deliveryStreetNumber": [string];
  "update:deliveryNeighborhood": [string];
  "update:deliveryComplement": [string];
  "update:deliveryInstructions": [string];
  "update:deliveryFeeOverride": [boolean];
  "update:deliveryFeeOverrideInput": [string];
  "update:orderNotes": [string];
  pickSavedAddress: [SavedAddressProjection];
  openSchedule: [];
}>();

const isOpen = computed({
  get: () => props.open,
  set: (value: boolean) => emit("update:open", value),
});

// Foco automático: com entrega selecionada, quem recebe o foco é a busca de
// endereço — o passo que o operador veio dar. Tanto na abertura quanto ao
// alternar retirada→entrega com o diálogo já aberto.
const addressAutocompleteRef = ref<{ focus: () => void } | null>(null);
const searchQuery = ref("");
function onOpenAutoFocus(event: Event) {
  if (props.fulfillmentType !== "delivery") return; // retirada: foco padrão do diálogo
  event.preventDefault();
  void nextTick(() => addressAutocompleteRef.value?.focus());
}
watch(() => props.fulfillmentType, async (type) => {
  if (!props.open || type !== "delivery" || !import.meta.client) return;
  await nextTick();
  addressAutocompleteRef.value?.focus();
});

// De onde a taxa saiu, em palavras. O operador precisa poder responder "por que
// deu isso?" sem abrir o Admin.
const hasAddress = computed(() => Boolean(props.deliveryAddress.trim() || props.deliveryNeighborhood.trim()));
/** A taxa na tela é um número que a loja calculou — senão, travessão. */
const deliveryFeeKnown = computed(() =>
  !props.deliveryFeeOverride
  && hasAddress.value
  && (props.deliveryFeeStatus ?? "resolved") === "resolved"
  && Boolean(props.deliveryFeeSource)
  && props.deliveryFeeSource !== "blocked",
);
const deliveryFeeNote = computed(() => {
  if (props.deliveryFeeOverride) return "Valor combinado por você para esta entrega.";
  if (!hasAddress.value) return "Preencha o endereço para a loja calcular a taxa.";
  switch (props.deliveryFeeStatus ?? "resolved") {
    case "at_payment":
      return "A taxa deste endereço é calculada no pagamento.";
    case "calculating":
      return "Calculando a taxa deste endereço…";
    case "failed":
      return "Não deu para calcular a taxa agora. Combine o valor com o cliente.";
  }
  const km = props.deliveryDistanceKm;
  switch (props.deliveryFeeSource) {
    case "zone":
      return "Tabela do bairro/CEP deste endereço.";
    case "distance":
      return km == null ? "Pela distância até o endereço." : `Pela distância até o endereço (${km} km).`;
    case "default":
      return "Taxa padrão da loja: não deu para medir a distância deste endereço.";
    case "blocked":
      return "Fora da área de entrega. Para entregar, combine o valor com o cliente.";
    case "manual":
      return "Valor combinado para esta entrega.";
    default:
      // A review respondeu e não achou zona, bairro nem distância para este
      // endereço: a taxa não foi calculada — não é grátis.
      return "Não deu para calcular a taxa deste endereço. Confira o CEP e o bairro, ou combine o valor.";
  }
});
// Frete grátis (ou abatido) pela loja: a regra pelo nome, e a taxa que seria.
// Só quando a taxa é a da loja: com a combinada à mão, a promoção não entra.
const deliveryFeeWaiverLine = computed(() =>
  deliveryFeeKnown.value ? deliveryFeeWaiverNote(props.deliveryFeeWaiver, props.deliveryFeeQ) : "",
);
const deliveryFeeAmount = computed(() => {
  if (!deliveryFeeKnown.value) return "—";
  return deliveryFeeWaivedInFull(props.deliveryFeeWaiver, props.deliveryFeeQ) ? "Grátis" : formatBRL(props.deliveryFeeQ);
});

// O ENDEREÇO DE ENTREGA É O DA LOJA ONLINE (decisão do dono, 13/10/2026): os
// mesmos passos (buscar por CEP ou endereço, escolher a sugestão, confirmar o ponto
// no mapa quando a loja faz isso, completar número, complemento e referência), os
// mesmos campos e a mesma régua de "endereço completo". A regra mora no módulo
// gêmeo `presentation/addressForm.ts`, byte a byte igual ao do storefront.
//
// O que é do balcão fica do balcão: os campos estão sempre à vista (o operador
// preenche enquanto o cliente dita, sem trocar de tela), e o ENTER LEVA AO
// PRÓXIMO CAMPO VAZIO, pulando o que a busca já trouxe; sem campo vazio adiante,
// o Enter confirma o recebimento pelo mesmo caminho do botão. O foco anda pelo
// mecanismo da suíte (`useNextFocus().reveal`), nunca por scroll avulso.
const { reveal } = useNextFocus();
const fieldKey = (field: DeliveryAddressField | "search") => `delivery-${field}`;
const isDelivery = computed(() => props.fulfillmentType === "delivery");

const draft = computed<AddressDraft>(() => draftFromDeliveryState({
  route: props.deliveryAddress,
  streetNumber: props.deliveryStreetNumber,
  neighborhood: props.deliveryNeighborhood,
  complement: props.deliveryComplement,
  instructions: props.deliveryInstructions,
  structured: props.deliveryAddressStructured || {},
}));
const summaryLine = computed(() => (draft.value.route.trim() ? draftSummaryLine(draft.value) : ""));
const stateItems = BR_STATES.map((uf) => ({ label: uf, value: uf }));

// Erros da validação, por campo da tela. Só aparecem depois da primeira tentativa
// de confirmar, e cada campo corrigido apaga o seu (como na loja).
const fieldErrors = ref<Partial<Record<DeliveryAddressField, string>>>({});
/** As mensagens de uma linha de campos, numa frase só. */
function rowError(fields: DeliveryAddressField[]): string {
  return fields.map((field) => fieldErrors.value[field]).filter(Boolean).join(" ");
}
function errorsByField(errors: Record<string, string>) {
  const byField: Partial<Record<DeliveryAddressField, string>> = {};
  for (const [key, message] of Object.entries(errors)) {
    const field = DRAFT_FIELD_OF[key];
    if (field) byField[field] = message;
  }
  return byField;
}

/** Escreve um rascunho inteiro de volta no carrinho (campos + estruturado). */
function emitDraft(next: AddressDraft) {
  emit("update:deliveryAddressStructured", structuredFromDraft(next, props.deliveryAddressStructured || {}));
  emit("update:deliveryAddress", next.route);
  emit("update:deliveryStreetNumber", next.street_number);
  emit("update:deliveryNeighborhood", next.neighborhood);
  emit("update:deliveryComplement", next.complement);
  emit("update:deliveryInstructions", next.delivery_instructions);
}

function setField(field: DeliveryAddressField, raw: unknown) {
  const value = String(raw ?? "");
  if (fieldErrors.value[field]) {
    fieldErrors.value = Object.fromEntries(
      Object.entries(fieldErrors.value).filter(([key]) => key !== field),
    );
  }
  switch (field) {
    case "route": emit("update:deliveryAddress", value); return;
    case "number": emit("update:deliveryStreetNumber", value); return;
    case "neighborhood": emit("update:deliveryNeighborhood", value); return;
    case "complement": emit("update:deliveryComplement", value); return;
    case "instructions": emit("update:deliveryInstructions", value); return;
  }
  const structured = { ...(props.deliveryAddressStructured || {}) };
  if (field === "postal_code") structured.postal_code = maskCepInput(value);
  if (field === "city") structured.city = value;
  if (field === "state") structured.state_code = value.trim().toUpperCase();
  emit("update:deliveryAddressStructured", structured);
}

/** Confirma o recebimento; na entrega, só com o endereço completo. */
function confirmFulfillment() {
  if (!props.fulfillmentConfirmed) return;
  if (isDelivery.value) {
    const errors = addressDraftErrors(draft.value);
    fieldErrors.value = errorsByField(errors);
    const first = firstInvalidField(errors);
    if (first) {
      reveal(fieldKey(first), { align: "center" });
      return;
    }
  }
  isOpen.value = false;
}

function goPast(after: DeliveryAddressField | null, values = deliveryValuesFromDraft(draft.value)) {
  const next = nextEmptyAddressField(after, values);
  if (next) {
    reveal(fieldKey(next), { align: "center" });
    return;
  }
  confirmFulfillment();
}

function onFieldEnter(field: DeliveryAddressField, event: KeyboardEvent) {
  if (event.isComposing) return;
  event.preventDefault();
  goPast(field);
}

function onStatePicked(value: unknown) {
  setField("state", value);
  const values = { ...deliveryValuesFromDraft(draft.value), state: String(value ?? "") };
  void nextTick(() => goPast("state", values));
}

// ── Sugestão escolhida (CEP ou Google) ────────────────────────────────

/**
 * A sugestão SUBSTITUI o lugar (rua, número, bairro, CEP, cidade, UF, ponto),
 * como na loja; complemento e instruções são de quem dita o endereço e ficam.
 */
function draftWithPlace(address: StructuredAddressProjection): AddressDraft {
  const hasPoint = address.latitude != null && address.longitude != null;
  return {
    ...emptyAddressDraft(),
    formatted_address: address.formatted_address || "",
    route: address.route || "",
    street_number: address.street_number || "",
    neighborhood: address.neighborhood || "",
    city: address.city || "",
    state_code: address.state_code || "",
    postal_code: maskCepInput(address.postal_code || ""),
    latitude: address.latitude ?? null,
    longitude: address.longitude ?? null,
    place_id: address.place_id || "",
    coordinates_source: hasPoint ? "geocoded" : null,
    complement: props.deliveryComplement,
    delivery_instructions: props.deliveryInstructions,
  };
}

function applyDraft(next: AddressDraft) {
  emitDraft(next);
  fieldErrors.value = {};
  // A busca acabou de preencher: o próximo campo vazio desde o começo. As props
  // ainda não refletem os emits deste instante: os valores novos entram por cima.
  goPast(null, deliveryValuesFromDraft(next));
}

const capabilityRef = computed(() => props.addressAutocomplete);
const { isAvailable: mapsAvailable } = usePosGoogleMaps(capabilityRef);
const canAdjustOnMap = computed(() => mapsAvailable.value && draft.value.latitude != null && draft.value.longitude != null);

function onAddressSelected(address: StructuredAddressProjection) {
  const next = draftWithPlace(address);
  const confirmOnMap = Boolean(props.addressAutocomplete?.map_confirmation_enabled)
    && mapsAvailable.value
    && next.latitude != null
    && next.longitude != null;
  if (confirmOnMap) {
    openMap("confirm", next);
    return;
  }
  applyDraft(next);
}

// ── Ponto no mapa ─────────────────────────────────────────────────────

const mapOpen = ref(false);
const mapPurpose = ref<"confirm" | "adjust">("adjust");
/** O endereço em jogo no mapa: a sugestão pendente ("É aqui?") ou o atual. */
const mapDraft = ref<AddressDraft | null>(null);
const mapBusy = ref(false);
const mapIssue = ref("");
const mapPoint = computed<AddressPoint | null>(() => {
  const target = mapDraft.value;
  if (!target || target.latitude == null || target.longitude == null) return null;
  return { lat: target.latitude, lng: target.longitude };
});
const mapSummary = computed(() => (mapDraft.value ? draftSummaryLine(mapDraft.value) : ""));

function openMap(purpose: "confirm" | "adjust", target: AddressDraft = draft.value) {
  mapPurpose.value = purpose;
  mapDraft.value = { ...target };
  mapIssue.value = "";
  mapOpen.value = true;
}

const action = usePosAction();
async function onMapConfirm({ point, moved }: { point: AddressPoint; moved: boolean }) {
  const target = mapDraft.value;
  if (!target) return;
  mapBusy.value = true;
  mapIssue.value = "";
  try {
    // O servidor descreve o ponto só quando ele MEXEU: o do Google já veio descrito.
    const reverse = moved
      ? await action.call<StructuredAddressProjection>("/api/v1/geocode/reverse/", {
        method: "POST",
        body: { lat: point.lat, lng: point.lng },
      })
      : null;
    const source = mapPurpose.value === "confirm" && !moved ? "geocoded" : "pin";
    const confirmed = mergeConfirmedPoint(target, reverse, point, source);
    mapOpen.value = false;
    mapDraft.value = null;
    applyDraft(confirmed);
  } catch (error) {
    mapIssue.value = httpErrorMessage(error, "Não deu para confirmar o ponto. Tente de novo.");
  } finally {
    mapBusy.value = false;
  }
}

function onMapCancel() {
  // "Voltar" do "É aqui?": a sugestão não vale; a busca volta para outra tentativa.
  // "Voltar" do ajuste: nada mudou, e o foco volta ao botão que abriu o mapa.
  const wasConfirming = mapPurpose.value === "confirm";
  mapDraft.value = null;
  if (wasConfirming) reveal(fieldKey("search"), { align: "center" });
  else reveal(() => document.querySelector("[data-pos-address-adjust-map]"), { align: "center" });
}
</script>

<template>
  <NuxtModal
    v-model:open="isOpen"
    title="Recebimento"
    description="Escolha uma opção. Cliente e data não definem como o pedido será recebido."
    :content="{ onOpenAutoFocus }"
    :ui="{ content: 'sm:max-w-lg' }"
    data-pos-fulfillment-modal
  >
    <template #body>
      <div class="grid gap-4">
        <div class="grid grid-cols-2 gap-2">
          <UiButton
            v-for="option in fulfillmentOptions"
            :key="option.ref"
            variant="outline"
            class="h-auto justify-start whitespace-normal px-3 py-2 text-left"
            :class="fulfillmentConfirmed && fulfillmentType === option.ref ? 'border-primary bg-primary/5' : ''"
            @click="$emit('update:fulfillmentType', option.ref as 'pickup' | 'delivery'); $emit('update:fulfillmentConfirmed', true)"
            :aria-pressed="!!fulfillmentConfirmed && fulfillmentType === option.ref"
          >
            <span>
              <span class="block text-sm font-semibold">{{ option.label }}</span>
              <span class="block text-xs opacity-80">{{ option.description }}</span>
            </span>
          </UiButton>
        </div>

        <div v-if="fulfillmentType === 'delivery'" class="grid gap-3">
          <div v-if="savedAddresses.length" class="flex flex-wrap gap-2">
            <UiButton
              v-for="address in savedAddresses"
              :key="address.id"
              type="button"
              variant="outline"
              size="sm"
              class="h-auto justify-start whitespace-normal px-2 py-1 text-left"
              @click="$emit('pickSavedAddress', address)"
            >
              <span class="max-w-48 truncate">{{ address.label || address.formatted_address }}</span>
            </UiButton>
          </div>
          <!-- OS PASSOS DA LOJA: buscar (CEP ou endereço) → a sugestão preenche
               os campos → número, complemento, referência. Cada campo é um bloco
               do próximo foco (`data-focus-target`), e o Enter anda para o
               próximo VAZIO (`onFieldEnter`). A grade é a mesma do site. -->
          <NuxtFormField label="Buscar endereço ou CEP" :data-focus-target="fieldKey('search')">
            <PosAddressAutocomplete
              ref="addressAutocompleteRef"
              v-model="searchQuery"
              :capability="addressAutocomplete"
              @selected="onAddressSelected"
              @advance="goPast(null)"
            />
          </NuxtFormField>
          <div v-if="summaryLine" class="flex flex-wrap items-center gap-x-2 gap-y-1" data-pos-address-summary>
            <Icon name="lucide:map-pin" class="size-4 shrink-0 text-muted" aria-hidden="true" />
            <p class="min-w-0 flex-1 text-sm font-semibold">{{ summaryLine }}</p>
            <NuxtButton
              v-if="canAdjustOnMap"
              color="neutral"
              variant="ghost"
              icon="i-lucide-map"
              label="Ajustar no mapa"
              data-pos-address-adjust-map
              @click="openMap('adjust')"
            />
          </div>
          <NuxtFormField label="Rua" :error="fieldErrors.route" :data-focus-target="fieldKey('route')">
            <NuxtInput data-focus-control class="w-full" autocomplete="off" :model-value="deliveryAddress" @update:model-value="setField('route', $event)" @keydown.enter="onFieldEnter('route', $event)" />
          </NuxtFormField>
          <!-- Nas linhas de dois campos o erro sai numa linha só, sob a linha: na
               coluna estreita do número ele quebrava em três. -->
          <div class="grid gap-2">
            <div class="grid grid-cols-[7rem_minmax(0,1fr)] gap-3">
              <NuxtFormField label="Número" :error="Boolean(fieldErrors.number)" :data-focus-target="fieldKey('number')">
                <NuxtInput data-focus-control class="w-full" autocomplete="off" :model-value="deliveryStreetNumber" @update:model-value="setField('number', $event)" @keydown.enter="onFieldEnter('number', $event)" />
              </NuxtFormField>
              <NuxtFormField label="Complemento" :data-focus-target="fieldKey('complement')">
                <NuxtInput data-focus-control class="w-full" autocomplete="off" placeholder="Apto, bloco, referência" :model-value="deliveryComplement" @update:model-value="setField('complement', $event)" @keydown.enter="onFieldEnter('complement', $event)" />
              </NuxtFormField>
            </div>
            <p v-if="rowError(['number'])" class="text-sm text-error" data-pos-address-row-error>{{ rowError(['number']) }}</p>
          </div>
          <div class="grid gap-2">
            <div class="grid grid-cols-[minmax(0,1fr)_8rem] gap-3">
              <NuxtFormField label="Bairro" :error="Boolean(fieldErrors.neighborhood)" :data-focus-target="fieldKey('neighborhood')">
                <NuxtInput data-focus-control class="w-full" autocomplete="off" :model-value="deliveryNeighborhood" @update:model-value="setField('neighborhood', $event)" @keydown.enter="onFieldEnter('neighborhood', $event)" />
              </NuxtFormField>
              <NuxtFormField label="CEP" :error="Boolean(fieldErrors.postal_code)" :data-focus-target="fieldKey('postal_code')">
                <NuxtInput data-focus-control class="w-full" autocomplete="off" inputmode="numeric" placeholder="00000-000" :model-value="draft.postal_code" @update:model-value="setField('postal_code', $event)" @keydown.enter="onFieldEnter('postal_code', $event)" />
              </NuxtFormField>
            </div>
            <p v-if="rowError(['neighborhood', 'postal_code'])" class="text-sm text-error" data-pos-address-row-error>{{ rowError(['neighborhood', 'postal_code']) }}</p>
          </div>
          <div class="grid gap-2">
            <div class="grid grid-cols-[minmax(0,1fr)_6rem] gap-3">
              <NuxtFormField label="Cidade" :error="Boolean(fieldErrors.city)" :data-focus-target="fieldKey('city')">
                <NuxtInput data-focus-control class="w-full" autocomplete="off" :model-value="draft.city" @update:model-value="setField('city', $event)" @keydown.enter="onFieldEnter('city', $event)" />
              </NuxtFormField>
              <NuxtFormField label="UF" :error="Boolean(fieldErrors.state)" :data-focus-target="fieldKey('state')">
                <NuxtSelect
                  data-focus-control
                  class="w-full"
                  aria-label="UF"
                  :items="stateItems"
                  :model-value="draft.state_code || undefined"
                  @update:model-value="onStatePicked"
                />
              </NuxtFormField>
            </div>
            <p v-if="rowError(['city', 'state'])" class="text-sm text-error" data-pos-address-row-error>{{ rowError(['city', 'state']) }}</p>
          </div>
          <NuxtFormField label="Instruções de entrega" :data-focus-target="fieldKey('instructions')">
            <NuxtInput data-focus-control class="w-full" autocomplete="off" placeholder="Portaria, interfone, melhor acesso" :model-value="deliveryInstructions" @update:model-value="setField('instructions', $event)" @keydown.enter="onFieldEnter('instructions', $event)" />
          </NuxtFormField>
          <!-- QUANTO — a taxa é RESOLVIDA pelo endereço (zona de CEP, faixa de
               distância, frete grátis por valor), o mesmo motor da loja. Era um
               campo livre, e campo livre é um segundo dono do preço: duas vendas
               do mesmo endereço saíam diferentes conforme quem estava no caixa.
               A digitação continua existindo como EXCEÇÃO declarada. -->
          <div class="grid gap-1.5 rounded-md border bg-card p-3 text-sm">
            <div class="flex items-center justify-between gap-2">
              <span class="font-medium text-muted-foreground">Taxa de entrega</span>
              <strong class="tabular-nums" data-pos-delivery-fee-amount>{{ deliveryFeeAmount }}</strong>
            </div>
            <p class="text-xs text-muted-foreground">{{ deliveryFeeNote }}</p>
            <p v-if="deliveryFeeWaiverLine" class="text-xs text-primary" data-pos-delivery-fee-waiver>{{ deliveryFeeWaiverLine }}</p>
            <NuxtButton
              color="neutral"
              variant="ghost"
              class="justify-self-start"
              :label="deliveryFeeOverride ? 'Usar a taxa da loja' : 'Combinar outro valor'"
              @click="$emit('update:deliveryFeeOverride', !deliveryFeeOverride)"
            />
            <UiInput
              v-if="deliveryFeeOverride"
              :model-value="deliveryFeeOverrideInput"
              inputmode="decimal"
              placeholder="0,00"
              aria-label="Taxa combinada com o cliente"
              @update:model-value="$emit('update:deliveryFeeOverrideInput', String($event || ''))"
            />
          </div>
        </div>

        <!-- QUANDO saiu deste formulário, e essa é a mudança. Data e janela
             viraram a terceira caixa da barra de contexto (PosScheduleModal),
             porque *quando* é fato do PEDIDO e não da entrega: presas dentro do
             bloco de entrega, elas simplesmente NÃO EXISTIAM na retirada, e a
             encomenda por telefone para retirar na quinta não tinha onde ser
             escrita. O atalho fica FORA do bloco de entrega pela mesma razão. -->
        <NuxtButton
          color="neutral"
          variant="outline"
          trailing-icon="i-lucide-chevron-right"
          class="justify-between gap-2 px-3 py-2 text-left font-normal"
          @click="$emit('openSchedule')"
        >
          <span>
            <span class="block font-medium text-muted-foreground">Quando</span>
            <span class="block text-xs opacity-80">{{ scheduleLabel }}</span>
          </span>
        </NuxtButton>

        <!-- Observações do pedido valem para RETIRADA também (não só entrega):
             o dado sempre viajou no intent; só a tela o escondia. -->
        <label class="grid gap-1 text-sm">
          <span class="font-medium text-muted-foreground">Observações</span>
          <UiTextarea :model-value="orderNotes" :rows="2" placeholder="Instruções do pedido, referência, recado" @update:model-value="$emit('update:orderNotes', String($event || ''))" />
        </label>
      </div>
      <PosAddressMapDialog
        v-model:open="mapOpen"
        :capability="addressAutocomplete"
        :point="mapPoint"
        :purpose="mapPurpose"
        :summary="mapSummary"
        :busy="mapBusy"
        :issue="mapIssue"
        @confirm="onMapConfirm"
        @cancel="onMapCancel"
      />
    </template>
    <template #footer>
      <!-- ⚠️ O rodapé confirma a ESCOLHA, não o desfecho: aqui só se decide
           COMO o pedido será recebido, antes de qualquer coisa acontecer.
           "Concluir entrega" é ato real desta casa (é o que o Gestor de
           Pedidos faz quando o pedido chegou na mão de alguém), e numa
           encomenda para sábado o rótulo afirmava que a entrega tinha
           terminado no instante em que foi combinada. -->
      <NuxtButton
        block
        color="primary"
        :disabled="!fulfillmentConfirmed"
        :label="!fulfillmentConfirmed ? 'Escolha o recebimento' : fulfillmentType === 'delivery' ? 'Entrega neste endereço' : 'Retirada no balcão'"
        data-pos-fulfillment-confirm
        @click="confirmFulfillment"
      />
    </template>
  </NuxtModal>
</template>
