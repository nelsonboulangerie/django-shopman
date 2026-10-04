<script setup lang="ts">
// Navegação do PDV na camada visual da suíte (onda V4, prévia `pos-sale4.html`).
//
// `place="rail"` (padrão, do tablet para cima): o `OperatorSuiteRail` do kit com as
// seções do balcão dentro dele. Em cima a operação (Comandas F2, Encomendas, Caixa,
// Tela do cliente); no pé, Terminal (a saúde e o Atualizar), Avisos, Atalhos,
// Bloquear e o operador. O selo do app volta à Central; tema, giro e ocultar a barra
// moram no menu das iniciais (kit).
//
// `place="bar"` (celular): a barra do polegar (`OperatorSectionBar`) com as MESMAS
// seções, no fim da coluna de conteúdo. Ela lê as seções que o rail publica: a
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
  /** A tela tem a ajuda de atalhos (a venda): mostra "Atalhos" no pé. */
  shortcuts?: boolean;
}>(), {
  place: "rail",
  pos: null,
  hasOpenCashSession: false,
  operatorName: "",
  pending: false,
  view: "board",
  shortcuts: false,
});

const emit = defineEmits<{
  board: [];
  cash: [];
  display: [];
  lock: [];
  refresh: [];
  shortcuts: [];
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
        ariaLabel: preorders.ariaLabel.value,
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

const isPhone = useMediaQuery("(max-width: 767.98px)");
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
    data-pos-rail
    @select="onSelect"
    @lock="emit('lock')"
  >
    <template v-if="!isPhone" #foot>
      <!-- Terminal: a saúde da estação (impressora, gaveta, agente, fiscal) e o
           Atualizar, lado a lado no mesmo painel, como o Pablo pediu (17/09). -->
      <PosTerminalHealth
        v-if="pos"
        :pos="pos"
        variant="suite"
        :refreshing="pending"
        @refresh="emit('refresh')"
      />
      <div class="my-1 h-px w-9 shrink-0 bg-rail-foreground/20" aria-hidden="true" />
      <NotificationBell placement="rail" />
      <RailSection
        v-if="shortcuts"
        icon="lucide:keyboard"
        label="Atalhos"
        aria-label="Atalhos do teclado"
        shortcut="?"
        data-pos-rail-shortcuts
        @activate="emit('shortcuts')"
      />
    </template>
  </OperatorSuiteRail>
  <OperatorSectionBar
    v-else-if="shared.sections.length"
    :sections="shared.sections"
    :current="shared.current"
    label="Seções do PDV"
    @select="onSelect"
  />
</template>
