<script setup lang="ts">
const pwa = usePwaUpdate();
const updating = ref(false);

async function update() {
  if (updating.value) return;
  updating.value = true;
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
