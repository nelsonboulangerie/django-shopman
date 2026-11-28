<script setup lang="ts">
// O SELO DOS PIX ABERTOS fora da tela de resultado, e a saída dele: o cliente que
// ainda paga voltou ao balcão, e o operador precisa do QR de novo, na tela dele e
// na Tela do cliente (beta 07/11: o selo só informava). Com uma tela guardada, o
// selo é o botão que a reabre; com várias, um menu com o pedido de cada uma. O Pix
// que voltou de um recarregar não tem tela guardada (o QR não fica no dispositivo):
// segue como selo, acompanhado até resolver.
//
// A cor `info` mora no selo, não no botão (conjunto mínimo da suíte, README do kit):
// o botão é `ghost` `neutral` `md` e carrega o próprio selo dentro dele.
const props = defineProps<{
  badge: { label: string; title: string };
  /** Os pedidos com a tela do Pix guardada, na ordem do selo. */
  reopenable: readonly string[];
}>();
const emit = defineEmits<{ reopen: [orderRef: string] }>();

const items = computed(() => props.reopenable.map((orderRef) => ({
  label: `Mostrar o Pix do pedido ${orderRef}`,
  icon: "i-lucide-qr-code",
  onSelect: () => emit("reopen", orderRef),
})));
</script>

<template>
  <NuxtDropdownMenu v-if="reopenable.length > 1" :items="items" :content="{ align: 'end' }">
    <NuxtButton
      color="neutral"
      variant="ghost"
      size="md"
      trailing-icon="i-lucide-chevron-down"
      :title="badge.title"
      :aria-label="`${badge.label}. Mostrar o QR de um dos pedidos.`"
      data-pix-pending-menu
    >
      <NuxtBadge color="info" icon="i-lucide-loader-circle" :label="badge.label" />
    </NuxtButton>
  </NuxtDropdownMenu>
  <NuxtButton
    v-else-if="reopenable.length === 1"
    color="neutral"
    variant="ghost"
    size="md"
    :title="`${badge.title}. Toque para mostrar o QR de novo.`"
    :aria-label="`${badge.label}. Mostrar o QR de novo.`"
    data-pix-pending-reopen
    @click="emit('reopen', reopenable[0]!)"
  >
    <NuxtBadge color="info" icon="i-lucide-loader-circle" :label="badge.label" />
  </NuxtButton>
  <NuxtBadge
    v-else
    color="info"
    icon="i-lucide-loader-circle"
    role="status"
    :title="badge.title"
    :label="badge.label"
    data-pix-pending-status
  />
</template>
