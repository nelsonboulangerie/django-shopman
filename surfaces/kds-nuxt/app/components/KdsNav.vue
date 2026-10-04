<script setup lang="ts">
// Navegação da Cozinha na camada visual da suíte (prévia v4, `cozinha-estacao4.html`).
// Do tablet para cima, o rail da suíte (`OperatorSuiteRail`): Estações, Preparo,
// Saída (atalho para a coluna Saída do Gestor), Painel de retirada; no pé, Ajustes,
// Avisos, Bloquear e o operador. No celular as mesmas seções vão para a barra do
// polegar (`OperatorSectionBar`). `place` diz qual das duas peças este ponto do shell
// monta. Ajustes não é rota: abre o painel de Ajustes (densidade e data).
const props = defineProps<{
  place: "rail" | "bar";
  /** Rail: URL da Central e operador ativo (o menu e o Bloquear). */
  hubUrl?: string;
  operatorName?: string;
}>();
const emit = defineEmits<{ lock: [] }>();

// No celular o rail não aparece e o sino vai para o cabeçalho de cada tela: aqui ele
// só é montado do tablet para cima (um sino por tela, não dois no DOM).
const isPhone = useMediaQuery("(max-width: 767.98px)");
const { sections, current } = useKdsSections(props.place);
const settingsOpen = useKdsSettingsOpen();

function onSelect(key: string) {
  if (key === "settings") settingsOpen.value = true;
}
</script>

<template>
  <OperatorSuiteRail
    v-if="place === 'rail'"
    :sections="sections"
    :current="current"
    label="Seções da Cozinha"
    :hub-url="hubUrl"
    :operator-name="operatorName"
    @select="onSelect"
    @lock="emit('lock')"
  >
    <template v-if="!isPhone" #foot>
      <NotificationBell placement="rail" />
    </template>
  </OperatorSuiteRail>
  <OperatorSectionBar
    v-else
    :sections="sections"
    :current="current"
    label="Seções da Cozinha"
    @select="onSelect"
  />
</template>
