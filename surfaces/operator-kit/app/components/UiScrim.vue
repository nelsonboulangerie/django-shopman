<script setup lang="ts">
import { computed, normalizeClass } from "vue";
import type { HTMLAttributes } from "vue";

const props = withDefaults(
  defineProps<{
    label?: string;
    class?: HTMLAttributes["class"];
  }>(),
  { label: "Fechar painel" },
);

const emit = defineEmits<{ click: [event: MouseEvent] }>();
const rootClass = computed(() => [
  "fixed inset-0 z-40 bg-foreground/35 backdrop-blur-[1px]",
  normalizeClass(props.class),
]);
</script>

<template>
  <button type="button" :class="rootClass" :aria-label="label" data-slot="scrim" @click="emit('click', $event)" />
</template>
