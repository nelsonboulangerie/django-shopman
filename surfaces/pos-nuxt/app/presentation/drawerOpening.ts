/**
 * Abrir a gaveta de qualquer posto, com autoria (decisão do dono, 04/10/2026).
 *
 * No tablet, ao receber em dinheiro, a comanda fecha na mesa e o tablet guarda o
 * cartão "Dinheiro da comanda · troco · leve ao Balcão". Na frente da gaveta, o
 * atendente toca "Abrir gaveta do Balcão": o servidor grava a abertura no livro
 * (quem, de qual dispositivo, quando, por quê) e manda o pulso pelo relay ao
 * agente do Balcão. Nunca abre sozinha com o atendente ainda na mesa.
 *
 * Funções puras: o composable (`useDrawerOpening`) faz a rede; aqui só a
 * decisão e a frase. ⚠️ Nada aqui fala do valor esperado da gaveta nem do
 * veredito do fechamento: ele é cego, e o veredito é só do gerente.
 */
import { formatBRL } from "~/utils/posIntent";

/** O que aconteceu com o pedido de abrir. `offline` = nem chegou ao servidor. */
export type DrawerOpeningState =
  | "idle"
  | "sending"
  | "sent"
  | "failed"
  | "expired"
  | "uncertain"
  | "offline";

/** Por que a gaveta abre: venda em dinheiro (com o pedido) ou sem venda (com motivo). */
export type DrawerOpeningPurpose = "sale" | "no_sale";

/** O que o servidor diz do caminho de relay deste terminal (`POSProjection.drawer_relay`). */
export interface DrawerRelayCapability {
  available: boolean;
  online: boolean;
  terminal_label: string;
  reason: string;
}

/** O dinheiro da venda que ficou no tablet, esperando a gaveta. */
export interface PendingCashDrawer {
  orderRef: string;
  tabDisplay: string;
  changeQ: number;
}

/** Estados em que o gesto acabou e não deu: a tela oferece tentar de novo. */
export function drawerOpeningFailed(state: DrawerOpeningState): boolean {
  return state === "failed" || state === "expired" || state === "offline";
}

/** O botão some só quando a gaveta abriu; "sem confirmação" pede olhar antes de repetir. */
export function drawerOpeningDone(state: DrawerOpeningState): boolean {
  return state === "sent";
}

/**
 * A gaveta abre sozinha na venda em dinheiro SÓ neste caso: o dispositivo É o
 * Balcão (alcança o agente da própria máquina) e o dono deixou ligado no Admin.
 * No tablet nunca: abriria com o atendente ainda na mesa.
 */
export function autoOpensOnCashSale(opts: { localAgent: boolean; openOnCashSale: boolean }): boolean {
  return opts.localAgent && opts.openOnCashSale;
}

/** O título do cartão: "Dinheiro da comanda 6" ou "Dinheiro do pedido #1012". */
export function pendingCashTitle(pending: PendingCashDrawer): string {
  if (pending.tabDisplay) return `Dinheiro da comanda ${pending.tabDisplay}`;
  return `Dinheiro do pedido ${pending.orderRef}`;
}

/** A linha do cartão: "troco R$ 45,00 · leve ao Balcão". Sem troco, só o destino. */
export function pendingCashLine(pending: PendingCashDrawer, terminalLabel: string): string {
  const where = `leve ao ${terminalLabel || "Balcão"}`;
  if (pending.changeQ > 0) return `troco ${formatBRL(pending.changeQ)} · ${where}`;
  return where;
}

/** O botão: "Abrir gaveta do Balcão" (o nome é o do terminal no Admin). */
export function openDrawerLabel(terminalLabel: string): string {
  return `Abrir gaveta do ${terminalLabel || "Balcão"}`;
}

/** A frase do estado, sem fingir sucesso. O servidor manda a dele; isto cobre o resto. */
export function drawerOpeningMessage(state: DrawerOpeningState, terminalLabel: string, serverMessage = ""): string {
  const label = terminalLabel || "Balcão";
  if (serverMessage) return serverMessage;
  switch (state) {
    case "sending":
      return `Abrindo a gaveta do ${label}…`;
    case "sent":
      return `Gaveta do ${label} aberta.`;
    case "expired":
      return `O ${label} não respondeu: a gaveta não abriu. Confira o agente no PC do ${label} ou abra na chave.`;
    case "uncertain":
      return `O agente do ${label} recebeu o pedido e não confirmou. Olhe a gaveta antes de pedir de novo.`;
    case "offline":
      return "Sem conexão com o servidor: a gaveta não abriu. Abra na chave ou tente quando a rede voltar.";
    case "failed":
      return `A gaveta do ${label} não abriu.`;
    default:
      return "";
  }
}

/** A dica sob o botão: o gesto é para quem já está na frente da gaveta. */
export const OPEN_DRAWER_HINT = "Use quando estiver na frente da gaveta.";

/** Os motivos de abrir sem venda que viram um toque (o digitado cobre o resto). */
export const NO_SALE_REASONS = ["Troco", "Conferência"] as const;
