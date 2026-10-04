<script setup lang="ts">
// Navegação da Produção na camada visual da suíte (V4-PROD, pé da V6-KIT). O rail
// (`OperatorSuiteRail`, tablet deitado e desktop) leva o ciclo do lote com a tecla
// impressa sob o nome (Alt1 a Alt5, só com ponteiro fino), os Timers logo abaixo e, no
// pé, Receitas, Relatórios e o Letreiro; depois do traço, o pé da suíte: Avisos,
// Atalhos, Bloquear e o operador (`plano-porque4.html`). No celular e no tablet em pé,
// a barra do polegar (`OperatorSectionBar`): as quatro primeiras etapas e o "Mais", que
// guarda Qualidade, Timers, as ferramentas e o menu do operador.
//
// Avisos é UM item (T-01/T-13): os alertas da operação (`useAlerts`, OperatorAlert)
// entram na caixa do kit ao lado da caixa pessoal, que a Produção não tinha.
import { activeSectionKey } from "../../../operator-kit/app/presentation/appBar";
import { operatorAlertToInbox } from "../../../operator-kit/app/presentation/suiteChrome";

const props = defineProps<{
  place: "rail" | "bar";
  /** Rail: URL da Central. Rail e barra: operador ativo (o menu e o Bloquear). */
  hubUrl?: string;
  operatorName?: string;
}>();
const emit = defineEmits<{ lock: [] }>();
const { sections, phone } = useProductionSections();
const route = useRoute();
const phoneCurrent = computed(() => activeSectionKey(route.path, phone.value));

if (props.place === "rail") {
  const { alerts, activeCount, ack, isPending } = useAlerts();
  provideOperatorInboxAlerts(() => ({
    title: "Da operação",
    emptyText: "Nenhum alerta agora.",
    items: alerts.value.map(operatorAlertToInbox),
    count: activeCount.value,
    ack: (key) => {
      const alert = alerts.value.find((item) => item.pk === key);
      if (alert) return ack(alert);
    },
    isPending: (key) => isPending(Number(key)),
  }));
}
</script>

<template>
  <OperatorSuiteRail
    v-if="place === 'rail'"
    :sections="sections"
    label="Telas de produção"
    :hub-url="hubUrl"
    :operator-name="operatorName"
    dense-labels
    @lock="emit('lock')"
  />
  <OperatorSectionBar
    v-else
    :sections="phone"
    :current="phoneCurrent"
    label="Telas de produção"
    :operator-name="operatorName"
    @lock="emit('lock')"
  />
</template>
