// O contexto que o chamado do Gestor leva (#2515, ADR-045): o app, a tela e, com um
// pedido aberto, a ref dele no `focus` do kit ("Em foco" no chamado). Refs, nunca
// PII: o servidor já sabe quem abriu.
import { operatorSupportContext } from "../../../operator-kit/app/presentation/support";

/** A rota da página do pedido (`pages/[ref].vue`): o pedido em foco. */
const ORDER_ROUTE_NAME = "ref";

export function gestorSupportContext(route: {
  path: string;
  name?: unknown;
  params?: Record<string, unknown>;
}): Record<string, unknown> {
  const ref = route.name === ORDER_ROUTE_NAME ? String(route.params?.ref ?? "").trim() : "";
  return operatorSupportContext("orders", route.path, ref ? { focus: { kind: "order", ref } } : {});
}
