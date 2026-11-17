<script setup lang="ts">
// Faixa da homologação do iFood (chamado 36323618, critérios de 17/11/2026): todo
// vídeo de evidência mostra data, hora e o client_id do app de TESTE. Só liga
// quando o runtime de teste define NUXT_PUBLIC_HOMOLOGATION_CLIENT_ID; sem a env
// (alpha, produção, dev comum) nada aparece. O client_id identifica o app, não é
// segredo; o segredo nunca chega ao navegador.
import { homologationClock } from "~/presentation/homologationBand";

const clientId = String(
  useRuntimeConfig().public.homologationClientId || "",
).trim();
const now = ref(new Date());
let timer: ReturnType<typeof setInterval> | undefined;
onMounted(() => {
  if (!clientId) return;
  timer = setInterval(() => (now.value = new Date()), 1000);
});
onBeforeUnmount(() => timer && clearInterval(timer));
const clock = computed(() => homologationClock(now.value));
</script>

<template>
  <!-- No body e acima de tudo: o overlay de um modal não pode esconder a faixa,
       porque o vídeo de evidência precisa dela em todo quadro. -->
  <Teleport v-if="clientId" to="body">
    <div
      class="pointer-events-none fixed inset-x-0 bottom-0 z-[2147483647] flex flex-wrap items-center justify-center gap-x-4 gap-y-1 bg-inverted px-4 py-1.5 text-center font-mono text-sm text-inverted"
      role="status"
      aria-label="Faixa de homologação do iFood"
      data-homologation-band
    >
      <span class="font-semibold">Homologação iFood (app de teste)</span>
      <span>client_id {{ clientId }}</span>
      <ClientOnly
        ><span data-homologation-clock>{{ clock }}</span></ClientOnly
      >
    </div>
  </Teleport>
</template>
