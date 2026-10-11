<script setup lang="ts">
import { markPwaUpdateApplied } from "../utils/pwaUpdateReport";

const pwa = usePwaUpdate();
const updating = ref(false);
const config = useRuntimeConfig().public as { operatorPwa?: { app?: string }; appVersion?: string };

async function update() {
  if (updating.value) return;
  updating.value = true;
  // Mesma marca da aplicação automática, com o gatilho que a distingue no log: a
  // prova no ar precisa separar "o operador aceitou" de "entrou sozinha no ocioso".
  markPwaUpdateApplied({
    app: String(config.operatorPwa?.app || "operator"),
    trigger: "prompt",
    from_version: String(config.appVersion || ""),
  });
  const accepted = await pwa.update();
  if (!accepted) updating.value = false;
}
</script>

<template>
  <NuxtAlert
    v-if="pwa.needRefresh.value"
    class="fixed right-3 bottom-3 z-[60] max-w-sm"
    color="info"
    icon="i-lucide-refresh-cw"
    title="Nova versão disponível"
    data-operator-pwa-update
  >
    <template #actions><NuxtButton :loading="updating" :label="updating ? 'Atualizando…' : 'Atualizar'" @click="update" /></template>
  </NuxtAlert>
</template>
