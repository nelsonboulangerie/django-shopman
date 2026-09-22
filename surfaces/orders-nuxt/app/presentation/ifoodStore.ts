// Frases do menu "A loja no iFood" — puras, testáveis sem runtime.
// Copy: inequívoco primeiro (docs/reference/omotenashi-copy.md). Quem lê precisa saber,
// sem completar sentido, se o iFood está recebendo pedido AGORA e por quê.
import type { IFoodPause, IFoodStoreProjection } from "~/types/ifoodStore";

/** Uma linha: o que o iFood está fazendo com os pedidos neste momento. */
export function ifoodStatusLine(store: IFoodStoreProjection): string {
  const pause = store.pause;
  if (pause?.state === "pending_create") return "Pedindo a pausa ao iFood…";
  if (pause?.state === "pending_remove") return "Retomando os pedidos no iFood…";
  if (pause?.state === "active") return `iFood pausado até ${pause.ends_at_display}`;
  if (store.ifood_available === null) return store.ifood_status_label;
  const when = store.ifood_checked_at_display ? ` (conferido às ${store.ifood_checked_at_display})` : "";
  return `iFood: ${store.ifood_status_label.toLowerCase()}${when}`;
}

/** Quem pausou, por quê e quando — a trilha da pausa em curso. */
export function pauseTrail(pause: IFoodPause): string {
  const who = pause.requested_by ? ` por ${pause.requested_by}` : "";
  const when = pause.requested_at_display ? ` às ${pause.requested_at_display}` : "";
  return `Motivo: ${pause.reason}. Pausado${who}${when}.`;
}

/** A pausa que o iFood recusou fica na tela, com o motivo da recusa. */
export function refusedPauseLine(store: IFoodStoreProjection): string {
  const last = store.last_pause;
  if (!last || last.state !== "failed") return "";
  return last.error || "O iFood recusou a pausa.";
}

/** O ponto no botão de mais opções: só quando há algo que o gestor precisa ver. */
export function menuNeedsAttention(store: IFoodStoreProjection | null): boolean {
  if (!store?.enabled) return false;
  return Boolean(store.diverges || store.pause || refusedPauseLine(store));
}

/** A pausa está em curso (pedida, em vigor ou sendo retomada)? */
export function pauseInFlight(store: IFoodStoreProjection | null): boolean {
  const state = store?.pause?.state;
  return state === "pending_create" || state === "pending_remove";
}
