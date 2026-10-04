import { getCurrentInstance, onBeforeUnmount, onMounted, watch } from "vue";
import { gestorSections, gestorSettingsSections } from "~/presentation/gestorSections";
import { useOperatorResourceKey } from "./useOperatorResourceKey";

/** O que o quadro conta ao rail (selos de Pedidos e Saída, e se o posto é a Saída).
 *  Vale enquanto o quadro está montado; fora dele, `useGestorRailCounts` lê a contagem. */
export interface GestorRailState {
  onBoard: boolean;
  exitPost: boolean;
  intake: number;
  exit: number;
}

export function useGestorRail() {
  return useState<GestorRailState>("gestor-rail", () => ({ onBoard: false, exitPost: false, intake: 0, exit: 0 }));
}

/** Os selos fora do quadro: `orders/rail-counts/` a cada minuto enquanto `active()`.
 *  Leitura que falha não vira zero mentiroso: o selo some até a próxima dar certo. */
export function useGestorRailCounts(active: () => boolean) {
  const counts = useState<{ intake: number; exit: number }>("gestor-rail-counts", () => ({ intake: 0, exit: 0 }));
  if (import.meta.server || !getCurrentInstance()) return counts;
  let timer: ReturnType<typeof setInterval> | null = null;
  async function read() {
    if (!active()) return;
    try {
      counts.value = await $fetch<{ intake: number; exit: number }>("/api/v1/backstage/orders/rail-counts/");
    } catch {
      counts.value = { intake: 0, exit: 0 };
    }
  }
  onMounted(() => {
    void read();
    timer = setInterval(read, 60_000);
  });
  watch(active, (now) => { if (now) void read(); });
  onBeforeUnmount(() => { if (timer) clearInterval(timer); });
  return counts;
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
  // Fora do quadro (Catálogo, Clientes, Canais) os selos continuam (G26, v4
  // `catalogo-produto`: "Pedidos 10"): uma contagem leve, com a régua do quadro.
  const offBoard = useGestorRailCounts(() => !rail.value.onBoard);

  const input = computed(() => ({
    channelsAttention: attention.value?.label || "",
    canManageCustomers: customersAccess.value?.authorized === true,
    canManageWorkstations: workstationsAccess.value?.authorized === true,
    expeditesOnly: expeditesOnly.value,
    intakeCount: rail.value.onBoard ? rail.value.intake : offBoard.value.intake,
    exitCount: rail.value.onBoard ? rail.value.exit : offBoard.value.exit,
  }));
  const sections = computed(() => gestorSections(input.value));
  const settings = computed(() => gestorSettingsSections(input.value));
  // No quadro, quem diz se a tela é "Pedidos" ou "Saída" é a arrumação do posto.
  const route = useRoute();
  const current = computed(() => (route.path === "/" ? (rail.value.exitPost ? "exit" : "orders") : undefined));
  return { sections, settings, current };
}
