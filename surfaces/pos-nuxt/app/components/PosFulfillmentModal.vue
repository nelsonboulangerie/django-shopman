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
  /** Endereços que o cliente já usou — atalho para não redigitar. */
  savedAddresses: SavedAddressProjection[];
  addressAutocomplete: POSAddressAutocompleteProjection | null;
  deliveryAddress: string;
  deliveryStreetNumber: string;
  deliveryNeighborhood: string;
  deliveryComplement: string;
  deliveryInstructions: string;
  deliveryDate: string;
  /** A data que vale — a escolhida, ou o hoje que o servidor devolveu. */
  deliveryDateEffective: string;
  deliveryTimeSlot: string;
  /** Janelas de meia hora do expediente do dia escolhido. */
  deliverySlots: Array<{ ref: string; label: string }>;
  /** Ainda não há resposta sobre as janelas (a review está a caminho). */
  deliverySlotsPending: boolean;
  deliveryFeeOverride: boolean;
  deliveryFeeOverrideInput: string;
  /** A taxa RESOLVIDA pelo servidor, e de onde ela veio. */
  deliveryFeeQ: number;
  deliveryFeeSource: string;
  deliveryDistanceKm: number | null;
  orderNotes: string;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  "update:fulfillmentType": ["pickup" | "delivery"];
  "update:deliveryAddress": [string];
  "update:deliveryAddressStructured": [StructuredAddressProjection];
  "update:deliveryStreetNumber": [string];
  "update:deliveryNeighborhood": [string];
  "update:deliveryComplement": [string];
  "update:deliveryInstructions": [string];
  "update:deliveryDate": [string];
  "update:deliveryTimeSlot": [string];
  "update:deliveryFeeOverride": [boolean];
  "update:deliveryFeeOverrideInput": [string];
  "update:orderNotes": [string];
  pickSavedAddress: [SavedAddressProjection];
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

const slotPlaceholder = computed(() => {
  if (props.deliverySlots.length) return "A combinar";
  return props.deliverySlotsPending ? "Preencha o endereço" : "Sem janela neste dia";
});

// De onde a taxa saiu, em palavras. O operador precisa poder responder "por que
// deu isso?" sem abrir o Admin.
const deliveryFeeNote = computed(() => {
  if (props.deliveryFeeOverride) return "Valor combinado por você para esta entrega.";
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
      return "Preencha o endereço para a loja calcular a taxa.";
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
  <UiDialog v-model:open="isOpen">
    <UiDialogContent class="max-h-[85vh] overflow-y-auto sm:max-w-lg" @open-auto-focus="onOpenAutoFocus">
      <UiDialogHeader>
        <UiDialogTitle>Recebimento</UiDialogTitle>
        <UiDialogDescription>Como o cliente recebe o pedido.</UiDialogDescription>
      </UiDialogHeader>
      <div class="grid gap-4">
        <div class="grid grid-cols-2 gap-2">
          <UiButton
            v-for="option in fulfillmentOptions"
            :key="option.ref"
            variant="outline"
            class="h-auto justify-start whitespace-normal px-3 py-2 text-left"
            :class="fulfillmentType === option.ref ? 'border-primary bg-primary/5' : ''"
            @click="$emit('update:fulfillmentType', option.ref as 'pickup' | 'delivery')"
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
          <!-- QUANDO — data e janela. A data nasce em HOJE (o hoje do servidor,
               não o do tablet) e o horário deixa de ser texto solto: as janelas
               de meia hora vêm do EXPEDIENTE daquele dia. Digitar "14:00-14:30"
               num dia em que a casa fecha às 11h era uma promessa que ninguém
               podia cumprir, e a tela não tinha como saber. -->
          <div class="grid gap-2 sm:grid-cols-2">
            <label class="grid gap-1 text-sm">
              <span class="font-medium text-muted-foreground">Data</span>
              <UiInput
                :model-value="deliveryDateEffective"
                type="date"
                @update:model-value="$emit('update:deliveryDate', String($event || ''))"
              />
            </label>
            <label class="grid gap-1 text-sm">
              <span class="font-medium text-muted-foreground">Horário combinado</span>
              <select
                :value="deliveryTimeSlot"
                class="h-9 rounded-md border bg-background px-3 text-sm"
                :disabled="!deliverySlots.length"
                @change="$emit('update:deliveryTimeSlot', ($event.target as HTMLSelectElement).value)"
              >
                <option value="">{{ slotPlaceholder }}</option>
                <option v-for="slot in deliverySlots" :key="slot.ref" :value="slot.ref">{{ slot.label }}</option>
              </select>
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
              <strong class="tabular-nums">{{ deliveryFeeOverride ? "—" : formatBRL(deliveryFeeQ) }}</strong>
            </div>
            <p class="text-xs text-muted-foreground">{{ deliveryFeeNote }}</p>
            <button
              type="button"
              class="justify-self-start text-xs font-medium text-muted-foreground underline underline-offset-2 hover:text-foreground"
              @click="$emit('update:deliveryFeeOverride', !deliveryFeeOverride)"
            >
              {{ deliveryFeeOverride ? "Usar a taxa da loja" : "Combinar outro valor" }}
            </button>
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

        <!-- Observações do pedido valem para RETIRADA também (não só entrega):
             o dado sempre viajou no intent; só a tela o escondia. -->
        <label class="grid gap-1 text-sm">
          <span class="font-medium text-muted-foreground">Observações</span>
          <UiTextarea :model-value="orderNotes" :rows="2" placeholder="Instruções do pedido, referência, recado" @update:model-value="$emit('update:orderNotes', String($event || ''))" />
        </label>
      </div>
      <UiDialogFooter>
        <UiButton class="w-full" @click="isOpen = false">Concluir</UiButton>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
