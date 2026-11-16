<script setup lang="ts">
// PRÉVIA (16/11): os links entre as 7 prévias da revisão das Entregas. Não vai ao ar.
const props = defineProps<{ current: number }>();
const items = [
  { n: 1, label: "Chamar entregador" },
  { n: 2, label: "Sugestões" },
  { n: 3, label: "Editando" },
  { n: 4, label: "Painel" },
  { n: 5, label: "Corrida em apuros" },
  { n: 6, label: "Volta" },
  { n: 7, label: "Tela do cliente" },
  { n: 8, label: "Cartão da Saída" },
];
const href = (n: number) => (n === 7 ? "http://localhost:3911/preview-revisao/7" : `http://localhost:3121/preview-revisao/${n}`);
</script>

<template>
  <nav class="fixed bottom-4 left-1/2 z-[100] flex -translate-x-1/2 flex-wrap items-center justify-center gap-1.5 rounded-2xl bg-[#f6efe6]/95 px-3 py-2 shadow-xl ring-1 ring-black/15 backdrop-blur" aria-label="Prévias">
    <span class="me-1 text-sm font-semibold text-black/70">Prévias:</span>
    <a
      v-for="it in items"
      :key="it.n"
      :href="href(it.n)"
      class="rounded-lg px-2.5 py-1 text-sm"
      :class="it.n === props.current ? 'bg-black font-semibold text-white' : 'bg-white text-black ring-1 ring-black/15 hover:bg-black/5'"
      :aria-current="it.n === props.current ? 'page' : undefined"
    >{{ it.n }} · {{ it.label }}</a>
  </nav>
</template>
