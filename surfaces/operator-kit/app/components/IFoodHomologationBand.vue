<script setup lang="ts">
// Faixa de homologação do iFood: data, hora (com segundos) e client_id do app de
// teste, sempre visíveis, porque o iFood recusa vídeo de evidência sem eles
// (chamado 36323618, DEV-2026-044). Peça da layer: o app que grava evidência a
// monta no app.vue. Só aparece com NUXT_PUBLIC_IFOOD_HOMOLOGATION_CLIENT_ID
// preenchida, o que só o runtime local de teste faz; em qualquer outro ambiente
// não desenha nada.
import { homologationClock } from "../presentation/homologationBand";

const clientId = String(useRuntimeConfig().public.ifoodHomologationClientId || "");
const now = ref<Date | null>(null);
let timer: ReturnType<typeof setInterval> | null = null;
onMounted(() => {
  if (!clientId) return;
  now.value = new Date();
  timer = setInterval(() => (now.value = new Date()), 1000);
});
onBeforeUnmount(() => {
  if (timer) clearInterval(timer);
});
</script>

<template>
  <div
    v-if="clientId && now"
    class="pointer-events-none fixed inset-x-0 bottom-0 z-[100] flex flex-wrap justify-center gap-x-4 bg-black/85 px-3 py-1 font-mono text-xs text-white"
    data-ifood-homologation-band
  >
    <span>Homologação iFood</span>
    <span>{{ homologationClock(now) }}</span>
    <span>client_id {{ clientId }}</span>
  </div>
</template>
