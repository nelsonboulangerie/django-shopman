<script setup lang="ts">
// Navegação do Marketing na camada visual da suíte (V4-MKT, modelo: `GestorNav`).
// O rail da suíte (`OperatorSuiteRail`, do tablet para cima) tem dois andares: em
// cima a OPERAÇÃO (Decisões com o selo do que espera você, Agendados e Enviados); no
// pé, Ajustes (Campanhas, Modelos, Ofertas e cupons e Plataformas moram lá, numa
// segunda linha do cabeçalho) e, abaixo do traço, Bloquear e o menu do operador. No
// celular as mesmas seções vão para a barra do polegar (`OperatorSectionBar`), como na
// prévia `marketing-decisoes4.html`. `place` diz qual das duas peças este ponto do
// shell monta.
//
// A barra do polegar mora no FIM da coluna de conteúdo (ver `app.vue`), nunca fixa na
// largura da janela: fixa, ela cobria o que estivesse à esquerda (a11y.spec.ts,
// 320×568, regressão de 03/10/2026).
//
// O sino não mora no rail: do tablet para cima o selo de Decisões já é o sino (o sino
// abre a mesma fila, decisão do dono de 03/10/2026). No celular ele fica na barra de
// 56px de cada tela (`MarketingPageHeader`).
defineProps<{
  place: "rail" | "bar";
  /** Rail: URL da Central e operador ativo (o menu e o Bloquear). */
  hubUrl?: string;
  operatorName?: string;
}>();
const emit = defineEmits<{ lock: [] }>();
const { sections, activeSection } = useMarketingSections();
</script>

<template>
  <OperatorSuiteRail
    v-if="place === 'rail'"
    :sections="sections"
    :current="activeSection"
    label="Seções do Marketing"
    :hub-url="hubUrl"
    :operator-name="operatorName"
    @lock="emit('lock')"
  />
  <OperatorSectionBar
    v-else
    :sections="sections"
    :current="activeSection"
    label="Seções do Marketing no celular"
  />
</template>
