<script setup lang="ts">
import { markPwaUpdateApplied } from "../utils/pwaUpdateReport";
import { alertActions } from "../utils/alertActions";

const pwa = usePwaUpdate();
const updating = ref(false);
const config = useRuntimeConfig().public as {
  operatorPwa?: { app?: string };
  appVersion?: string;
};

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

const actions = computed(() => [
  {
    label: updating.value ? "Atualizando…" : "Atualizar agora",
    loading: updating.value,
    onClick: update,
  },
]);
</script>

<template>
  <NuxtAlert
    v-if="pwa.needRefresh.value"
    color="info"
    variant="subtle"
    orientation="horizontal"
    icon="i-lucide-refresh-cw"
    title="Nova versão disponível"
    description="A tela será recarregada para aplicar as melhorias mais recentes."
    :actions="alertActions('info', actions)"
    data-operator-pwa-update
  />
</template>
