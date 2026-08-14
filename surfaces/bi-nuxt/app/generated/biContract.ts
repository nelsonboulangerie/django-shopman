// AUTO-GENERATED — do not edit by hand.
// Source of truth: shopman/backstage/projections/bi_*.py
// Regenerate with: python manage.py export_bi_schema

/** Tempo de forno agregado por receita ou por forno. */
export interface BIOvenTimeRow {
  ref: string;
  label: string;
  runs: number;
  avg_minutes: string;
  p50_minutes: string;
  p90_minutes: string;
  avg_planned_minutes: string;
}

/** Um dia da série: produção fechada e o mix comercial da qualidade. */
export interface BIProductionDay {
  date: string;
  planned: string;
  finished: string;
  loss: string;
  yield_percent: number | null;
  full_price: string;
  discounted: string;
}

/** BIProductionReport(date_from: 'str', date_to: 'str', days: 'tuple[BIProductionDay, ...]', oven_time_by_recipe: 'tuple[BIOvenTimeRow, ...]', oven_time_by_oven: 'tuple[BIOvenTimeRow, ...]', batches_finished: 'int', batches_measured: 'int', oven_coverage_percent: 'int') */
export interface BIProductionReport {
  date_from: string;
  date_to: string;
  days: BIProductionDay[];
  oven_time_by_recipe: BIOvenTimeRow[];
  oven_time_by_oven: BIOvenTimeRow[];
  batches_finished: number;
  batches_measured: number;
  oven_coverage_percent: number;
}

/** BISalesDay(date: 'str', orders: 'int', revenue_q: 'int', average_ticket_q: 'int', source: 'str') */
export interface BISalesDay {
  date: string;
  orders: number;
  revenue_q: number;
  average_ticket_q: number;
  source: string;
}

/** BISalesChannelRow(channel_ref: 'str', orders: 'int', revenue_q: 'int') */
export interface BISalesChannelRow {
  channel_ref: string;
  orders: number;
  revenue_q: number;
}

/** BITopSkuRow(sku: 'str', name: 'str', qty: 'str', revenue_q: 'int') */
export interface BITopSkuRow {
  sku: string;
  name: string;
  qty: string;
  revenue_q: number;
}

/** BISalesReport(date_from: 'str', date_to: 'str', days: 'tuple[BISalesDay, ...]', by_channel: 'tuple[BISalesChannelRow, ...]', top_skus: 'tuple[BITopSkuRow, ...]', orders_by_hour: 'tuple[int, ...]', orders_by_weekday: 'tuple[int, ...]', orders_total: 'int', revenue_total_q: 'int', average_ticket_q: 'int', cancelled_total: 'int', historical_days: 'int') */
export interface BISalesReport {
  date_from: string;
  date_to: string;
  days: BISalesDay[];
  by_channel: BISalesChannelRow[];
  top_skus: BITopSkuRow[];
  orders_by_hour: number[];
  orders_by_weekday: number[];
  orders_total: number;
  revenue_total_q: number;
  average_ticket_q: number;
  cancelled_total: number;
  historical_days: number;
}

/** BICashDay(date: 'str', shifts: 'int', difference_q: 'int', sangria_q: 'int', suprimento_q: 'int') */
export interface BICashDay {
  date: string;
  shifts: number;
  difference_q: number;
  sangria_q: number;
  suprimento_q: number;
}

/** BICashOperatorRow(operator: 'str', shifts: 'int', difference_q: 'int') */
export interface BICashOperatorRow {
  operator: string;
  shifts: number;
  difference_q: number;
}

/** BICashMethodRow(method: 'str', amount_q: 'int') */
export interface BICashMethodRow {
  method: string;
  amount_q: number;
}

/** BICashReport(date_from: 'str', date_to: 'str', days: 'tuple[BICashDay, ...]', by_operator: 'tuple[BICashOperatorRow, ...]', payment_methods: 'tuple[BICashMethodRow, ...]', shifts_total: 'int', difference_total_q: 'int', closings_missing: 'int') */
export interface BICashReport {
  date_from: string;
  date_to: string;
  days: BICashDay[];
  by_operator: BICashOperatorRow[];
  payment_methods: BICashMethodRow[];
  shifts_total: number;
  difference_total_q: number;
  closings_missing: number;
}

/** BICustomerSegmentRow(segment: 'str', customers: 'int') */
export interface BICustomerSegmentRow {
  segment: string;
  customers: number;
}

/** BICustomersWeekRow(week_start: 'str', new_customers: 'int') */
export interface BICustomersWeekRow {
  week_start: string;
  new_customers: number;
}

/** BICustomersReport(date_from: 'str', date_to: 'str', segments: 'tuple[BICustomerSegmentRow, ...]', new_by_week: 'tuple[BICustomersWeekRow, ...]', customers_total: 'int', with_insight: 'int', at_risk: 'int', average_ticket_q: 'int') */
export interface BICustomersReport {
  date_from: string;
  date_to: string;
  segments: BICustomerSegmentRow[];
  new_by_week: BICustomersWeekRow[];
  customers_total: number;
  with_insight: number;
  at_risk: number;
  average_ticket_q: number;
}
