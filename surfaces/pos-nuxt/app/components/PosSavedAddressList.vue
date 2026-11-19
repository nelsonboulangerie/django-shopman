<script setup lang="ts">
// OS ENDEREÇOS JÁ CADASTRADOS DO CLIENTE, um por linha inteira.
//
// Eram botõezinhos lado a lado com o rótulo cortado; num cliente vindo de pedido
// de entrega todos diziam "Entrega" e ninguém sabia qual era qual (pedido do
// dono, 19/11/2026, #2754). Agora cada endereço é uma opção de largura total que
// se identifica sozinha (`presentation/savedAddress`), o da entrega em edição já
// vem marcado, e o teclado resolve: as setas trocam de endereço e o Enter aceita
// e segue.
//
// A peça é o grupo de rádio do Nuxt UI (variante cartão): a seleção acompanha a
// seta e o Tab para uma vez só no grupo, no endereço marcado. Um Enter numa opção
// é do grupo de rádio do Reka, que o ignora de propósito; quem dá sentido a ele
// ("aceitar e seguir") é este componente, uma vez, para o assistente e para o
// diálogo de Recebimento.
import type { SavedAddressProjection } from "~/types/pos";
import { savedAddressOption } from "~/presentation/savedAddress";

const props = defineProps<{
  addresses: SavedAddressProjection[];
  /** O endereço da entrega em edição ("" quando não é nenhum dos cadastrados). */
  selected: string;
  disabled?: boolean;
}>();

const emit = defineEmits<{
  /** O operador escolheu este endereço para a entrega. */
  pick: [SavedAddressProjection];
  /** Enter no endereço: aceita e segue. */
  accept: [];
}>();

const options = computed(() => props.addresses.map(savedAddressOption));

function pick(value: unknown) {
  const address = props.addresses.find((item) => String(item.id) === String(value));
  if (address) emit("pick", address);
}

const root = useTemplateRef<HTMLElement>("root");
const radios = () => Array.from(root.value?.querySelectorAll<HTMLElement>('[role="radio"]') ?? []);

async function onEnter(event: KeyboardEvent) {
  if (event.isComposing || props.disabled) return;
  const index = radios().indexOf((event.target as HTMLElement | null)?.closest<HTMLElement>('[role="radio"]') as HTMLElement);
  const address = props.addresses[index];
  if (!address) return;
  event.preventDefault();
  event.stopPropagation();
  // Sem endereço marcado, o foco está no primeiro: o Enter escolhe e segue.
  if (String(address.id) !== props.selected) {
    emit("pick", address);
    await nextTick();
  }
  emit("accept");
}

/** Onde o foco do teclado deve cair: no endereço marcado, ou no primeiro. */
function focusTarget(): HTMLElement | null {
  const all = radios();
  return all.find((radio) => radio.getAttribute("aria-checked") === "true") ?? all[0] ?? null;
}
defineExpose({ focusTarget });
</script>

<template>
  <div ref="root" data-pos-saved-addresses @keydown.enter="onEnter">
    <NuxtRadioGroup
      :model-value="selected"
      :items="options"
      variant="card"
      legend="Endereços do cliente"
      :disabled="disabled"
      :ui="{ fieldset: 'w-full gap-y-2', item: 'w-full', wrapper: 'min-w-0', label: 'break-words', description: 'flex flex-wrap items-center gap-x-2 gap-y-1' }"
      @update:model-value="pick"
    >
      <!-- Duas linhas em toda opção, sempre no mesmo lugar: em cima o endereço;
           embaixo a etiqueta do cliente (quando identifica) e o bairro com a
           cidade. A etiqueta fica na segunda linha para a rua nunca dividir a
           largura com ela no celular. -->
      <template #label="{ item }">
        <span data-pos-saved-address-line>{{ item.label }}</span>
      </template>
      <template #description="{ item }">
        <NuxtBadge v-if="item.tag" color="neutral" :label="item.tag" data-pos-saved-address-tag />
        <span v-if="item.description" data-pos-saved-address-detail>{{ item.description }}</span>
      </template>
    </NuxtRadioGroup>
  </div>
</template>
