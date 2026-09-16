<script setup lang="ts">
const push = useWebPush();
</script>

<template>
  <div
    v-if="!push.active.value && push.permission.value !== 'denied'"
    data-operator-push-invite
    class="fixed bottom-[calc(1rem+env(safe-area-inset-bottom))] right-4 z-40 max-w-xs rounded-xl border bg-card p-3 shadow-lg"
  >
    <p class="text-sm font-semibold">Avisos mesmo com o app fechado</p>
    <p class="mt-1 text-xs text-muted-foreground">Ative neste aparelho para receber só os avisos desta área.</p>
    <button
      type="button"
      class="mt-2 inline-flex h-11 items-center rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-60"
      :disabled="push.loading.value"
      @click="push.activate"
    >
      {{ push.loading.value ? 'Ativando…' : 'Ativar avisos' }}
    </button>
  </div>
</template>
