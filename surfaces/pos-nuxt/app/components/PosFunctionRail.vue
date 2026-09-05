<script setup lang="ts">
// Rail do PDV = o `OperatorRail` canônico (kit) + as funções do balcão nos slots. A
// espinha, os 3 estados, o botão Central, operador/travar e tema vêm do kit — mesma
// gramática das outras superfícies. Aqui ficam só as funções do PDV: ir às Comandas,
// abrir o caixa, saúde do terminal e atualizar. É a adoção-prova do shell (WP-B0.2): o
// POS é a origem do rail, então é onde o padrão nasce de pé.
import type { POSProjection } from "~/types/pos";

defineProps<{
  pos: POSProjection;
  hasOpenCashSession: boolean;
  operatorName: string;
  pending: boolean;
  /** qual tela de trabalho está ativa, para acender o item correspondente. */
  view: "board" | "sale" | "checkout" | "session" | "tickets";
}>();

const emit = defineEmits<{
  board: [];
  cash: [];
  tickets: [];
  lock: [];
  refresh: [];
}>();

const hubUrl = useRuntimeConfig().public.operatorHubUrl as string;
</script>

<template>
  <OperatorRail
    app-icon="banknote"
    app-label="PDV"
    :central-url="hubUrl"
    :operator-name="operatorName || undefined"
    @lock="emit('lock')"
  >
    <template #nav>
      <RailItem
        icon="notebook-tabs"
        label="Comandas"
        :active="view === 'board'"
        @activate="emit('board')"
      />
      <RailItem
        icon="wallet"
        :label="hasOpenCashSession ? 'Sessão de caixa' : 'Abrir caixa'"
        :aria-label="hasOpenCashSession ? 'Sessão de caixa' : 'Abrir caixa'"
        :active="view === 'session'"
        :attention="!hasOpenCashSession"
        @activate="emit('cash')"
      />
      <!-- Filipetas: o pedido remoto virando papel para o painel de parede. Mora
           no rail do PDV porque a bobina e o agente do balcão moram aqui. -->
      <RailItem
        icon="printer"
        label="Filipetas"
        :active="view === 'tickets'"
        @activate="emit('tickets')"
      />
    </template>

    <template #status>
      <!-- O card recebe a Projection inteira porque ele mesmo sonda o agente do
           balcão (useAgentHealth) e promove o resultado às linhas. -->
      <PosTerminalHealth v-if="pos" compact :pos="pos" />
      <RailItem
        icon="refresh-cw"
        label="Atualizar"
        :busy="pending"
        @activate="emit('refresh')"
      />
    </template>
  </OperatorRail>
</template>
