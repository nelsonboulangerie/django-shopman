<script setup lang="ts">
// Navegação da Cozinha na camada visual da suíte (prévia v4, `cozinha-estacao4.html`,
// pé da V6-KIT). Os itens são as estações da casa, pelo nome, cada uma levando à sua
// bancada, e a Saída, atalho para a coluna Saída do Gestor (`kdsSections`).
// No tablet deitado e no desktop, a barra lateral (`OperatorSuiteRail`): todas as
// estações, Saída, Painel de retirada; no pé, na ordem da v4 da Cozinha, Avisos ·
// Ajustes · Bloquear e o operador, sem traço (`footOrder="inbox-first"`). No celular e
// no tablet em pé, a barra inferior (`OperatorSectionBar`): a estação aberta (ou a deste
// dispositivo) à frente, outras estações, Saída e o "Mais" com o resto.
// `place` diz qual das duas peças este ponto do shell monta. Ajustes não é rota: abre o
// painel de Ajustes.
import { KDS_BAR_SECTIONS } from "~/presentation/sections";

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
    :max="KDS_BAR_SECTIONS"
    @select="onSelect"
    @lock="emit('lock')"
  />
</template>
