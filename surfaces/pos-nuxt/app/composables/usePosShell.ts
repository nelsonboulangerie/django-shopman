// O que o shell do PDV (`OperatorSuiteShell`) sabe das telas: as seções, qual está
// acesa e o que fazem as duas seções que não são rota (Comandas e Tela do cliente).
//
// Uma leitura por app, montada UMA vez no shell (fase 2: "navegação montada uma vez no
// layout", WP-FASE2 §7): as Encomendas (selo e permissão, com o tempo real delas), as
// comandas em uso (selo das Comandas), o caixa (ponto do Caixa) e a sonda do agente do
// balcão (sinal do Terminal). Antes cada página remontava o rail e a barra do polegar.
import { toast } from "vue-sonner";

import type { POSProjection } from "~/types/pos";
import { posCurrentSection, posSections } from "~/presentation/sections";
import { terminalHealthRows, terminalOverallStatus } from "~/presentation/terminalHealth";

/**
 * "Comandas" pedido de dentro da tela da venda: a rota já é `/`, então não há
 * navegação; a tela observa este número e volta ao quadro guardando a comanda.
 */
export function usePosBoardRequest() {
  return useState<number>("pos-board-request", () => 0);
}

export function usePosShell(pos: Ref<POSProjection | null>) {
  const route = useRoute();
  const tabs = usePosTabsState();
  const preorders = usePosPreordersRail();
  const { probe } = useAgentHealth(computed(() => pos.value));

  const terminal = computed(() => {
    if (!pos.value) return undefined;
    return terminalOverallStatus(
      terminalHealthRows(
        pos.value.terminal_components,
        { status: pos.value.fiscal_status, label: pos.value.fiscal_label, message: pos.value.fiscal_message },
        probe.value,
      ),
    );
  });

  const sections = computed(() =>
    posSections({
      tabs: tabs.value,
      hasOpenCashSession: Boolean(pos.value?.has_open_cash_session),
      preorders: { allowed: preorders.allowed.value, badge: preorders.badge.value },
      terminal: terminal.value,
    }),
  );
  const current = computed(() => posCurrentSection(route.path));

  const boardRequest = usePosBoardRequest();
  const customerDisplayWindow = useCustomerDisplayWindow();

  function select(key: string) {
    if (key === "board") {
      if (route.path === "/") boardRequest.value += 1;
      else void navigateTo("/");
    } else if (key === "display") {
      if (!customerDisplayWindow.open()) {
        toast.error("O navegador bloqueou a Tela do Cliente.", {
          description: "Permita pop-ups para este site e tente novamente.",
        });
      }
    }
  }

  return { sections, current, select };
}
