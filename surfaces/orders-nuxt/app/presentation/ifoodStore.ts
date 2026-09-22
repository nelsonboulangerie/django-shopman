// Frases da loja no iFood — puras, testáveis sem runtime. O controle (pausar/retomar)
// mora no card do canal iFood, na aba Canais; a aba Pedidos só mostra o SINAL, e só
// quando ele muda o que entra na fila.
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

/** O ref do canal iFood — o card da aba Canais que carrega o estado da loja. */
export const IFOOD_CHANNEL_REF = "ifood";

/** A chave de foco do card do iFood (`data-focus-target` + `?focus=` na URL). */
export const IFOOD_FOCUS_KEY = "ifood";

/**
 * O sinal da aba Pedidos: uma frase quando o iFood não está entregando pedidos como
 * a loja espera — pausado, com a pausa recusada, ou divergente. Estado normal: "".
 * A recusa só vale enquanto dura a janela que o gestor pediu; depois dela, a fila
 * já não tem o que esperar da pausa (o card do canal segue contando o desfecho).
 */
export function queueSignal(store: IFoodStoreProjection | null, now: Date = new Date()): string {
  if (!store?.enabled) return "";
  const pause = store.pause;
  if (pause?.state === "active") return `iFood pausado até ${pause.ends_at_display} — ${pause.reason}`;
  if (pause) return ifoodStatusLine(store);
  if (store.diverges) {
    if (store.ifood_available === false && store.shop_open) return "iFood fechado com a loja aberta: nenhum pedido do iFood entra";
    if (store.ifood_available === true && !store.shop_open) return "iFood recebendo pedidos com a loja fechada";
    return `iFood: ${store.ifood_status_label.toLowerCase()}, diferente do esperado`;
  }
  const last = store.last_pause;
  if (last?.state === "failed" && Date.parse(last.ends_at) > now.getTime()) {
    const when = last.requested_at_display ? ` às ${last.requested_at_display}` : "";
    return `O iFood recusou a pausa pedida${when}`;
  }
  return "";
}

/** A pausa está em curso (pedida, em vigor ou sendo retomada)? */
export function pauseInFlight(store: IFoodStoreProjection | null): boolean {
  const state = store?.pause?.state;
  return state === "pending_create" || state === "pending_remove";
}
