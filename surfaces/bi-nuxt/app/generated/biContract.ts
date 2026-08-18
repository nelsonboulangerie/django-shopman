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

/** O período de mesmo tamanho imediatamente anterior (F7 — comparação). */
export interface BIProductionPrevious {
  date_from: string;
  date_to: string;
  batches_finished: number;
  finished_total: string;
  loss_total: string;
  finished_by_day: string[];
}

/** BIProductionReport(date_from: 'str', date_to: 'str', days: 'tuple[BIProductionDay, ...]', oven_time_by_recipe: 'tuple[BIOvenTimeRow, ...]', oven_time_by_oven: 'tuple[BIOvenTimeRow, ...]', batches_finished: 'int', batches_measured: 'int', oven_coverage_percent: 'int', previous: 'BIProductionPrevious') */
export interface BIProductionReport {
  date_from: string;
  date_to: string;
  days: BIProductionDay[];
  oven_time_by_recipe: BIOvenTimeRow[];
  oven_time_by_oven: BIOvenTimeRow[];
  batches_finished: number;
  batches_measured: number;
  oven_coverage_percent: number;
  previous: BIProductionPrevious;
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

/** O período de MESMO tamanho imediatamente anterior (F7 — comparação). */
export interface BISalesPrevious {
  date_from: string;
  date_to: string;
  orders_total: number;
  revenue_total_q: number;
  average_ticket_q: number;
  revenue_by_day: number[];
}

/** BISalesReport(date_from: 'str', date_to: 'str', days: 'tuple[BISalesDay, ...]', by_channel: 'tuple[BISalesChannelRow, ...]', top_skus: 'tuple[BITopSkuRow, ...]', orders_by_hour: 'tuple[int, ...]', orders_by_weekday: 'tuple[int, ...]', orders_total: 'int', revenue_total_q: 'int', average_ticket_q: 'int', cancelled_total: 'int', historical_days: 'int', previous: 'BISalesPrevious') */
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
  previous: BISalesPrevious;
}

/** BICashDay(date: 'str', shifts: 'int', difference_q: 'int', sangria_q: 'int', suprimento_q: 'int') */
export interface BICashDay {
  date: string;
  shifts: number;
  difference_q: number;
  sangria_q: number;
  suprimento_q: number;
}

/** BICashOperatorRow(operator: 'str', shifts: 'int', difference_q: 'int', drawer_openings: 'int', drawer_unlocks: 'int', change_requests: 'int') */
export interface BICashOperatorRow {
  operator: string;
  shifts: number;
  difference_q: number;
  drawer_openings: number;
  drawer_unlocks: number;
  change_requests: number;
}

/** Uma hora do dia com atividade de gaveta. Só horas com algo aparecem. */
export interface BICashHourRow {
  hour: number;
  drawer_openings: number;
  drawer_unlocks: number;
}

/** BICashMethodRow(method: 'str', amount_q: 'int') */
export interface BICashMethodRow {
  method: string;
  amount_q: number;
}

/** O período de mesmo tamanho imediatamente anterior (F7 — comparação). */
export interface BICashPrevious {
  date_from: string;
  date_to: string;
  shifts_total: number;
  difference_total_q: number;
  difference_by_day: number[];
}

/** BICashReport(date_from: 'str', date_to: 'str', days: 'tuple[BICashDay, ...]', by_operator: 'tuple[BICashOperatorRow, ...]', payment_methods: 'tuple[BICashMethodRow, ...]', shifts_total: 'int', difference_total_q: 'int', closings_missing: 'int', previous: 'BICashPrevious', drawer_by_hour: 'tuple[BICashHourRow, ...]') */
export interface BICashReport {
  date_from: string;
  date_to: string;
  days: BICashDay[];
  by_operator: BICashOperatorRow[];
  payment_methods: BICashMethodRow[];
  shifts_total: number;
  difference_total_q: number;
  closings_missing: number;
  previous: BICashPrevious;
  drawer_by_hour: BICashHourRow[];
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

/** BIExploreRow(key: 'str', label: 'str', key2: 'str', label2: 'str', value: 'float') */
export interface BIExploreRow {
  key: string;
  label: string;
  key2: string;
  label2: string;
  value: number;
}

/** BIExploreMetricOption(key: 'str', label: 'str', unit: 'str', dimensions: 'tuple[str, ...]') */
export interface BIExploreMetricOption {
  key: string;
  label: string;
  unit: string;
  dimensions: string[];
}

/** BIExploreReport(metric: 'str', metric_label: 'str', unit: 'str', dimension: 'str', dimension_label: 'str', dimension2: 'str', dimension2_label: 'str', date_from: 'str', date_to: 'str', rows: 'tuple[BIExploreRow, ...]', truncated: 'int', metrics: 'tuple[BIExploreMetricOption, ...]') */
export interface BIExploreReport {
  metric: string;
  metric_label: string;
  unit: string;
  dimension: string;
  dimension_label: string;
  dimension2: string;
  dimension2_label: string;
  date_from: string;
  date_to: string;
  rows: BIExploreRow[];
  truncated: number;
  metrics: BIExploreMetricOption[];
}

/** O provável, e a faixa onde caiu metade dos dias parecidos. */
export interface Expectation {
  expected: number;
  low: number;
  high: number;
}

/** Um ramo condicional: 'se fizer calor', 'se chover'. */
export interface ForecastBranch {
  key: string;
  label: string;
  sample_size: number;
  revenue_q: Expectation;
  orders: Expectation;
}

/** A prestação de contas. Sem ela o número vira promessa. */
export interface ForecastBasis {
  sample_size: number;
  applied: string[];
  relaxed: string[];
  unavailable: string[];
  window_from: string;
  window_to: string;
  excluded_closed: number;
  excluded_disrupted: number;
  without_sales: number;
  without_level: number;
  level_revenue_q: number;
  level_days: number;
}

/** Uma ocorrência passada da mesma data comercial. */
export interface OccasionYear {
  date: string;
  revenue_q: number;
  ratio: number;
}

/** O que ESTA data fez nos anos anteriores. */
export interface ForecastOccasion {
  name: string;
  is_eve: boolean;
  years: OccasionYear[];
  expected_revenue_q: number;
}

/** DayForecast(date: 'str', weekday: 'int', weekday_label: 'str', closed: 'bool', closed_reason: 'str', revenue_q: 'Expectation | None', orders: 'Expectation | None', branches: 'tuple[ForecastBranch, ...]', occasion: 'ForecastOccasion | None', basis: 'ForecastBasis | None', missing_reason: 'str') */
export interface DayForecast {
  date: string;
  weekday: number;
  weekday_label: string;
  closed: boolean;
  closed_reason: string;
  revenue_q: Expectation | null;
  orders: Expectation | null;
  branches: ForecastBranch[];
  occasion: ForecastOccasion | null;
  basis: ForecastBasis | null;
  missing_reason: string;
}

/** BIForecastReport(horizon: 'str', target: 'str', date_from: 'str', date_to: 'str', days: 'tuple[DayForecast, ...]', total_revenue_q: 'Expectation | None', total_orders: 'Expectation | None', total_missing_days: 'tuple[str, ...]') */
export interface BIForecastReport {
  horizon: string;
  target: string;
  date_from: string;
  date_to: string;
  days: DayForecast[];
  total_revenue_q: Expectation | null;
  total_orders: Expectation | null;
  total_missing_days: string[];
}

/** Quanto de troco sai por venda em dinheiro — o hábito do bairro. */
export interface ChangeHabit {
  per_cash_order_q: Expectation;
  band: string;
  measured_days: number;
  measured_orders: number;
  unmeasured_orders: number;
  window_from: string;
  window_to: string;
}

/** A tendência da denominação. Nunca uma contagem de peças. */
export interface ChangeMix {
  tendency: string;
  coin_value_percent: number;
  small_change_percent: number;
  sample_size: number;
}

/** DayChangeForecast(date: 'str', weekday: 'int', weekday_label: 'str', closed: 'bool', closed_reason: 'str', change_q: 'Expectation | None', coin_floor_q: 'float | None', cash_orders: 'Expectation | None', cash_share_percent: 'int', cash_share_days: 'int', missing_reason: 'str') */
export interface DayChangeForecast {
  date: string;
  weekday: number;
  weekday_label: string;
  closed: boolean;
  closed_reason: string;
  change_q: Expectation | null;
  coin_floor_q: number | null;
  cash_orders: Expectation | null;
  cash_share_percent: number;
  cash_share_days: number;
  missing_reason: string;
}

/** BIChangeReport(horizon: 'str', target: 'str', date_from: 'str', date_to: 'str', days: 'tuple[DayChangeForecast, ...]', total_change_q: 'Expectation | None', total_missing_days: 'tuple[str, ...]', habit: 'ChangeHabit | None', mix: 'ChangeMix | None', missing_reason: 'str') */
export interface BIChangeReport {
  horizon: string;
  target: string;
  date_from: string;
  date_to: string;
  days: DayChangeForecast[];
  total_change_q: Expectation | null;
  total_missing_days: string[];
  habit: ChangeHabit | null;
  mix: ChangeMix | null;
  missing_reason: string;
}
