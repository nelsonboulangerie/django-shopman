<script setup lang="ts">
import { computed } from "vue";

defineOptions({ inheritAttrs: false });

const props = withDefaults(
  defineProps<{
    title: string;
    description?: string;
    closeLabel?: string;
    dismissible?: boolean;
    scrollable?: boolean;
    size?: "sm" | "md" | "lg" | "xl";
  }>(),
  {
    closeLabel: "Fechar",
    dismissible: true,
    scrollable: false,
    size: "md",
  },
);

const open = defineModel<boolean>("open", { default: false });

const widths = {
  sm: "sm:max-w-sm",
  md: "sm:max-w-lg",
  lg: "sm:max-w-2xl",
  xl: "sm:max-w-4xl",
};

const ui = computed(() => ({
  overlay: "fixed inset-0 z-50 bg-foreground/45 backdrop-blur-[1px]",
  content: [
    "fixed top-1/2 left-1/2 z-50 grid max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-lg border bg-card text-card-foreground shadow-xl outline-none focus-visible:ring-2 focus-visible:ring-ring",
    widths[props.size],
  ],
  header: "flex min-w-0 items-start gap-3 border-b px-5 py-4 sm:px-6",
  wrapper: "min-w-0 flex-1",
  title: "text-base font-semibold leading-tight text-foreground",
  description: "mt-1 text-sm leading-relaxed text-muted-foreground",
  body: "min-h-0 overflow-y-auto px-5 py-4 sm:px-6",
  footer:
    "flex flex-col-reverse gap-2 border-t px-5 py-4 sm:flex-row sm:justify-end sm:px-6",
  close:
    "grid size-control shrink-0 place-items-center rounded-md text-muted-foreground outline-none transition hover:bg-accent hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring [&_svg]:size-4",
}));
</script>

<template>
  <NuxtModal
    v-model:open="open"
    v-bind="$attrs"
    :title="title"
    :description="description"
    :dismissible="dismissible"
    :scrollable="scrollable"
    :close="true"
    :ui="ui"
  >
    <slot name="trigger" />

    <template #close>
      <button type="button" :aria-label="closeLabel" :class="ui.close">
        <Icon name="lucide:x" aria-hidden="true" />
        <span class="sr-only">{{ closeLabel }}</span>
      </button>
    </template>

    <template #body="scope">
      <slot name="body" v-bind="scope" />
    </template>

    <template v-if="$slots.footer" #footer="scope">
      <slot name="footer" v-bind="scope" />
    </template>
  </NuxtModal>
</template>
