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
  POSFulfillmentOptionProjection,
  SavedAddressProjection,
  StructuredAddressProjection,
} from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";

const props = defineProps<{
  open: boolean;
  fulfillmentOptions: POSFulfillmentOptionProjection[];
  fulfillmentType: "pickup" | "delivery";
  fulfillmentConfirmed?: boolean;
  /** Endereços que o cliente já usou — atalho para não redigitar. */
  savedAddresses: SavedAddressProjection[];
  addressAutocomplete: POSAddressAutocompleteProjection | null;
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
// endereço — o campo que o operador veio preencher. Tanto na abertura quanto ao
// alternar retirada→entrega com o diálogo já aberto.
const addressAutocompleteRef = ref<{ focus: () => void } | null>(null);
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
      return "Este endereço está fora da área de entrega.";
    case "manual":
      return "Valor combinado para esta entrega.";
    default:
      // A review respondeu e não achou zona, bairro nem distância para este
      // endereço: a taxa não foi calculada — não é grátis.
      return "Não deu para calcular a taxa deste endereço. Confira o CEP e o bairro, ou combine o valor.";
  }
});

function onAddressSelected(address: StructuredAddressProjection) {
  emit("update:deliveryAddressStructured", address);
  if (address.route) emit("update:deliveryAddress", address.route);
  if (address.street_number) emit("update:deliveryStreetNumber", address.street_number);
  if (address.neighborhood) emit("update:deliveryNeighborhood", address.neighborhood);
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
          <label class="grid gap-1 text-sm">
            <span class="font-medium text-muted-foreground">Endereço</span>
            <PosAddressAutocomplete
              ref="addressAutocompleteRef"
              :model-value="deliveryAddress"
              :capability="addressAutocomplete"
              @update:model-value="$emit('update:deliveryAddress', String($event || ''))"
              @selected="onAddressSelected"
            />
          </label>
          <div class="grid gap-2 sm:grid-cols-2">
            <label class="grid gap-1 text-sm">
              <span class="font-medium text-muted-foreground">Número</span>
              <UiInput :model-value="deliveryStreetNumber" placeholder="123" @update:model-value="$emit('update:deliveryStreetNumber', String($event || ''))" />
            </label>
            <label class="grid gap-1 text-sm">
              <span class="font-medium text-muted-foreground">Bairro</span>
              <UiInput :model-value="deliveryNeighborhood" placeholder="Centro" @update:model-value="$emit('update:deliveryNeighborhood', String($event || ''))" />
            </label>
          </div>
          <div class="grid gap-2 sm:grid-cols-2">
            <label class="grid gap-1 text-sm">
              <span class="font-medium text-muted-foreground">Complemento</span>
              <UiInput :model-value="deliveryComplement" placeholder="Apto, bloco" @update:model-value="$emit('update:deliveryComplement', String($event || ''))" />
            </label>
            <label class="grid gap-1 text-sm">
              <span class="font-medium text-muted-foreground">Instruções</span>
              <UiInput :model-value="deliveryInstructions" placeholder="Portaria, referência" @update:model-value="$emit('update:deliveryInstructions', String($event || ''))" />
            </label>
          </div>
          <!-- QUANTO — a taxa é RESOLVIDA pelo endereço (zona de CEP, faixa de
               distância, frete grátis por valor), o mesmo motor da loja. Era um
               campo livre, e campo livre é um segundo dono do preço: duas vendas
               do mesmo endereço saíam diferentes conforme quem estava no caixa.
               A digitação continua existindo como EXCEÇÃO declarada. -->
          <div class="grid gap-1.5 rounded-md border bg-card p-3 text-sm">
            <div class="flex items-center justify-between gap-2">
              <span class="font-medium text-muted-foreground">Taxa de entrega</span>
              <strong class="tabular-nums">{{ deliveryFeeKnown ? formatBRL(deliveryFeeQ) : "—" }}</strong>
            </div>
            <p class="text-xs text-muted-foreground">{{ deliveryFeeNote }}</p>
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
        @click="isOpen = false"
      />
    </template>
  </NuxtModal>
</template>
