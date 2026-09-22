<script setup lang="ts">
// A loja no iFood, dentro do card do canal iFood (aba Canais): o que o iFood diz da
// loja na última conferência e, quando diverge da casa, o porquê. Ligar e desligar
// (com período e motivo) é o toggle "Ativo" do card — o mesmo de todo canal.
// Some por inteiro enquanto a integração estiver desligada.
import { ifoodStatusLine } from "~/presentation/ifoodStore";

const { store } = useIFoodStore();

const visible = computed(() => Boolean(store.value?.enabled));
const statusLine = computed(() => (store.value ? ifoodStatusLine(store.value) : ""));
</script>

<template>
  <div v-if="visible && store" class="space-y-1 border-t border-border pt-3" data-ifood-store>
    <p class="text-xs font-medium text-muted-foreground">A loja no iFood</p>
    <p class="text-sm font-semibold text-foreground" data-ifood-status>{{ statusLine }}</p>
    <ul v-if="store.diverges && store.ifood_problems.length" class="flex flex-col gap-0.5 text-xs text-amber-700 dark:text-amber-300" data-ifood-problems>
      <li v-for="(problem, i) in store.ifood_problems" :key="i">{{ problem }}</li>
    </ul>
  </div>
</template>
