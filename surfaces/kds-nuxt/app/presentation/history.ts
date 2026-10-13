// A linha do Histórico de hoje (dono, 13/10/2026), pura: o que cada pedido diz na lista.
//
//   0131  Encomenda · Ana                                   preparo 9 min   [Reabrir]
//   2x Croque, 1x Café
//   recebido 21:40 · iniciado 21:42 Rafael · Pronto 21:51 Rafael (tela)
//   Pronto 21:51 Rafael (tela) → desfeito 21:58 Ana
//
// A trilha vem pronta do servidor (`steps`, `undone`); aqui só se junta e se decide o que
// aparece. Reabrir só onde o servidor deixa; onde não deixa, a linha diz o motivo.
import type { KDSHistoryEntryProjection, KDSHistoryProjection } from "~/types/kds";
import { splitRef, ticketOverline } from "~/presentation/board";

export interface KdsHistoryRow {
  pk: number;
  code: string;
  /** "Encomenda · Ana" na encomenda; vazio na venda do dia (o código chama o pedido). */
  overline: string;
  items: string;
  trail: string;
  undone: string[];
  /** "preparo 9 min"; vazio no cancelado. */
  prep: string;
  cancelled: boolean;
  canReopen: boolean;
  blockedReason: string;
}

export function historyRow(entry: KDSHistoryEntryProjection): KdsHistoryRow {
  const ticket = entry.ticket;
  return {
    pk: ticket.pk,
    code: splitRef(ticket.order_ref).code,
    overline: ticket.is_preorder ? ticketOverline(ticket) : "",
    items: entry.items_summary,
    trail: entry.steps.join(" · "),
    undone: [...entry.undone],
    prep: entry.prep_display ? `preparo ${entry.prep_display}` : "",
    cancelled: entry.state === "cancelled",
    canReopen: entry.can_reopen,
    blockedReason: entry.can_reopen ? "" : entry.reopen_block_reason,
  };
}

/** O rodapé quando a lista não mostra o dia inteiro; vazio quando mostra. */
export function historyFootnote(history: Pick<KDSHistoryProjection, "entries" | "total" | "query">): string {
  const shown = history.entries.length;
  if (history.total <= shown) return "";
  return `Mostrando os ${shown} mais recentes de ${history.total}. Busque pelo código para achar os outros.`;
}

/** O vazio do histórico: sem nada hoje, ou sem nada para a busca. */
export function historyEmptyTitle(query: string): string {
  const q = query.trim();
  return q ? `Nenhum pedido de hoje para “${q}”.` : "Nenhum pedido concluído ou cancelado hoje nesta estação.";
}
