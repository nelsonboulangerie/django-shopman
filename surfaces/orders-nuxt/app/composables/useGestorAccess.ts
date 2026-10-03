import { useOperatorResourceKey } from "./useOperatorResourceKey";
// Quem está operando GERENCIA pedidos, ou só EXPEDE? (SUITE-UX §15: uma Saída só,
// no Gestor.) O Gestor deixa entrar as duas pessoas (`GESTOR_SURFACE_PERM`); quem só
// expede opera a coluna Saída e não ganha o resto do Gestor (detalhe do pedido,
// Catálogo, Canais, Clientes, Histórico). A pergunta é a mesma da antessala, sobre
// quem está operando: o servidor responde sim/não, sem listar permissões. Troca de
// operador relê. O servidor recusa de todo modo; isto só evita oferecer o que ele
// vai recusar.

/** A permissão da superfície: quem gerencia pedidos OU quem expede (a trava é a primeira). */
export const GESTOR_SURFACE_PERM = "shop.manage_orders|backstage.operate_kds";

export function useGestorAccess() {
  const { data: session } = useNuxtData<{ operator?: { id: number } }>("operator-session");
  const operatorId = computed(() => session.value?.operator?.id ?? null);
  const { data } = useFetch<{ authorized?: boolean }>("/api/v1/backstage/operator/session/", {
    key: useOperatorResourceKey("manage-orders-access"),
    query: { perm: "shop.manage_orders" },
    server: true,
    watch: [operatorId],
  });
  // Só uma resposta "não" encolhe o Gestor. Enquanto a leitura não chega, a tela
  // fica como sempre foi para quem gerencia (o caso comum), e o servidor segue
  // recusando o que não é de quem só expede.
  const expeditesOnly = computed(() => data.value?.authorized === false);
  const canManageOrders = computed(() => !expeditesOnly.value);
  return { canManageOrders, expeditesOnly };
}
