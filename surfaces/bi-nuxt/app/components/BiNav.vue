<script setup lang="ts">
// Navegação do B.I. (V4-BI, desenho de `bi-sobra4.html`, pé da V6-KIT). O rail da suíte
// (`OperatorSuiteRail`, tablet deitado e desktop) leva as oito leituras do app com os
// ícones da prévia; no pé, o da suíte: Avisos, Atalhos, Bloquear e o operador. No
// celular e no tablet em pé, a barra do polegar (`OperatorSectionBar`): as quatro
// primeiras leituras e o "Mais" com Perfis, Explorar, Projeção e Cenários (v3 b).
//
// Cada seção leva a janela de análise na query (`useBiSections`): trocar de seção não
// troca de período, e o link colado abre a mesma leitura. A janela em si mora no
// cabeçalho de cada tela (`BiWindowPicker`), como o período na prévia.
defineProps<{
  place: "rail" | "bar";
  /** Rail: URL da Central. Rail e barra: operador ativo (o menu e o Bloquear). */
  hubUrl?: string;
  operatorName?: string;
}>();
const emit = defineEmits<{ lock: [] }>();

const { sections } = useBiSections();
</script>

<template>
  <OperatorSuiteRail
    v-if="place === 'rail'"
    :sections="sections"
    label="Seções do B.I."
    :hub-url="hubUrl"
    :operator-name="operatorName"
    @lock="emit('lock')"
  />
  <OperatorSectionBar
    v-else
    :sections="sections"
    label="Seções do B.I."
    :operator-name="operatorName"
    @lock="emit('lock')"
  />
</template>
