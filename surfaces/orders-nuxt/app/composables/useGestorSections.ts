import { gestorSections, gestorSettingsSections } from "~/presentation/gestorSections";
import { useOperatorResourceKey } from "./useOperatorResourceKey";

/** O que o quadro conta ao rail (selos de Pedidos e Saída, e se o posto é a Saída).
 *  Só vale enquanto o quadro está montado: fora dele os selos somem, em vez de mentir. */
export interface GestorRailState {
  onBoard: boolean;
  exitPost: boolean;
  intake: number;
  exit: number;
}

export function useGestorRail() {
  return useState<GestorRailState>("gestor-rail", () => ({ onBoard: false, exitPost: false, intake: 0, exit: 0 }));
}

// As seções do rail (operação + Ajustes) e as do andar Ajustes. As perguntas de
// permissão são as mesmas da antessala, sobre quem está operando: o servidor responde
// sim/não, sem listar permissões. Troca de operador relê.
export function useGestorSections() {
  // Canal ou feed desligado, pausado ou divergente: um ponto âmbar em Ajustes e em
  // Canais. Estado normal não mostra nada.
  const { attention } = useChannelAttention();
  const { data: session } = useNuxtData<{ operator?: { id: number } }>("operator-session");
  const operatorId = computed(() => session.value?.operator?.id ?? null);
  // Clientes só para quem pode usar a seção (`shop.manage_customers`, 24/09/2026).
  const { data: customersAccess } = useFetch<{ authorized?: boolean }>("/api/v1/backstage/operator/session/", {
    key: useOperatorResourceKey("customers-access"),
    query: { perm: "shop.manage_customers" },
    server: true,
    watch: [operatorId],
  });
  // Postos só para quem gere operadores (vincula dispositivos e cadastra postos).
  const { data: workstationsAccess } = useFetch<{ authorized?: boolean }>("/api/v1/backstage/operator/session/", {
    key: useOperatorResourceKey("workstations-access"),
    query: { perm: "cashman.manage_operators" },
    server: true,
    watch: [operatorId],
  });
  const { expeditesOnly } = useGestorAccess();
  const rail = useGestorRail();

  const input = computed(() => ({
    channelsAttention: attention.value?.label || "",
    canManageCustomers: customersAccess.value?.authorized === true,
    canManageWorkstations: workstationsAccess.value?.authorized === true,
    expeditesOnly: expeditesOnly.value,
    intakeCount: rail.value.onBoard ? rail.value.intake : 0,
    exitCount: rail.value.onBoard ? rail.value.exit : 0,
  }));
  const sections = computed(() => gestorSections(input.value));
  const settings = computed(() => gestorSettingsSections(input.value));
  // No quadro, quem diz se a tela é "Pedidos" ou "Saída" é a arrumação do posto.
  const route = useRoute();
  const current = computed(() => (route.path === "/" ? (rail.value.exitPost ? "exit" : "orders") : undefined));
  return { sections, settings, current };
}
