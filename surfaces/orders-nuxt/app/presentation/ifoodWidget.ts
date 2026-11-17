// O widget oficial do iFood no Gestor (DEV-2026-019, issue #2321) — regras puras.
//
// A API do iFood não tem chat. O iFood oferece um widget (chat com o cliente,
// notificações, rastreio) que roda num iframe dele, preso ao canto da tela. A API
// JavaScript só tem `init`, `show`, `hide` e `ready`: não há "abrir a conversa do
// pedido X". Por isso o detalhe do pedido não abre o chat, ele diz onde o chat está.
import type { IFoodWidgetProjection } from "~/types/ifoodWidget";

export const IFOOD_WIDGET_SCRIPT = "https://widgets.ifood.com.br/widget.js";

/** Quanto o Gestor espera o `init` do iFood antes de dizer que o chat não carregou. */
export const IFOOD_WIDGET_INIT_TIMEOUT_MS = 30_000;

/** off: a loja não ligou · loading: baixando/autorizando · ready · failed. */
export type IFoodWidgetState = "off" | "loading" | "ready" | "failed";

export interface IFoodWidgetInit {
  widgetId: string;
  merchantIds: string[];
  /** Sempre falso: quem decide mostrar o botão é `ifoodWidgetVisible`. */
  autoShow: false;
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
  return { widgetId, merchantIds, autoShow: false };
}

/** O botão do iFood aparece? (decisão do dono, 14/11, DEV-2026-023)
 *
 * Só enquanto houver pedido iFood aberto e ainda não entregue: sem pedido em
 * curso ele não polui o Gestor; com pedido em curso, a mensagem nova do cliente
 * aparece em qualquer tela. No detalhe de um pedido iFood ele aparece sempre,
 * porque o cliente também escreve depois da entrega ("faltou um item"). Esconder
 * o botão esconde também os avisos de mensagem nova do iFood. */
export function ifoodWidgetVisible(
  hasOrderInProgress: boolean,
  viewingIFoodOrder: boolean,
): boolean {
  return hasOrderInProgress || viewingIFoodOrder;
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

/** A margem de baixo do botão do iFood, configurada no Portal do Parceiro (widget
 * "Shopman Gestor de pedidos", 14/11/2026). O widget não deixa o Gestor mudá-la. */
export const IFOOD_WIDGET_MARGIN_Y = 96;
/** O respiro entre o botão do iFood e a barra mais alta da base. */
export const IFOOD_WIDGET_GAP = 12;
/** Uma região de toque mais alta que isto é a conversa aberta, não o botão. */
export const IFOOD_WIDGET_PANEL_MIN_HEIGHT = 200;

/**
 * Quanto o widget do iFood sobe para não tampar o que fica na base (a barra das
 * seções, a barra de ação da tela, a área segura do celular). O botão mora a
 * `IFOOD_WIDGET_MARGIN_Y` do fundo; a base ocupa `obstruction` px. Com a conversa
 * aberta, nada sobe: o painel é alto e perderia o topo.
 */
export function ifoodWidgetLift(obstruction: number, panelOpen: boolean): number {
  if (panelOpen) return 0;
  return Math.max(0, Math.ceil(obstruction + IFOOD_WIDGET_GAP - IFOOD_WIDGET_MARGIN_Y));
}
