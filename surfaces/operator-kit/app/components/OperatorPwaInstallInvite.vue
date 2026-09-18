<script setup lang="ts">
const props = withDefaults(defineProps<{
  app: string;
  appName?: string;
}>(), {
  appName: "Shopman",
});

const pwa = usePwaInstall({ app: props.app });
const visible = computed(() => !pwa.isStandalone.value
  && !pwa.isDismissed.value
  && (pwa.canInstall.value || pwa.isIos.value));

async function install() {
  if (await pwa.install()) pwa.dismiss();
}
</script>

<template>
  <aside
    v-if="visible"
    class="fixed inset-x-3 bottom-3 z-50 mx-auto max-w-md rounded-md border border-border bg-card p-4 text-card-foreground shadow-xl"
    aria-live="polite"
    data-operator-pwa-install
  >
    <div class="flex items-start gap-3">
      <div class="min-w-0 flex-1">
        <p class="text-sm font-semibold">Instale {{ appName }}</p>
        <p v-if="pwa.isIos.value" class="mt-1 text-sm text-muted-foreground">
          No Safari, toque em Compartilhar e depois em Adicionar à Tela de Início.
        </p>
        <p v-else class="mt-1 text-sm text-muted-foreground">
          Abra o caixa direto da tela inicial deste aparelho.
        </p>
      </div>
      <button
        type="button"
        class="h-9 rounded-md px-3 text-sm font-medium text-muted-foreground hover:bg-muted"
        @click="pwa.dismiss"
      >
        Agora não
      </button>
    </div>
    <button
      v-if="pwa.canInstall.value"
      type="button"
      class="mt-3 h-11 w-full rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground"
      @click="install"
    >
      Instalar
    </button>
  </aside>
</template>
