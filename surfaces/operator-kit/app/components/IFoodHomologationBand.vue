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
  <!-- Teleport para o body, acima de qualquer modal (o login do Gestor inclusive):
       a faixa precisa aparecer nítida em todo quadro do vídeo. Canto inferior
       direito e compacta, para não cobrir a barra lateral (operador, avisos) nem o
       rodapé dos painéis; sem clique (pointer-events-none). -->
  <Teleport to="body">
    <div
      v-if="clientId && now"
      class="pointer-events-none fixed bottom-2 right-2 z-[2147483647] flex flex-col items-end rounded-md bg-black/85 px-2.5 py-1 text-right font-mono text-xs leading-snug text-white shadow-lg"
      data-ifood-homologation-band
    >
      <span>Homologação iFood · {{ homologationClock(now) }}</span>
      <span>client_id {{ clientId }}</span>
    </div>
  </Teleport>
</template>
