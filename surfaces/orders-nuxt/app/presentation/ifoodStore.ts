// Frases da loja no iFood — puras, testáveis sem runtime. O controle (ligar e
// desligar, com período) é o toggle "Ativo" do card do canal iFood, na aba Canais;
// o aviso da fila de Pedidos é o de todo canal de venda (`ChannelQueueSignal`).
// Copy: inequívoco primeiro (docs/reference/omotenashi-copy.md). Quem lê precisa saber,
// sem completar sentido, se o iFood está recebendo pedido AGORA e por quê.
import type { IFoodStoreProjection } from "~/types/ifoodStore";

/** Uma linha: o que o iFood está fazendo com os pedidos neste momento. */
export function ifoodStatusLine(store: IFoodStoreProjection): string {
  if (store.ifood_available === null) return store.ifood_status_label;
  const when = store.ifood_checked_at_display ? ` (conferido às ${store.ifood_checked_at_display})` : "";
  return `iFood: ${store.ifood_status_label.toLowerCase()}${when}`;
}

/** O ref do canal iFood — o card da aba Canais que carrega o estado da loja. */
export const IFOOD_CHANNEL_REF = "ifood";

