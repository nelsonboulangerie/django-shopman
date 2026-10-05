<script setup lang="ts">
import { computed } from "vue";

export type UiStepperItem = {
  title: string;
  description?: string;
  disabled?: boolean;
};

const props = withDefaults(
  defineProps<{
    items: UiStepperItem[];
    label?: string;
    disabled?: boolean;
    showCurrentDescription?: boolean;
  }>(),
  {
    label: "Etapas",
    disabled: false,
    showCurrentDescription: true,
  },
);

const current = defineModel<number>({ default: 0 });
const normalizedItems = computed(() =>
  props.items.map((item, index) => ({ ...item, value: index })),
);
const activeItem = computed(() => props.items[current.value]);

const ui = {
  root: "w-full",
  header: "flex gap-1 rounded-lg border border-border bg-muted/30 p-1",
  item: "group/step relative flex min-h-control min-w-0 flex-1 items-center rounded-md px-2 text-muted-foreground transition data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm data-[state=completed]:text-primary",
  container: "shrink-0",
  trigger: "absolute inset-0 z-0 flex items-center rounded-md px-2 outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed",
  indicator: "relative z-10 grid size-6 shrink-0 place-items-center rounded-full border border-border text-[11px] group-data-[state=active]/step:border-primary group-data-[state=active]/step:bg-primary group-data-[state=active]/step:text-primary-foreground group-data-[state=completed]/step:border-primary group-data-[state=completed]/step:text-primary",
  separator: "hidden",
  wrapper: "pointer-events-none relative z-10 ml-7 hidden min-w-0 sm:block",
  title: "truncate text-left text-xs font-medium text-current",
  description: "hidden",
  content: "hidden",
};
</script>

<template>
  <div data-slot="stepper-shell">
    <NuxtStepper
      class="ui-stepper-localized"
      v-model="current"
      :items="normalizedItems"
      :linear="false"
      :disabled="disabled"
      :aria-label="label"
      :ui="ui"
    >
      <template #indicator="{ item }">
        <Icon v-if="Number(item.value) < current" name="lucide:check" class="size-3.5" aria-hidden="true" />
        <span v-else>{{ Number(item.value) + 1 }}</span>
      </template>
      <template #title="{ item }">
        <span class="sr-only">{{ Number(item.value) + 1 }}. </span>{{ item.title }}
      </template>
    </NuxtStepper>

    <span class="sr-only" role="status" aria-live="polite">
      Etapa {{ current + 1 }} de {{ items.length }}
    </span>

    <p v-if="showCurrentDescription && activeItem" class="mt-2 text-xs text-muted-foreground">
      <strong class="text-foreground">{{ current + 1 }}. {{ activeItem.title }}.</strong>
      {{ activeItem.description }}
    </p>
  </div>
</template>

<style scoped>
/* Reka 2.10 embute "Step N of M" em inglês sem opção de tradução. */
.ui-stepper-localized :deep([role="status"]) {
  display: none;
}
</style>
