<script setup lang="ts">
// O SINAL da loja no iFood na aba Pedidos — nunca o controle. Aparece só quando muda
// o que entra na fila: iFood desligado no Gestor, ou divergente da loja. Em estado
// normal não existe. Quem pode abrir a aba Canais segue o sinal até o card do canal
// iFood, onde mora o toggle; os outros leem o estado e seguem.
import { IFOOD_FOCUS_KEY, queueSignal } from "~/presentation/ifoodStore";

const { store } = useIFoodStore();
const signal = computed(() => queueSignal(store.value));
const canOpenControl = computed(() => Boolean(store.value?.can_open_channels));
const target = { path: "/feeds", query: { focus: IFOOD_FOCUS_KEY } };
</script>

<template>
  <div
    v-if="signal"
    class="flex flex-wrap items-center gap-2 rounded-md border border-warning/50 bg-warning/10 px-3 py-2 text-sm"
    role="status"
    data-ifood-signal
  >
    <Icon name="lucide:store" class="size-4 text-warning" />
    <NuxtLink
      v-if="canOpenControl"
      :to="target"
      class="inline-flex items-center gap-1 rounded-md px-1 py-0.5 font-medium transition hover:bg-accent hover:text-foreground"
      data-ifood-signal-link
    >
      {{ signal }}
      <Icon name="lucide:chevron-right" class="size-3.5 opacity-60" />
    </NuxtLink>
    <span v-else class="font-medium">{{ signal }}</span>
  </div>
</template>
