import type { ReceiptLineStatus } from "~/types/purchase";

/**
 * A COR de cada estado do item, num lugar só.
 *
 * O estado quem decide é `receiptLineStatus` (projeção pura). Aqui fica só como
 * ele se pinta — e fica uma vez, porque a lista, o cabeçalho da gaveta e a
 * pílula de estado precisam concordar. Dois ternários em dois templates é como
 * a mesma linha aparecia âmbar num canto e verde no outro.
 */
// Cartão da linha (prévia v3 do Receber): o que trava tem a borda no tom e fundo de
// cartão; o que está feito ganha o verde leve. A cor nunca fala sozinha: o estado
// também está escrito na etiqueta e o próximo passo, na própria linha.
export const RECEIPT_LINE_STATUS_ROW: Record<ReceiptLineStatus, string> = {
  blocked: "border-destructive/45 bg-card",
  attention: "border-warning/45 bg-card",
  ready: "border-border bg-card",
  matched: "border-success/30 bg-success/5",
  checked: "border-success/30 bg-success/5",
};

// A etiqueta cheia da suíte (`pill-*` do kit): tinta de 12% e texto no tom.
export const RECEIPT_LINE_STATUS_BADGE: Record<ReceiptLineStatus, string> = {
  blocked: "pill-destructive",
  attention: "pill-warning",
  ready: "pill-info",
  matched: "pill-success",
  checked: "pill-success",
};

/** Só a cor do texto/ícone — para o ícone da linha, que não leva fundo. */
export const RECEIPT_LINE_STATUS_TEXT: Record<ReceiptLineStatus, string> = {
  blocked: "text-destructive",
  attention: "text-warning",
  ready: "text-info",
  matched: "text-success",
  checked: "text-success",
};
