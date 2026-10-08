<script setup lang="ts">
// O aviso de CANAL na fila de Pedidos — nunca o controle. Uma linha por canal de
// VENDA desligado, pausado ou divergente (loja online, WhatsApp, iFood, PDV):
// é o que muda o que entra na fila. Feed e TV não aparecem aqui (estão só no
// ponto da navegação). Estado normal: não existe. Quem pode abrir a aba Canais
// segue a linha até o card do canal, onde mora o toggle.
import type { ChannelAttentionProjection } from "~/types/channelAttention";

const props = defineProps<{
  /** A página passa a leitura quando precisa decidir se cria a toolbar. */
  attention?: ChannelAttentionProjection | null;
}>();

// Mantém o componente utilizável isoladamente no catálogo e nos testes, mas permite
// que a página conheça o estado ANTES de declarar o slot #feedback. Um filho vazio
// ainda faria a faixa contextual reservar espaço sem conteúdo.
const local = props.attention === undefined ? useChannelAttention() : null;
const resolvedAttention = computed(
  () => props.attention ?? local?.attention.value ?? null,
);
const lines = computed(() => resolvedAttention.value?.queue ?? []);
const canOpen = computed(() =>
  Boolean(resolvedAttention.value?.can_open_channels),
);
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
        <NuxtButton
          v-for="item in lines"
          :key="item.ref"
          :to="canOpen ? item.focus_path : undefined"
          :label="item.line"
          :trailing-icon="canOpen ? 'i-lucide-chevron-right' : undefined"
          color="warning"
          variant="link"
          :data-channel-signal-item="item.ref"
          :data-channel-signal-link="canOpen ? '' : undefined"
        />
      </div>
    </template>
  </NuxtAlert>
</template>
