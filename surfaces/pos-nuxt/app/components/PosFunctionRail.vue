<script setup lang="ts">
// Rail do PDV = o `OperatorRail` canônico (kit) + as funções do balcão nos slots. A
// espinha, os 3 estados, o botão do Shopman Apps, operador/travar e tema vêm do kit — mesma
// gramática das outras superfícies. Aqui ficam só as funções do PDV: ir às Comandas,
// abrir o caixa, as Encomendas, a tela do cliente, saúde do terminal e atualizar. É a adoção-prova do shell (WP-B0.2): o
// POS é a origem do rail, então é onde o padrão nasce de pé.
import type { POSProjection } from "~/types/pos";

defineProps<{
  pos: POSProjection;
  hasOpenCashSession: boolean;
  operatorName: string;
  pending: boolean;
  /** qual tela de trabalho está ativa, para acender o item correspondente. */
  view: "board" | "sale" | "checkout" | "session" | "preorders";
}>();

const emit = defineEmits<{
  board: [];
  cash: [];
  display: [];
  lock: [];
  refresh: [];
}>();

const hubUrl = useRuntimeConfig().public.operatorHubUrl as string;

// Encomendas: o item só existe para quem pode ler pedidos, e o selo conta as de
// hoje ainda por entregar. A leitura e o tempo real moram no composable.
const preorders = usePosPreordersRail();
</script>

<template>
  <OperatorRail
    :hub-url="hubUrl"
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
      <!-- Encomendas: a porta da seção (decisão do dono, 26/09), no lugar em que
           morava "Fichas de pedido" — que virou o card Via Pedido – painel da casa
           das Encomendas. Navega sozinho: nenhuma tela tem estado a desfazer antes
           de sair para lá. -->
      <RailItem
        v-if="preorders.allowed.value"
        icon="package"
        label="Encomendas"
        :aria-label="preorders.ariaLabel.value"
        :badge="preorders.badge.value"
        :active="view === 'preorders'"
        data-rail-preorders
        @activate="navigateTo('/preorders')"
      />
      <!-- Tela do cliente: o segundo monitor da MESMA máquina e navegador. Morava só
           no cabeçalho da antessala de caixa, onde só se chega abrindo o turno — e a
           janela, uma vez fechada sem querer, não tinha volta de dentro da venda.
           Aqui ela é função do balcão, alcançável de qualquer tela. -->
      <RailItem
        icon="monitor"
        label="Tela do cliente"
        aria-label="Abrir a tela do cliente no segundo monitor"
        @activate="emit('display')"
      />
    </template>

    <template #status>
      <!-- Ordem pedida pelo Pablo (17/09): Atualizar primeiro, para a saúde do
           terminal ficar colada na capacidade do servidor, que o OperatorRail põe
           logo depois deste slot — as duas leituras de "como está" lado a lado. -->
      <RailItem
        icon="refresh-cw"
        label="Atualizar"
        :busy="pending"
        @activate="emit('refresh')"
      />
      <!-- O card recebe a Projection inteira porque ele mesmo sonda o agente do
           balcão (useAgentHealth) e promove o resultado às linhas. -->
      <PosTerminalHealth v-if="pos" compact :pos="pos" />
    </template>
  </OperatorRail>
</template>
