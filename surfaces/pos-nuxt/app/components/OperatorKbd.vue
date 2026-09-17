<script setup lang="ts">
import { normalizeClass } from "vue";
import type { HTMLAttributes } from "vue";
import { twMerge } from "tailwind-merge";

const props = withDefaults(defineProps<{
  variant?: "default" | "inverse";
  class?: HTMLAttributes["class"];
}>(), {
  variant: "default",
});

// Classes do consumidor substituem utilitários conflitantes, preservando
// modificadores responsivos. O kit também funciona sem autoimports do app.
const baseClass = "inline-flex h-5 min-w-5 shrink-0 select-none items-center justify-center whitespace-nowrap rounded border px-1.5 font-mono text-xs font-medium leading-none";
</script>

<template>
  <kbd
    :class="twMerge(
      baseClass,
      variant === 'inverse'
        ? 'border-current/30 bg-transparent text-inherit opacity-80'
        : 'bg-muted text-muted-foreground',
      normalizeClass(props.class),
    )"
  ><slot /></kbd>
</template>
