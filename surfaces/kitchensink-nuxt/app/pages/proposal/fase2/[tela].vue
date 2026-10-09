<script setup lang="ts">
// As telas compostas da rodada 2 da proposta da fase 2: as peças JUNTAS, disputando
// espaço e atenção, em tela cheia (390 e 1440 são a mesma rota; o arranjo muda por CSS).
// `?estado=` escolhe a situação: selecao (padrão), livre, filtros, busca, favorito,
// detalhe, vazio, erro, agrupado. As regras de precedência que estas telas revelaram
// estão em docs/plans/WP-FASE2-UX-OPERADOR.md, seção 11.
import { computed, onMounted, ref } from "vue";

const route = useRoute();
const tela = computed(() => String(route.params.tela ?? ""));
const estado = computed(() => String(route.query.estado ?? ""));
const titles: Record<string, string> = {
  fila: "Fila do Gestor",
  historico: "Histórico do Gestor",
  compras: "Base do Compras",
  pdv: "Balcão do PDV",
};
if (!titles[tela.value]) {
  throw createError({ statusCode: 404, statusMessage: "Tela composta inexistente" });
}
useHead({ title: `Proposta fase 2: ${titles[tela.value]}` });

const hydrated = ref(false);
onMounted(() => {
  hydrated.value = true;
});
</script>

<template>
  <div data-proposal="fase2" :data-fase2-tela="tela" :data-hydrated="hydrated ? 'true' : 'false'">
    <Fase2TelaFila v-if="tela === 'fila'" :key="estado" :estado="estado" />
    <Fase2TelaHistorico v-else-if="tela === 'historico'" :key="estado" :estado="estado" />
    <Fase2TelaCompras v-else-if="tela === 'compras'" :key="estado" :estado="estado" />
    <Fase2TelaPdv v-else-if="tela === 'pdv'" :key="estado" :estado="estado" />
  </div>
</template>
