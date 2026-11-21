<script setup lang="ts">
// PRÉVIA (16/11): a cotação em linhas. A linha da opção que vale (a do ✔) em
// destaque; as demais esmaecidas. Não vai ao ar.
const props = defineProps<{ text: string | string[]; size?: "body" | "micro" }>();
const lines = computed(() => (Array.isArray(props.text) ? props.text : props.text.split("\n")).filter(Boolean));
const main = computed(() => {
  const i = lines.value.findIndex((l) => l.includes("✔"));
  return i >= 0 ? i : 0;
});
</script>

<template>
  <span class="flex flex-col tabular-nums" :class="size === 'micro' ? 'op-micro' : 'op-body'">
    <span
      v-for="(line, i) in lines"
      :key="line"
      :class="i === main ? 'font-semibold text-highlighted' : 'text-dimmed'"
    >{{ line }}</span>
  </span>
</template>
