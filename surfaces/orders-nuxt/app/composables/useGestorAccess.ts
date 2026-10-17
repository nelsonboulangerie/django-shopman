import {
  gestorLandingPath,
  type GestorSurfaceRole,
} from "~/presentation/gestorAccess";
// O Gestor atende três trabalhos sem misturar grants: gestão de pedidos, posto de
// Saída e catálogo diário. A antessala devolve a persona efetiva e a landing; cada
// endpoint continua conferindo sua capability. Assim catálogo não herda Pedidos ou
// Clientes, e quem só expede continua restrito à operação da Saída.

/** A porta comum: pedidos, posto de saída ou catálogo diário. */
export const GESTOR_SURFACE_PERM =
  "shop.manage_orders|backstage.operate_kds|shop.manage_catalog";

export function useGestorAccess() {
  const { data: session } = useNuxtData<{
    operator?: { id: number };
    surface_role?: GestorSurfaceRole | null;
    landing_path?: string;
  }>(
    "operator-session",
  );
  const role = computed<GestorSurfaceRole | null>(
    () => session.value?.surface_role ?? null,
  );
  const canManageOrders = computed(() => role.value === "orders");
  const expeditesOnly = computed(() => role.value === "expedition");
  const catalogOnly = computed(() => role.value === "catalog");
  const landingPath = computed(() =>
    gestorLandingPath(role.value, session.value?.landing_path),
  );
  return { role, canManageOrders, expeditesOnly, catalogOnly, landingPath };
}
