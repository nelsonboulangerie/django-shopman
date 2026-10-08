<script setup lang="ts">
// Navegação do PDV na camada visual da suíte (onda V4, prévia `pos-sale4.html`).
//
// `place="rail"` (padrão, do tablet para cima): o `OperatorSuiteRail` do kit com as
// seções do balcão dentro dele. Em cima a operação (Comandas F2, Encomendas, Caixa,
// Tela do cliente); no pé, Terminal (a saúde e o Atualizar) e, depois do traço, o pé
// da suíte (kit, V6-KIT): Avisos, Atalhos, Bloquear e o operador. O selo do app volta à
// Central; tema, giro, capacidade e ocultar a barra moram no menu das iniciais.
//
// `place="bar"` (celular e tablet em pé): a barra do polegar (`OperatorSectionBar`) com
// as MESMAS seções e o "Mais" do menu do operador, no fim da coluna de conteúdo. Ela lê as seções que o rail publica: a
// leitura das Encomendas (com o tempo real dela) existe uma vez só por tela.
import type { POSProjection } from "~/types/pos";
import { posCurrentSection, posSections, type PosView } from "~/presentation/sections";

const props = withDefaults(defineProps<{
  place?: "rail" | "bar";
  /** Rail: a Projection do terminal (comandas, caixa, saúde). */
  pos?: POSProjection | null;
  hasOpenCashSession?: boolean;
  operatorName?: string;
  pending?: boolean;
  /** qual tela de trabalho está ativa, para acender a seção correspondente. */
  view?: PosView;
}>(), {
  place: "rail",
  pos: null,
  hasOpenCashSession: false,
  operatorName: "",
  pending: false,
  view: "board",
});

const emit = defineEmits<{
  board: [];
  cash: [];
  display: [];
  lock: [];
  refresh: [];
}>();

const hubUrl = useRuntimeConfig().public.operatorHubUrl as string;
const shared = usePosSectionsState();
const tabs = usePosTabsState();

// Encomendas: o item só existe para quem pode ler pedidos, e o selo conta as de
// hoje ainda por entregar. A leitura e o tempo real moram no composable, e só o
// rail os liga (a barra do polegar lê o que o rail publicou).
const preorders = props.place === "rail" ? usePosPreordersRail() : null;

if (preorders) {
  watchEffect(() => {
    const sections = posSections({
      tabs: tabs.value,
      hasOpenCashSession: props.hasOpenCashSession,
      preorders: {
        allowed: preorders.allowed.value,
        badge: preorders.badge.value,
      },
    });
    shared.value = { sections, current: posCurrentSection(props.view) };
  });
}

function onSelect(key: string) {
  if (key === "board") emit("board");
  else if (key === "cash") emit("cash");
  else if (key === "display") emit("display");
}
</script>

<template>
  <OperatorSuiteRail
    v-if="place === 'rail'"
    :sections="shared.sections"
    :current="shared.current"
    label="Seções do PDV"
    print-shortcuts
    :hub-url="hubUrl"
    :operator-name="operatorName || undefined"
    touch-label="none"
    data-pos-rail
    @select="onSelect"
    @lock="emit('lock')"
  >
    <template #foot>
      <!-- Terminal: a saúde da estação (impressora, gaveta, agente, fiscal) e o
           Atualizar, lado a lado no mesmo painel, como o Pablo pediu (17/09). -->
      <PosTerminalHealth
        v-if="pos"
        :pos="pos"
        variant="suite"
        :refreshing="pending"
        @refresh="emit('refresh')"
      />
    </template>
  </OperatorSuiteRail>
  <OperatorSectionBar
    v-else-if="shared.sections.length"
    :sections="shared.sections"
    :current="shared.current"
    label="Seções do PDV"
    :operator-name="operatorName || undefined"
    @select="onSelect"
    @lock="emit('lock')"
  >
    <!-- O Terminal no "Mais" (P27): a saúde da estação e o Atualizar. -->
    <template v-if="pos" #more>
      <PosTerminalHealth :pos="pos" variant="sheet" :refreshing="pending" @refresh="emit('refresh')" />
    </template>
  </OperatorSectionBar>
</template>
