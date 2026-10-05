<script setup lang="ts">
// Switch canônico do Nuxt UI, com uma área de toque operacional de 44 px.
//
// Trilho, polegar, estados, teclado e ARIA vêm do `NuxtSwitch` (Reka UI). O
// wrapper apenas traduz os dois tamanhos e três tons já usados pela suíte.
import { computed, useAttrs } from "vue";

defineOptions({ inheritAttrs: false });

const props = withDefaults(
  defineProps<{
    modelValue?: boolean;
    disabled?: boolean;
    tone?: "primary" | "success" | "muted";
    size?: "md" | "sm";
  }>(),
  { modelValue: false, tone: "primary", size: "md" },
);

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>();
const attrs = useAttrs();

// Os tamanhos oficiais xs e xl correspondem aos trilhos compactos e regulares
// já adotados: 28×16 e 44×24. O alvo permanece 44×44 nos dois casos.
const nuxtSize = computed(() => (props.size === "sm" ? "xs" : "xl"));
const nuxtColor = computed(() => (props.tone === "success" ? "success" : "primary"));
const ui = computed(() => ({
  root: "size-control items-center justify-center",
  base: [
    "after:absolute after:inset-0 after:content-['']",
    props.tone === "muted" ? "data-[state=checked]:bg-accented" : "",
  ].join(" "),
}));
</script>

<template>
  <NuxtSwitch
    v-bind="attrs"
    :model-value="modelValue"
    :disabled="disabled"
    :color="nuxtColor"
    :size="nuxtSize"
    :ui="ui"
    data-slot="switch"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>
