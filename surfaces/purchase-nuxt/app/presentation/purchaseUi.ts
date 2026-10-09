// O estado do insumo e do pedido de compra em selo (`NuxtBadge`, sem `variant`: o tema
// dá `soft`). Uma cor e uma palavra por estado, em toda tela do Compras.
import type { MaterialTone, PurchaseRequestStatus } from "~/types/purchase";

type BadgeColor = "neutral" | "primary" | "info" | "success" | "warning" | "error";

export const TONE_BADGE: Record<MaterialTone, BadgeColor> = {
  ok: "success",
  watch: "warning",
  urgent: "error",
};

export const TONE_LABEL: Record<MaterialTone, string> = {
  ok: "Em ordem",
  watch: "Revisar",
  urgent: "Comprar",
};

/** A ordem de "Situação" ao ordenar: o que pede compra primeiro. */
export const TONE_RANK: Record<MaterialTone, number> = { urgent: 0, watch: 1, ok: 2 };

export const REQUEST_BADGE: Record<PurchaseRequestStatus, BadgeColor> = {
  review: "warning",
  approved: "info",
  sent: "success",
};

export const REQUEST_LABEL: Record<PurchaseRequestStatus, string> = {
  review: "Revisar",
  approved: "Pronto para enviar",
  sent: "Enviado",
};

/** "1 insumo", "3 insumos". */
export function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}
