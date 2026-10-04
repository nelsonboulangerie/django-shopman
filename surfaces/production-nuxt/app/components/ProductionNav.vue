<script setup lang="ts">
// Navegação da Produção na camada visual da suíte (V4-PROD, modelo do Gestor). O rail
// (`OperatorSuiteRail`, do tablet para cima) leva o ciclo do lote com a tecla impressa
// sob o nome (Alt1 a Alt5, só com ponteiro fino), os Timers logo abaixo e, no pé,
// Receitas, Relatórios e o Letreiro; depois do traço, Alertas, Bloquear e o operador.
// No celular as cinco etapas vão para a barra do polegar (`OperatorSectionBar`).
// `place` diz qual das duas peças este ponto do shell monta.
import { activeSectionKey } from "../../../operator-kit/app/presentation/appBar";

defineProps<{
  place: "rail" | "bar";
  /** Rail: URL da Central e operador ativo (o menu e o Bloquear). */
  hubUrl?: string;
  operatorName?: string;
}>();
const emit = defineEmits<{ lock: [] }>();
// No celular o sino mora no cabeçalho de cada tela: aqui só do tablet para cima (um
// sino por tela, não dois no DOM).
const isPhone = useMediaQuery("(max-width: 767.98px)");
const { sections, phone } = useProductionSections();
// Na barra do polegar só moram as etapas: em Timers, Receitas, Relatórios ou no
// Letreiro nenhuma delas acende (a barra não cai na Abertura por ser a raiz).
const route = useRoute();
const phoneCurrent = computed(() => {
  const key = activeSectionKey(route.path, sections.value);
  return phone.value.some((section) => section.key === key) ? key : "none";
});
</script>

<template>
  <OperatorSuiteRail
    v-if="place === 'rail'"
    :sections="sections"
    label="Telas de produção"
    :hub-url="hubUrl"
    :operator-name="operatorName"
    print-shortcuts
    dense-labels
    @lock="emit('lock')"
  >
    <template v-if="!isPhone" #foot>
      <AlertsBell placement="rail" />
    </template>
  </OperatorSuiteRail>
  <OperatorSectionBar
    v-else
    :sections="phone"
    :current="phoneCurrent"
    label="Telas de produção"
  />
</template>
