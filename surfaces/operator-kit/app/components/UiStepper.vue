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

// O componente permanece no tema oficial. A única adaptação visual troca,
// responsivamente, entre dois tamanhos que o próprio Nuxt UI oferece: `md` no
// celular (cinco etapas ainda deixam a linha respirar) e `xl` a partir de `sm`.
// Os valores abaixo são literalmente os slots do size `xl` canônico.
const responsiveUi = {
  trigger: "sm:size-14 sm:text-xl",
  icon: "sm:size-7",
  separator:
    "sm:start-[calc(50%+36px)] sm:end-[calc(-50%+36px)]",
  wrapper: "hidden sm:mt-3.5 sm:block",
  title: "sm:text-lg",
  description: "sm:text-lg",
};
</script>

<template>
  <div data-slot="stepper-shell">
    <NuxtStepper
      v-model="current"
      class="ui-stepper-localized"
      :items="normalizedItems"
      :linear="false"
      :disabled="disabled"
      :aria-label="label"
      size="md"
      :ui="responsiveUi"
    >
      <template #title="{ item }">
        <span class="sr-only">{{ Number(item.value) + 1 }}. </span>{{ item.title }}
      </template>
    </NuxtStepper>

    <span class="sr-only" role="status" aria-live="polite">
      Etapa {{ current + 1 }} de {{ items.length }}
    </span>

    <p v-if="showCurrentDescription && activeItem" class="mt-3 text-sm text-muted-foreground sm:hidden">
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
