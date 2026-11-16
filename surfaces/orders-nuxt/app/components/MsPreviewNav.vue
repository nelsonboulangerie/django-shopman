<script setup lang="ts">
// PRÉVIA (16/11, DEV-2026-030): os links entre as prévias de "Quem leva" (serviço da
// corrida e entregador da casa). Não vai ao ar.
const props = defineProps<{ current: number }>();
const items = [
  { n: 1, label: "Chamar entregador: quem leva" },
  { n: 2, label: "Corrida da casa na Saída" },
  { n: 3, label: "O que o entregador recebe" },
  { n: 4, label: "Mapa em pé e deitado" },
];
</script>

<template>
  <nav class="fixed bottom-4 left-1/2 z-[100] flex -translate-x-1/2 flex-wrap items-center justify-center gap-1.5 rounded-2xl bg-[#f6efe6]/95 px-3 py-2 shadow-xl ring-1 ring-black/15 backdrop-blur" aria-label="Prévias">
    <span class="me-1 text-sm font-semibold text-black/70">Prévias:</span>
    <a
      v-for="it in items"
      :key="it.n"
      :href="`/preview-multisservico/${it.n}`"
      class="rounded-lg px-2.5 py-1 text-sm"
      :class="it.n === props.current ? 'bg-black font-semibold text-white' : 'bg-white text-black ring-1 ring-black/15 hover:bg-black/5'"
      :aria-current="it.n === props.current ? 'page' : undefined"
    >{{ it.n }} · {{ it.label }}</a>
  </nav>
</template>
