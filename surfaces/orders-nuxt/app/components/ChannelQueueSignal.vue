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
  <div
    v-if="lines.length"
    class="flex flex-col gap-1 rounded-md border border-warning/50 bg-warning/10 px-3 py-2 text-sm"
    role="status"
    data-channel-signal
  >
    <div v-for="item in lines" :key="item.ref" class="flex items-center gap-2" :data-channel-signal-item="item.ref">
      <Icon name="lucide:store" class="size-4 shrink-0 text-warning" />
      <NuxtLink
        v-if="canOpen"
        :to="item.focus_path"
        class="inline-flex items-center gap-1 rounded-md px-1 py-0.5 font-medium transition hover:bg-accent hover:text-foreground"
        data-channel-signal-link
      >
        {{ item.line }}
        <Icon name="lucide:chevron-right" class="size-3.5 opacity-60" />
      </NuxtLink>
      <span v-else class="font-medium">{{ item.line }}</span>
    </div>
  </div>
</template>
