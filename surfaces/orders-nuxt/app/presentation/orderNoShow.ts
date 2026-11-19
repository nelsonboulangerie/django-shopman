// Não retirado (WP-G11): a prévia que o servidor monta
// (`GET orders/<ref>/no-show/preview/`) e o que o diálogo mostra dela.
//
// O servidor decide TUDO: se o pedido já pode ser encerrado, o destino de cada
// linha (volta à venda ou perda), quanto volta ao cliente, quanto fica com a
// loja e o texto que o cliente vai ler. A tela não escolhe destino nem refaz
// conta: só arruma o que veio para leitura, com as frases do servidor.

import type { Action } from "~/generated/ordersContract";

export type NoShowDestiny = "restock" | "loss";

export interface NoShowLine {
  line_id: string;
  sku: string;
  name: string;
  /** Quanto o pedido levou (texto decimal: "2", "0.35"). */
  qty: string;
  destiny: NoShowDestiny;
  /** "Volta à venda" ou "Perda", na voz do servidor. */
  destiny_label: string;
  /** Por que é perda (`made_to_order` · `no_stock` · `lot_expired`); vazio na linha que volta. */
  reason: string;
  reason_label: string;
  value_q: number;
  value_display: string;
}

export interface OrderNoShowPreview {
  ref: string;
  allowed: boolean;
  block_reason: string;
  /** A partir de quando o gesto libera (ISO), ou vazio. O `block_reason` já diz a hora. */
  releases_at: string;
  lines: NoShowLine[];
  paid_q: number;
  paid_display: string;
  refund_q: number;
  refund_display: string;
  retained_q: number;
  retained_display: string;
  /** O que o gesto faz com o dinheiro, por extenso (o gerente assina esta frase). */
  money_sentence: string;
  /** O aviso que o cliente recebe depois do gesto. */
  customer_text: string;
  managers: { username: string; name: string }[];
  action: Action;
}

/** Uma linha do diálogo: o item, quanto, o valor e o que acontece com ele. */
export interface NoShowLineView {
  id: string;
  name: string;
  qty: string;
  value: string;
  destiny: string;
  /** A cor do selo: a perda pede atenção de quem assina; o que volta é o esperado. */
  tone: "neutral" | "warning";
  /** Por que é perda, na frase do servidor. Vazio na linha que volta à venda. */
  why: string;
}

/** O que o diálogo mostra, já decidido: o corpo, o bloqueio e o botão. */
export interface NoShowDialogView {
  /** O servidor recusa o gesto agora: só o motivo aparece, sem confirmar. */
  blocked: boolean;
  blockReason: string;
  lines: NoShowLineView[];
  moneySentence: string;
  customerText: string;
  confirmLabel: string;
  canConfirm: boolean;
}

/** "2", "0,35": a quantidade como o balcão lê, sem zero sobrando ("2.000" vira "2"). */
export function noShowQty(qty: string): string {
  const text = String(qty ?? "").trim();
  const trimmed = text.includes(".") ? text.replace(/0+$/, "").replace(/\.$/, "") : text;
  return trimmed.replace(".", ",");
}

export function noShowLineView(line: NoShowLine): NoShowLineView {
  const loss = line.destiny === "loss";
  return {
    id: line.line_id,
    name: line.name,
    qty: noShowQty(line.qty),
    value: line.value_display,
    destiny: line.destiny_label,
    tone: loss ? "warning" : "neutral",
    why: loss ? line.reason_label : "",
  };
}

/**
 * O diálogo inteiro a partir da prévia. Bloqueado (`allowed: false`), mostra só o
 * motivo do servidor e não confirma; liberado, mostra as linhas, a frase do
 * dinheiro, o texto do cliente e o botão com o rótulo da ação do servidor.
 */
export function noShowDialogView(
  preview: OrderNoShowPreview,
  options: { busy?: boolean } = {},
): NoShowDialogView {
  const blocked = !preview.allowed;
  return {
    blocked,
    blockReason: blocked ? preview.block_reason : "",
    lines: blocked ? [] : preview.lines.map(noShowLineView),
    moneySentence: blocked ? "" : preview.money_sentence,
    customerText: blocked ? "" : preview.customer_text,
    confirmLabel: preview.action.label,
    canConfirm: !blocked && preview.action.enabled && !options.busy,
  };
}
