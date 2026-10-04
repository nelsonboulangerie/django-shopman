<script setup lang="ts">
// Navegação do Gestor (UX-KIT-V1, desenho da v4 desde o UX-KIT-V2). O rail da suíte
// (`OperatorSuiteRail`, do tablet para cima) tem dois andares, como na prévia
// `gestor-fila4.html`: em cima a OPERAÇÃO (Pedidos e Saída, com o rótulo do grupo e os
// selos); no pé, Ajustes (Histórico, Catálogo, Clientes, Canais e Postos moram lá) e,
// abaixo do traço, Alertas, Avisos, Bloquear e o operador. No celular as mesmas seções
// vão para a barra do polegar (`OperatorSectionBar`). `place` diz qual das duas peças
// este ponto do shell monta.
defineProps<{
  place: "rail" | "bar";
  /** Rail: URL da Central e operador ativo (o menu e o Bloquear). */
  hubUrl?: string;
  operatorName?: string;
}>();
const emit = defineEmits<{ lock: [] }>();
// No celular o rail não aparece e o sino vai para o cabeçalho de cada tela: aqui ele
// só é montado do tablet para cima (um sino por tela, não dois no DOM).
const isPhone = useMediaQuery("(max-width: 767.98px)");
const { sections, current } = useGestorSections();
</script>

<template>
  <OperatorSuiteRail
    v-if="place === 'rail'"
    :sections="sections"
    :current="current"
    label="Seções do Gestor"
    :hub-url="hubUrl"
    :operator-name="operatorName"
    @lock="emit('lock')"
  >
    <template v-if="!isPhone" #foot>
      <AlertsBell placement="rail" />
      <NotificationBell placement="rail" />
    </template>
  </OperatorSuiteRail>
  <OperatorSectionBar v-else :sections="sections" :current="current" label="Seções do Gestor" />
</template>
