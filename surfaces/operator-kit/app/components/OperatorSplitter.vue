<script setup lang="ts">
import CanonicalSplitter from "@nuxt/ui/components/Splitter.vue";
import { computed, onMounted, ref } from "vue";

import { createOperatorSplitterStorage } from "../utils/operatorSplitterStorage";

export interface OperatorSplitterItem {
  id: string;
  slot?: string;
  defaultSize?: number;
  minSize?: number;
  maxSize?: number;
  collapsible?: boolean;
  collapsedSize?: number;
  class?: string;
}

const props = withDefaults(
  defineProps<{
    id: string;
    persistenceKey: string;
    items: readonly OperatorSplitterItem[];
    orientation?: "horizontal" | "vertical";
    keyboardResizeBy?: number;
    handleLabel?: string;
    disabled?: boolean;
  }>(),
  {
    orientation: "horizontal",
    keyboardResizeBy: 2,
    handleLabel: "Redimensionar painéis",
    disabled: false,
  },
);

const emit = defineEmits<{
  layout: [sizes: number[]];
  resize: [index: number, size: number, previousSize?: number];
  dragging: [index: number, dragging: boolean];
}>();

const renderKey = ref(0);
const autoSaveId = computed(() => `shopman:${props.persistenceKey}`);
const storage = computed(() =>
  createOperatorSplitterStorage(props.items.length),
);
const normalizedItems = computed(() =>
  props.items.map((item, index) => ({
    ...item,
    slot: item.slot || `panel-${index}`,
    class: ["min-w-0 overflow-hidden", item.class],
  })),
);

function reset() {
  storage.value.removeItem?.(`reka:${autoSaveId.value}`);
  renderKey.value += 1;
}

function onResize(index: number, size: number, previousSize?: number) {
  emit("resize", index, size, previousSize);
}

function onDragging(index: number, dragging: boolean) {
  emit("dragging", index, dragging);
}

function splitterElement(): HTMLElement | null {
  if (typeof document === "undefined") return null;
  return document.querySelector<HTMLElement>(
    `[data-slot="root"][data-panel-group-id="${CSS.escape(props.id)}"]`,
  );
}

/**
 * O handle do Splitter do Nuxt UI é focável e tem role=separator, mas a versão
 * corrente não expõe os atributos de valor exigidos pela ARIA. O wrapper já
 * conhece limites e layout, então completa o contrato sem duplicar o splitter.
 */
function syncHandleAccessibility() {
  const root = splitterElement();
  if (!root) return;
  const panels = [...root.querySelectorAll<HTMLElement>("[data-slot='panel']")];
  const handles = [
    ...root.querySelectorAll<HTMLElement>(
      "[data-slot='handle'][role='separator']",
    ),
  ];
  handles.forEach((handle, index) => {
    const item = normalizedItems.value[index];
    const panelSize = Number(panels[index]?.dataset.panelSize);
    const value = Number.isFinite(panelSize)
      ? panelSize
      : (item?.defaultSize ?? 50);
    handle.setAttribute("aria-label", `${props.handleLabel} ${index + 1}`);
    handle.setAttribute("aria-valuemin", String(item?.minSize ?? 0));
    handle.setAttribute("aria-valuemax", String(item?.maxSize ?? 100));
    handle.setAttribute("aria-valuenow", String(Math.round(value * 10) / 10));
    const controlled = [
      normalizedItems.value[index]?.id,
      normalizedItems.value[index + 1]?.id,
    ]
      .filter(Boolean)
      .join(" ");
    if (controlled) handle.setAttribute("aria-controls", controlled);
  });
}

function onLayout(sizes: number[]) {
  emit("layout", sizes);
}

onMounted(() => {
  window.setTimeout(syncHandleAccessibility, 100);
});

defineExpose({ reset });
</script>

<template>
  <CanonicalSplitter
    :id="id"
    :key="renderKey"
    :items="normalizedItems"
    :orientation="orientation"
    :auto-save-id="autoSaveId"
    :keyboard-resize-by="keyboardResizeBy"
    :storage="storage"
    :disabled="disabled"
    :hit-area-margins="{ coarse: 16, fine: 6 }"
    class="min-w-0"
    data-operator-splitter
    @layout="onLayout"
    @resize="onResize"
    @dragging="onDragging"
  >
    <template
      v-for="item in normalizedItems"
      :key="item.id"
      #[item.slot]="slotProps"
    >
      <slot :name="item.slot" v-bind="slotProps" />
    </template>
    <template #resize-handle="{ index }">
      <span class="sr-only">{{ handleLabel }} {{ index + 1 }}</span>
      <NuxtSeparator
        :orientation="orientation === 'horizontal' ? 'vertical' : 'horizontal'"
      />
    </template>
  </CanonicalSplitter>
</template>
