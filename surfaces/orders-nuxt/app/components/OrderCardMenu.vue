<script setup lang="ts">
// O ⋯ de um pedido: atender, seleção em lote, declarar volumes, voltar para a estação
// e abrir o pedido. Uma peça só para o cartão do quadro e a linha da Grade (dono,
// 07/10/2026: as opções sumiam da Grade), para as duas nunca divergirem.
// É NuxtDropdownMenu, o ⋯ canônico; os volumes, que pedem um número, abrem um modal
// próprio (o editor não cabe dentro de um menu).
import type { OrderCardProjection } from "~/types/orders";
import { computed, ref } from "vue";
import { splitRef } from "~/presentation/board";
import { kitchenRecallOptions } from "~/presentation/kitchen";

const props = withDefaults(
  defineProps<{
    card: OrderCardProjection;
    busy?: boolean;
    canOpen?: boolean;
    selecting?: boolean;
    selected?: boolean;
  }>(),
  { canOpen: true },
);
const emit = defineEmits<{
  (e: "toggle-select" | "toggle-assign" | "select-mode"): void;
  (e: "station-recall" | "volumes", value: number): void;
}>();

const code = computed(() => splitRef(props.card.ref));
const recallOptions = computed(() => kitchenRecallOptions(props.card.kitchen));

// "Volumes": quem embalou diz quantas sacolas ou caixas saem (0 apaga). Só aparece
// quando o servidor oferece o gesto (ação "volumes"), com a mesma régua das outras.
const volumesAction = computed(
  () => props.card.actions.find((action) => action.ref === "volumes") ?? null,
);
const volumesOpen = ref(false);
const volumesDraft = ref(0);
function openVolumes() {
  volumesDraft.value =
    props.card.volumes ||
    Math.max(1, Math.min(props.card.items_count || 1, 99));
  volumesOpen.value = true;
}
function saveVolumes() {
  volumesOpen.value = false;
  emit("volumes", volumesDraft.value);
}

const items = computed(() => [
  ...(props.canOpen
    ? [
        {
          label: props.card.assigned_operator
            ? `Liberar (${props.card.assigned_operator} atende)`
            : "Atender este pedido",
          icon: props.card.assigned_operator
            ? "i-lucide-user-check"
            : "i-lucide-user-plus",
          "data-card-assign": "",
          onSelect: () => emit("toggle-assign"),
        },
      ]
    : []),
  {
    label: props.selecting
      ? props.selected
        ? "Desmarcar este pedido"
        : "Marcar este pedido"
      : "Selecionar vários",
    icon: "i-lucide-list-checks",
    "data-card-select-mode": "",
    onSelect: () =>
      props.selecting ? emit("toggle-select") : emit("select-mode"),
  },
  ...(volumesAction.value
    ? [
        {
          label: props.card.volumes
            ? `Volumes: ${props.card.volumes} (mudar)`
            : "Declarar volumes",
          icon: "i-lucide-package",
          "data-card-volumes": "",
          disabled: props.busy || !volumesAction.value.enabled,
          onSelect: openVolumes,
        },
      ]
    : []),
  ...recallOptions.value.map((option) => ({
    label: option.label,
    icon: "i-lucide-rotate-ccw",
    "data-card-recall": "",
    disabled: props.busy,
    onSelect: () => emit("station-recall", option.ticketPk),
  })),
  ...(props.canOpen
    ? [
        {
          label: "Abrir o pedido",
          icon: "i-lucide-file-text",
          to: `/${props.card.ref}`,
        },
      ]
    : []),
]);
</script>

<template>
  <NuxtDropdownMenu :items="items" :content="{ side: 'top', align: 'end' }">
    <NuxtButton
      color="neutral"
      variant="outline"
      square
      icon="i-lucide-ellipsis"
      :aria-label="`Mais ações do pedido ${code.code}`"
      data-card-menu
    />
  </NuxtDropdownMenu>
  <NuxtModal
    v-model:open="volumesOpen"
    :title="`Volumes do pedido ${code.code}`"
    description="Sacolas ou caixas, contadas por quem embalou."
    data-card-volumes-editor
  >
    <template #body>
      <NuxtFormField
        label="Quantos volumes saem?"
        :help="
          volumesDraft === 0
            ? 'Zero apaga: o cartão volta a contar itens.'
            : undefined
        "
      >
        <NuxtInputNumber
          v-model="volumesDraft"
          class="w-full"
          :min="0"
          :max="99"
          data-card-volumes-draft
          @keydown.enter="saveVolumes"
        />
      </NuxtFormField>
    </template>
    <template #footer>
      <div class="flex w-full justify-end gap-2">
        <NuxtButton
          label="Cancelar"
          color="neutral"
          variant="ghost"
          @click="volumesOpen = false"
        />
        <NuxtButton
          label="Gravar"
          color="primary"
          :disabled="busy"
          data-card-volumes-save
          @click="saveVolumes"
        />
      </div>
    </template>
  </NuxtModal>
</template>
