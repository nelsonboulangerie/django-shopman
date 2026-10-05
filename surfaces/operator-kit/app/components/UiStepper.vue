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
  header: "flex items-start gap-0 rounded-none border-0 bg-transparent p-0",
  item: "group/step relative flex min-w-0 flex-1 flex-col items-center gap-2 text-center text-muted-foreground transition data-[state=active]:text-foreground data-[state=completed]:text-primary",
  container: "relative flex w-full items-center justify-center",
  trigger: "relative z-10 grid size-9 place-items-center rounded-full outline-none transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-60",
  indicator: "grid size-7 place-items-center rounded-full border border-border bg-card text-xs font-semibold tabular-nums text-muted-foreground shadow-xs transition group-data-[state=active]/step:border-primary group-data-[state=active]/step:bg-primary group-data-[state=active]/step:text-primary-foreground group-data-[state=completed]/step:border-primary group-data-[state=completed]/step:bg-primary/10 group-data-[state=completed]/step:text-primary",
  separator: "absolute top-1/2 left-1/2 z-0 h-0.5 w-full -translate-y-1/2 rounded-full bg-border transition group-data-[state=completed]/step:bg-primary",
  wrapper: "pointer-events-none hidden min-w-0 max-w-28 sm:block",
  title: "truncate text-center text-xs font-medium text-current",
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
