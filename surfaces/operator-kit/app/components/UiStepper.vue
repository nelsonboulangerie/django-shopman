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
  // O operator-kit usa Nuxt UI em modo `unstyled`; por isso este wrapper repõe,
  // sem reinterpretar, o tema canônico do UStepper 4.11.3. Só a cor semântica
  // `primary` continua vindo dos tokens Shopman. No celular, tamanho `md` e resumo
  // da etapa atual evitam comprimir cinco descrições; a partir de `sm`, é o `xl`
  // exibido na documentação oficial.
  root: "flex w-full flex-col gap-4",
  header: "flex",
  item: "group relative w-full text-center",
  container: "relative flex justify-center",
  trigger: "flex size-10 items-center justify-center rounded-full bg-muted text-center align-middle text-base font-medium font-semibold text-muted-foreground outline-primary/25 group-data-[state=completed]:bg-primary group-data-[state=completed]:text-primary-foreground group-data-[state=active]:bg-primary group-data-[state=active]:text-primary-foreground focus-visible:outline-3 sm:size-14 sm:text-xl",
  indicator: "flex size-full items-center justify-center",
  icon: "size-5 shrink-0 sm:size-7",
  separator: "absolute top-[calc(50%-2px)] start-[calc(50%+28px)] end-[calc(-50%+28px)] h-0.5 rounded-full bg-border group-data-[disabled]:opacity-75 group-data-[state=completed]:bg-primary sm:start-[calc(50%+36px)] sm:end-[calc(-50%+36px)]",
  wrapper: "mt-3.5 hidden sm:block",
  title: "text-lg font-medium text-foreground",
  description: "text-lg text-muted-foreground text-wrap",
  content: "size-full",
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
      :ui="ui"
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
