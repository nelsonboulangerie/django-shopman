<script setup lang="ts">
// Publicador RENDERLESS da tela do cliente. Recebe as fontes vivas da venda num
// único objeto de getters (`PosDisplaySources`, montado uma vez no setup do
// index.vue), transforma em snapshot (presentation pura) e publica no
// BroadcastChannel. Autocontido de propósito: a integração na tela de venda é
// uma const + uma linha de template, para não disputar `pages/index.vue` com
// outras frentes. Não renderiza nada.
import { computed, ref, watch } from "vue";

import type { PosDisplaySources } from "~/types/customerDisplay";
import { buildCustomerDisplaySnapshot } from "~/presentation/customerDisplay";
import { useCustomerDisplayPublisher } from "~/composables/useCustomerDisplay";

const props = defineProps<{ sources: PosDisplaySources }>();
// Getters estáveis: lidos uma vez; a reatividade vem do que eles LEEM.
const s = props.sources;

// O troco é congelado NO INSTANTE em que o resultado nasce (flush sync): logo
// depois o submitSale reseta o cart e o troco computado volta a zero — sem a
// captura síncrona, o cliente nunca veria o troco dele na tela.
const resultChangeQ = ref(0);
watch(
  () => s.result(),
  (result) => {
    resultChangeQ.value = result ? Math.max(0, s.paymentChangeQ()) : 0;
  },
  { flush: "sync" },
);

const snapshot = computed(() => buildCustomerDisplaySnapshot({
  shopName: s.pos()?.shop_name || "",
  checkoutMode: s.checkoutMode(),
  items: s.items(),
  review: s.review(),
  result: s.result(),
  pixStatus: s.pixStatus(),
  resultChangeQ: resultChangeQ.value,
  discountReasons: s.pos()?.checkout?.discount_reasons || [],
}));

useCustomerDisplayPublisher(snapshot);
</script>

<template>
  <!-- Renderless: só publica. -->
</template>
