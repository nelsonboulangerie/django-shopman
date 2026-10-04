<script setup lang="ts">
// Navegação do Gestor (UX-KIT-V1, desenho da v4 desde o UX-KIT-V2, pé da V6-KIT). O rail
// da suíte (`OperatorSuiteRail`, tablet deitado e desktop) tem dois andares, como na
// prévia `gestor-fila4.html`: em cima a OPERAÇÃO (Pedidos e Saída, com o rótulo do grupo
// e os selos); no pé, Ajustes (Histórico, Catálogo, Clientes, Canais e Postos moram lá),
// o traço, e o pé da suíte: Avisos, Atalhos, Bloquear e o operador. No celular e no
// tablet em pé as mesmas seções vão para a barra do polegar (`OperatorSectionBar`, com o
// "Mais"). `place` diz qual das duas peças este ponto do shell monta.
//
// Avisos é UM item (K01): os alertas de pedido (`useAlerts`, OperatorAlert com escopo
// `orders`) entram na caixa do kit ao lado da caixa pessoal. Quem registra é o rail,
// montado uma vez por tela.
import { operatorAlertToInbox } from "../../../operator-kit/app/presentation/suiteChrome";

const props = defineProps<{
  place: "rail" | "bar";
  /** Rail: URL da Central. Rail e barra: operador ativo (o menu e o Bloquear). */
  hubUrl?: string;
  operatorName?: string;
}>();
const emit = defineEmits<{ lock: [] }>();
const { sections, current } = useGestorSections();

if (props.place === "rail") {
  const { alerts, activeCount, ack } = useAlerts();
  provideOperatorInboxAlerts(() => ({
    title: "Da operação",
    emptyText: "Nenhum alerta de pedido agora.",
    items: alerts.value.map(operatorAlertToInbox),
    count: activeCount.value,
    ack: (key) => {
      const alert = alerts.value.find((item) => item.pk === key);
      if (alert) return ack(alert);
    },
  }));
}
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
  />
  <OperatorSectionBar
    v-else
    :sections="sections"
    :current="current"
    label="Seções do Gestor"
    :operator-name="operatorName"
    @lock="emit('lock')"
  />
</template>
