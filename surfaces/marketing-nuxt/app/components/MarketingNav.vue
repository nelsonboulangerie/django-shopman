<script setup lang="ts">
// Navegação do Marketing na camada visual da suíte (V4-MKT, pé da V6-KIT; modelo:
// `GestorNav`). O rail da suíte (`OperatorSuiteRail`, tablet deitado e desktop) tem
// dois andares: em cima a OPERAÇÃO (Decisões com o selo do que espera você, Agendados e
// Enviados); no pé, Ajustes (Campanhas, Modelos, Ofertas e cupons e Plataformas moram
// lá, numa segunda linha do cabeçalho), o traço e o pé da suíte: Avisos, Atalhos,
// Bloquear e o menu do operador. No celular e no tablet em pé as mesmas seções vão para
// a barra do polegar (`OperatorSectionBar`), como na prévia `marketing-decisoes4.html`,
// com o "Mais" do menu do operador. `place` diz qual das duas peças este ponto do shell
// monta.
//
// A barra do polegar mora no FIM da coluna de conteúdo (ver `app.vue`), nunca fixa na
// largura da janela: fixa, ela cobria o que estivesse à esquerda (a11y.spec.ts,
// 320×568, regressão de 03/10/2026).
//
// Avisos (MKT-01/T-13): a caixa do kit, a mesma em todo app. As decisões entram nela
// como UM resumo que leva à fila, não como uma segunda lista: decisão do dono de
// 03/10/2026 ("o sino abre a mesma fila"). A caixa pessoal (avisos de acesso) entra na
// outra aba, que o Marketing não tinha.
const props = defineProps<{
  place: "rail" | "bar";
  /** Rail: URL da Central. Rail e barra: operador ativo (o menu e o Bloquear). */
  hubUrl?: string;
  operatorName?: string;
}>();
const emit = defineEmits<{ lock: [] }>();
const { sections, activeSection } = useMarketingSections();

if (props.place === "rail") {
  const { decisionCount } = useMarketingDecisions();
  provideOperatorInboxAlerts(() => ({
    title: "Decisões",
    emptyText: "Nenhuma decisão esperando você.",
    count: decisionCount.value,
    items: decisionCount.value
      ? [{
          key: "decisions",
          tone: "warning" as const,
          message: decisionCount.value === 1 ? "1 decisão espera você." : `${decisionCount.value} decisões esperam você.`,
          meta: "O prazo mais curto primeiro.",
          href: "/",
          hrefLabel: "Abrir a fila de decisões",
        }]
      : [],
  }));
}
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
    :operator-name="operatorName"
    @lock="emit('lock')"
  />
</template>
