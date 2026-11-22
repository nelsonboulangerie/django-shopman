// Contrato do fechamento do DIA (contagem cega de sobras/perdas), servido por
// GET/POST /api/v1/backstage/closing/ — serialização da DayClosingProjection
// (shopman/backstage/projections/closing.py). Só os campos que a superfície lê.
//
// CEGO ATÉ A CONTAGEM: antes do registro o servidor não manda as quantidades
// que a contagem deveria descobrir (disponível, vencendo, não conforme, total,
// produção do dia). Por isso são opcionais aqui. Dinheiro não vem nunca.

export interface ClosingItemProjection {
  sku: string;
  name: string;
  classification: "keep" | "expired" | "mixed" | string; // o LOTE decide (C4)
  qty_available?: number;
  qty_expiring?: number;
  qty_nonconforming?: number;
}

export interface ClosingProductionRow {
  recipe_ref: string;
  output_sku: string;
  planned: number;
  finished: number;
  loss?: number;
}

export interface ClosingReconciliationError {
  sku: string;
  sold_qty: number;
  available_qty: number;
  deficit_qty: number;
}

export interface ClosingPendingProduction {
  ref: string;
  output_sku: string;
  recipe_name: string;
  status: string;
  status_label: string;
  quantity: string;
  /** ISO "2026-04-16" — a data que o link para a Produção precisa. */
  target_date: string;
  target_date_display: string;
  is_overdue: boolean;
}

/**
 * Um pedido de retirada pronto que ninguém veio buscar (#2684). `resolve`: o "Não
 * retirado" já pode ser feito, e o dia só fecha com a assinatura de um gerente;
 * `in_time`: ainda no prazo combinado, aparece e não segura; `owner`: o gesto não
 * serve a este pedido, fica com o Dono. O valor é o DESTE pedido, nunca somado.
 */
export interface ClosingPendingReadyOrder {
  ref: string;
  customer_name: string;
  /** "Combinado para 15h"; "" sem hora combinada. */
  promised_display: string;
  state: "resolve" | "in_time" | "owner";
  /** `in_time` e `owner`: o porquê, por extenso. */
  reason: string;
  /** `resolve`: o que acontece com o dinheiro. */
  money_sentence: string;
  /** `resolve`: a base que a tela leu, devolvida na assinatura. */
  revision: string;
}

export interface ClosingUpcomingPreorder {
  date: string;
  date_display: string;
  orders_count: number;
}

export interface DayClosingProjection {
  today: string;
  today_display: string;
  items: ClosingItemProjection[];
  has_items: boolean;
  already_closed: boolean;
  existing_closing_display: string;
  total_available?: number;
  production_summary?: Record<string, ClosingProductionRow>;
  reconciliation_errors: ClosingReconciliationError[];
  pending_production: ClosingPendingProduction[];
  has_pending_production: boolean;
  upcoming_preorders: ClosingUpcomingPreorder[];
  has_upcoming_preorders: boolean;
  /** "Explicar o dia estranho": vazio na maioria dos dias. */
  pending_episodes?: ClosingPendingEpisode[];
  episode_options?: ClosingEpisodeOption[];
  has_pending_episodes?: boolean;
  /** A forma do movimento por hora, hoje × o mesmo dia típico (0 a 1, sem valores). */
  hourly_shape?: ClosingHourlyShape | null;
  /** Quem fecha ("Admin · gerência"). */
  operator_display?: string;
  /** Pedidos prontos que ninguém veio buscar (#2684). */
  pending_ready_orders?: ClosingPendingReadyOrder[];
  /** Algum deles SEGURA o dia (`state === "resolve"`). */
  has_pending_ready_orders?: boolean;
}

/** Algo estranho que o sistema notou no dia e ninguém explicou (`OperationEpisode`). */
export interface ClosingPendingEpisode {
  id: number;
  /** O que o sistema MEDIU, em português ("nenhuma venda entre 14h e 16h"). */
  signal: string;
  window_display: string;
}

/** Uma resposta possível, do catálogo (`OperationEpisodeKind`): escolher, nunca digitar. */
export interface ClosingEpisodeOption {
  ref: string;
  label: string;
  hint: string;
}

export interface DayClosingResponse {
  closing: DayClosingProjection;
}

export interface ClosingHourlyShape {
  hours: string[];
  /** `null` nas horas que ainda não chegaram. */
  today: Array<number | null>;
  typical: number[];
  typical_label: string;
  /** "14h" quando o movimento de hoje caiu abaixo da metade do típico dali em diante. */
  drop_after: string;
}
