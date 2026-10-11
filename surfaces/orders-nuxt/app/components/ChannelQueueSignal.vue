<script setup lang="ts">
// O aviso de CANAL na fila de Pedidos — nunca o controle. Uma linha por canal de
// VENDA desligado, pausado ou divergente (loja online, WhatsApp, iFood, PDV):
// é o que muda o que entra na fila. Feed e TV não aparecem aqui (estão só no
// ponto da navegação). Estado normal: não existe. Quem pode abrir a aba Canais
// segue a linha até o card do canal, onde mora o toggle.
const { attention } = useChannelAttention();
const lines = computed(() => attention.value?.queue ?? []);
const canOpen = computed(() => Boolean(attention.value?.can_open_channels));
</script>

<template>
  <NuxtAlert
    v-if="lines.length"
    color="warning"
    variant="subtle"
    icon="i-lucide-store"
    title="Atenção nos canais"
    data-channel-signal
  >
    <template #description>
      <div class="flex flex-col items-start gap-1">
        <NuxtButton v-for="item in lines" :key="item.ref" :to="canOpen ? item.focus_path : undefined" :label="item.line" :trailing-icon="canOpen ? 'i-lucide-chevron-right' : undefined" color="warning" variant="link" :data-channel-signal-item="item.ref" :data-channel-signal-link="canOpen ? '' : undefined" />
      </div>
    </template>
  </NuxtAlert>
</template>
