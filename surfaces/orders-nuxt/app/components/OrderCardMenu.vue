<script setup lang="ts">
// O ⋯ de um pedido: atender, seleção em lote, declarar volumes, voltar para a estação
// e abrir o pedido. Uma peça só para o cartão do quadro e a linha da Grade (dono,
// 07/10/2026: as opções sumiam da Grade), para as duas nunca divergirem.
import type { OrderCardProjection } from "~/types/orders";
import { computed, ref, watch } from "vue";
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
const open = ref(false);
const volumesEditing = ref(false);
const volumesDraft = ref(0);
watch(open, (isOpen) => {
  if (!isOpen) volumesEditing.value = false;
});
function openVolumes() {
  volumesDraft.value =
    props.card.volumes ||
    Math.max(1, Math.min(props.card.items_count || 1, 99));
  volumesEditing.value = true;
}
function saveVolumes() {
  open.value = false;
  volumesEditing.value = false;
  emit("volumes", volumesDraft.value);
}
function pick(fn: () => void) {
  open.value = false;
  fn();
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
          onSelect: () => pick(() => emit("toggle-assign")),
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
      pick(() =>
        props.selecting ? emit("toggle-select") : emit("select-mode"),
      ),
  },
  ...(!volumesEditing.value && volumesAction.value
    ? [
        {
          label: props.card.volumes
            ? `Volumes: ${props.card.volumes} (mudar)`
            : "Declarar volumes",
          icon: "i-lucide-package",
          "data-card-volumes": "",
          disabled: props.busy || !volumesAction.value.enabled,
          onSelect: (event: Event) => {
            event.preventDefault();
            openVolumes();
          },
        },
      ]
    : []),
  ...recallOptions.value.map((option) => ({
    label: option.label,
    icon: "i-lucide-rotate-ccw",
    "data-card-recall": "",
    disabled: props.busy,
    onSelect: () => pick(() => emit("station-recall", option.ticketPk)),
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
  <NuxtPopover
    v-model:open="open"
    :content="{ side: 'top', align: 'end', sideOffset: 4 }"
  >
    <NuxtButton
      color="neutral"
      variant="outline"
      square
      icon="i-lucide-ellipsis"
      :aria-label="`Mais ações do pedido ${code.code}`"
      data-card-menu
    />
    <template #content>
      <div v-if="open" class="p-2">
        <NuxtFormField
          v-if="volumesEditing"
          label="Quantos volumes saem?"
          :description="
            volumesDraft === 0
              ? 'Zero apaga: o cartão volta a contar itens.'
              : 'Sacolas ou caixas, contadas por quem embalou.'
          "
          data-card-volumes-editor
        >
          <div class="flex items-center gap-2">
            <NuxtInputNumber
              v-model="volumesDraft"
              :min="0"
              :max="99"
              data-card-volumes-draft
            />
            <NuxtButton
              label="Gravar"
              color="primary"
              :disabled="busy"
              data-card-volumes-save
              @click="saveVolumes"
            />
          </div>
        </NuxtFormField>
        <NuxtNavigationMenu v-else orientation="vertical" :items="items" />
      </div>
    </template>
  </NuxtPopover>
</template>
