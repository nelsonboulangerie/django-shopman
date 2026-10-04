<script setup lang="ts">
// Navegação da Cozinha na camada visual da suíte (prévia v4, `cozinha-estacao4.html`,
// pé da V6-KIT). No tablet deitado e no desktop, o rail da suíte (`OperatorSuiteRail`):
// Estações, Preparo, Saída (atalho para a coluna Saída do Gestor), Painel de retirada;
// no pé, na ordem da v4 da Cozinha, Avisos · Ajustes · Bloquear e o operador, sem traço
// (`footOrder="inbox-first"`). No celular e no tablet em pé, a barra do polegar
// (`OperatorSectionBar`): Preparo · Saída · Estações · Mais, como `cozinha-celular4.html`.
// `place` diz qual das duas peças este ponto do shell monta. Ajustes não é rota: abre o
// painel de Ajustes.
const props = defineProps<{
  place: "rail" | "bar";
  /** Rail: URL da Central. Rail e barra: operador ativo (o menu e o Bloquear). */
  hubUrl?: string;
  operatorName?: string;
}>();
const emit = defineEmits<{ lock: [] }>();

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
    foot-order="inbox-first"
    @select="onSelect"
    @lock="emit('lock')"
  />
  <OperatorSectionBar
    v-else
    :sections="sections"
    :current="current"
    label="Seções da Cozinha"
    :operator-name="operatorName"
    :max="3"
    @select="onSelect"
    @lock="emit('lock')"
  />
</template>
