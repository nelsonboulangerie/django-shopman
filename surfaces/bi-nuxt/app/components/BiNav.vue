<script setup lang="ts">
// Navegação do B.I. (V4-BI, desenho de `bi-sobra4.html`). O rail da suíte
// (`OperatorSuiteRail`, do tablet para cima) leva as oito leituras do app com os
// ícones da prévia; no pé, Avisos, Bloquear e o operador. No celular as mesmas seções
// vão para a barra do polegar (`OperatorSectionBar`), que rola quando não cabem.
//
// Cada seção leva a janela de análise na query (`useBiSections`): trocar de seção não
// troca de período, e o link colado abre a mesma leitura. A janela em si mora no
// cabeçalho de cada tela (`BiWindowPicker`), como o período na prévia.
defineProps<{
  place: "rail" | "bar";
  /** Rail: URL da Central e operador ativo (o menu e o Bloquear). */
  hubUrl?: string;
  operatorName?: string;
}>();
const emit = defineEmits<{ lock: [] }>();

const { sections } = useBiSections();
// No celular o sino vai para o cabeçalho de cada tela (`BiPhoneBell`): aqui ele só é
// montado do tablet para cima (um sino por tela, não dois no DOM).
const isPhone = useMediaQuery("(max-width: 767.98px)");
</script>

<template>
  <OperatorSuiteRail
    v-if="place === 'rail'"
    :sections="sections"
    label="Seções do B.I."
    :hub-url="hubUrl"
    :operator-name="operatorName"
    @lock="emit('lock')"
  >
    <template v-if="!isPhone" #foot>
      <NotificationBell placement="rail" />
    </template>
  </OperatorSuiteRail>
  <OperatorSectionBar v-else :sections="sections" label="Seções do B.I." />
</template>
