<script setup lang="ts">
import CanonicalSplitter from "@nuxt/ui/components/Splitter.vue";
import { computed, ref } from "vue";

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

const props = withDefaults(defineProps<{
  id: string;
  persistenceKey: string;
  items: readonly OperatorSplitterItem[];
  orientation?: "horizontal" | "vertical";
  keyboardResizeBy?: number;
  handleLabel?: string;
  disabled?: boolean;
}>(), {
  orientation: "horizontal",
  keyboardResizeBy: 2,
  handleLabel: "Redimensionar painéis",
  disabled: false,
});

const emit = defineEmits<{
  layout: [sizes: number[]];
  resize: [index: number, size: number, previousSize?: number];
  dragging: [index: number, dragging: boolean];
}>();

const renderKey = ref(0);
const autoSaveId = computed(() => `shopman:${props.persistenceKey}`);
const storage = computed(() => createOperatorSplitterStorage(props.items.length));
const normalizedItems = computed(() => props.items.map((item, index) => ({
  ...item,
  slot: item.slot || `panel-${index}`,
})));

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
    :ui="{
      root: 'min-w-0',
      panel: 'min-w-0 overflow-hidden',
      handle: 'group relative z-[var(--op-layer-resize)] bg-border focus-visible:outline-3 focus-visible:outline-offset-[-3px] focus-visible:outline-primary data-[orientation=horizontal]:w-[var(--op-splitter-handle)] data-[orientation=vertical]:h-[var(--op-splitter-handle)]',
    }"
    data-operator-splitter
    @layout="emit('layout', $event)"
    @resize="onResize"
    @dragging="onDragging"
  >
    <template v-for="item in normalizedItems" :key="item.id" #[item.slot]="slotProps">
      <slot :name="item.slot" v-bind="slotProps" />
    </template>
    <template #resize-handle="{ index }">
      <span class="sr-only">{{ handleLabel }} {{ index + 1 }}</span>
      <span class="pointer-events-none absolute inset-0 m-auto h-10 w-1 rounded-full bg-muted-foreground/35 group-hover:bg-muted-foreground/60" aria-hidden="true" />
    </template>
  </CanonicalSplitter>
</template>
