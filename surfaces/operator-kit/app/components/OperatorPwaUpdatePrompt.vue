<script setup lang="ts">
import { markPwaUpdateApplied } from "../utils/pwaUpdateReport";
import { alertActions } from "../utils/alertActions";

const emit = defineEmits<{ visibility: [visible: boolean] }>();
const pwa = usePwaUpdate();
const dismissed = ref(false);
const visible = computed(() => pwa.needRefresh.value && !dismissed.value);
watch(pwa.needRefresh, (value) => {
  if (!value) dismissed.value = false;
});
watch(visible, (value) => emit("visibility", value), { immediate: true });
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
    label: "Agora não",
    secondary: true,
    onClick: () => { dismissed.value = true; },
  },
  {
    label: updating.value ? "Atualizando…" : "Atualizar agora",
    loading: updating.value,
    onClick: update,
  },
]);
</script>

<template>
  <NuxtAlert
    v-if="visible"
    color="info"
    variant="subtle"
    icon="i-lucide-refresh-cw"
    title="Nova versão disponível"
    description="A tela será recarregada para aplicar as melhorias mais recentes."
    :actions="alertActions('info', actions)"
    data-operator-pwa-update
  />
</template>
