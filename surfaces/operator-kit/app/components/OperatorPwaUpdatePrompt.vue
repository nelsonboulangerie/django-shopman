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
  <aside
    v-if="pwa.needRefresh.value"
    class="fixed bottom-3 right-3 z-[60] flex max-w-sm items-center gap-3 rounded-md border border-border bg-card p-3 text-card-foreground shadow-xl"
    aria-live="polite"
    data-operator-pwa-update
  >
    <p class="min-w-0 flex-1 text-sm font-medium">Nova versão disponível</p>
    <button
      type="button"
      class="h-9 rounded-md bg-primary px-3 text-sm font-semibold text-primary-foreground disabled:opacity-60"
      :disabled="updating"
      @click="update"
    >
      {{ updating ? "Atualizando…" : "Atualizar" }}
    </button>
  </aside>
</template>
