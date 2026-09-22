// Frases da loja no iFood — puras, testáveis sem runtime. O controle (ligar e
// desligar, com período) é o toggle "Ativo" do card do canal iFood, na aba Canais;
// a aba Pedidos só mostra o SINAL, e só quando ele muda o que entra na fila.
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

/** A chave de foco do card do iFood (`data-focus-target` + `?focus=` na URL). */
export const IFOOD_FOCUS_KEY = "ifood";

/**
 * O sinal da aba Pedidos: uma frase quando o iFood não está entregando pedidos como
 * a loja espera — desligado no Gestor ou divergente. Estado normal: "".
 */
export function queueSignal(store: IFoodStoreProjection | null): string {
  if (!store?.enabled) return "";
  if (store.channel_off) return "iFood desligado no Gestor: nenhum pedido do iFood entra";
  if (store.diverges) {
    if (store.ifood_available === false && store.shop_open) return "iFood fechado com a loja aberta: nenhum pedido do iFood entra";
    if (store.ifood_available === true && !store.shop_open) return "iFood recebendo pedidos com a loja fechada";
    return `iFood: ${store.ifood_status_label.toLowerCase()}, diferente do esperado`;
  }
  return "";
}
