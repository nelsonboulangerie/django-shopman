import type { ReceiptLineStatus } from "~/types/purchase";

/**
 * A COR de cada estado do item, num lugar só.
 *
 * O estado quem decide é `receiptLineStatus` (projeção pura). Aqui fica só como
 * ele se pinta — e fica uma vez, porque a lista, o cabeçalho da gaveta e a
 * pílula de estado precisam concordar. Dois ternários em dois templates é como
 * a mesma linha aparecia âmbar num canto e verde no outro.
 */
export const RECEIPT_LINE_STATUS_ROW: Record<ReceiptLineStatus, string> = {
  blocked: "border-destructive/30 bg-destructive/5",
  attention: "border-warning/40 bg-warning/5",
  ready: "border-info/30 bg-info/5",
  checked: "border-success/40 bg-success/5",
};

export const RECEIPT_LINE_STATUS_BADGE: Record<ReceiptLineStatus, string> = {
  blocked: "border-destructive/30 bg-destructive/10 text-destructive",
  attention: "border-warning/30 bg-warning/10 text-warning",
  ready: "border-info/30 bg-info/10 text-info",
  checked: "border-success/25 bg-success/10 text-success",
};

/** Só a cor do texto/ícone — para o ícone da linha, que não leva fundo. */
export const RECEIPT_LINE_STATUS_TEXT: Record<ReceiptLineStatus, string> = {
  blocked: "text-destructive",
  attention: "text-warning",
  ready: "text-info",
  checked: "text-success",
};
