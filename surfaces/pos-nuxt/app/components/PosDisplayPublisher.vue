<script setup lang="ts">
// Publicador RENDERLESS da tela do cliente. Recebe as fontes vivas da venda num
// único objeto de getters (`PosDisplaySources`, montado uma vez no setup do
// index.vue), transforma em snapshot (presentation pura) e publica no
// BroadcastChannel. Autocontido de propósito: a integração na tela de venda é
// uma const + uma linha de template, para não disputar `pages/index.vue` com
// outras frentes. Não renderiza nada.
//
// O troco do fechamento já chega CONGELADO dentro do `result` (`changeQ`,
// capturado pelo usePosSale no instante do commit): operador, display e recibo
// leem da mesma fonte — este publicador não precisa congelar nada por conta.
import { computed } from "vue";

import type { PosDisplaySources } from "~/types/customerDisplay";
import { buildCustomerDisplaySnapshot } from "~/presentation/customerDisplay";
import { useCustomerDisplayPublisher } from "~/composables/useCustomerDisplay";

const props = defineProps<{ sources: PosDisplaySources }>();
// Getters estáveis: lidos uma vez; a reatividade vem do que eles LEEM.
const s = props.sources;

const snapshot = computed(() => buildCustomerDisplaySnapshot({
  shopName: s.pos()?.shop_name || "",
  checkoutMode: s.checkoutMode(),
  items: s.items(),
  review: s.review(),
  result: s.result(),
  pixStatus: s.pixStatus(),
  discountReasons: s.pos()?.checkout?.discount_reasons || [],
}));

useCustomerDisplayPublisher(snapshot);
</script>

<template>
  <!-- Renderless: só publica. -->
</template>
