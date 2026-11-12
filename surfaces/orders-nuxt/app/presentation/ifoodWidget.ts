// O widget oficial do iFood no Gestor (DEV-2026-018, issue #2321) — regras puras.
//
// A API do iFood não tem chat. O iFood oferece um widget (chat com o cliente,
// notificações, rastreio) que roda num iframe dele, preso ao canto da tela. A API
// JavaScript só tem `init`, `show`, `hide` e `ready`: não há "abrir a conversa do
// pedido X". Por isso o detalhe do pedido não abre o chat, ele diz onde o chat está.
import type { IFoodWidgetProjection } from "~/types/ifoodWidget";

export const IFOOD_WIDGET_SCRIPT = "https://widgets.ifood.com.br/widget.js";

/** off: a loja não ligou · loading: baixando/autorizando · ready · failed. */
export type IFoodWidgetState = "off" | "loading" | "ready" | "failed";

export interface IFoodWidgetInit {
  widgetId: string;
  merchantIds: string[];
}

/** Os parâmetros do `init`, ou null. O iFood perde a sessão do dispositivo quando o
 * widget é iniciado com parâmetro vazio: sem os dois, não se inicia. */
export function ifoodWidgetInit(
  projection: IFoodWidgetProjection | null | undefined,
): IFoodWidgetInit | null {
  const widgetId = projection?.widget_id?.trim() ?? "";
  const merchantIds = (projection?.merchant_ids ?? [])
    .map((id) => id.trim())
    .filter(Boolean)
    .slice(0, 10);
  if (!widgetId || !merchantIds.length) return null;
  return { widgetId, merchantIds };
}

export interface IFoodChatNotice {
  tone: "info" | "warning";
  icon: string;
  title: string;
  description: string;
}

/** O aviso do cartão "Chat com o cliente" no detalhe de um pedido do iFood. */
export function ifoodChatNotice(
  state: IFoodWidgetState,
  isIFoodOrder: boolean,
): IFoodChatNotice | null {
  if (!isIFoodOrder || state === "off") return null;
  if (state === "failed") {
    return {
      tone: "warning",
      icon: "i-lucide-message-circle-warning",
      title: "O chat do iFood não carregou",
      description:
        "As mensagens deste cliente não chegam aqui agora. Responda pelo Gestor do iFood.",
    };
  }
  if (state === "loading") {
    return {
      tone: "info",
      icon: "i-lucide-message-circle",
      title: "Chat do iFood",
      description: "Carregando o chat do iFood.",
    };
  }
  return {
    tone: "info",
    icon: "i-lucide-message-circle",
    title: "Chat do iFood",
    description:
      "As mensagens do cliente chegam no botão do iFood, no canto da tela. Responda por ele.",
  };
}
