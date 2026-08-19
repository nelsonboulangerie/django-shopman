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

/** O período de mesmo tamanho imediatamente anterior (F7 — comparação). */
export interface BICashPrevious {
  date_from: string;
  date_to: string;
  shifts_total: number;
  difference_total_q: number;
  difference_by_day: number[];
}

/** BICashReport(date_from: 'str', date_to: 'str', days: 'tuple[BICashDay, ...]', by_operator: 'tuple[BICashOperatorRow, ...]', payment_methods: 'tuple[BICashMethodRow, ...]', shifts_total: 'int', difference_total_q: 'int', closings_missing: 'int', previous: 'BICashPrevious') */
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

/** BIProfileReading(key: 'str', label: 'str') */
export interface BIProfileReading {
  key: string;
  label: string;
}

/** BIProfileBand(key: 'str', label: 'str', title: 'str', start: 'int', end: 'int', hours: 'int') */
export interface BIProfileBand {
  key: string;
  label: string;
  title: string;
  start: number;
  end: number;
  hours: number;
}

/** BIProfileRow(reading: 'str', profile: 'str', label: 'str', orders: 'int', orders_share: 'float', revenue_q: 'int', revenue_share: 'float', average_ticket_q: 'int', units_per_order: 'str', distinct_per_order: 'str', orders_by_band: 'tuple[int, ...]', revenue_by_band_q: 'tuple[int, ...]') */
export interface BIProfileRow {
  reading: string;
  profile: string;
  label: string;
  orders: number;
  orders_share: number;
  revenue_q: number;
  revenue_share: number;
  average_ticket_q: number;
  units_per_order: string;
  distinct_per_order: string;
  orders_by_band: number[];
  revenue_by_band_q: number[];
}

/** BIProfileRange(profile: 'str', label: 'str', min_orders: 'int', max_orders: 'int', min_share: 'float', max_share: 'float', min_revenue_q: 'int', max_revenue_q: 'int') */
export interface BIProfileRange {
  profile: string;
  label: string;
  min_orders: number;
  max_orders: number;
  min_share: number;
  max_share: number;
  min_revenue_q: number;
  max_revenue_q: number;
}

/** BIProfileSensitivity(orders_changed: 'int', share_changed: 'float', ranges: 'tuple[BIProfileRange, ...]') */
export interface BIProfileSensitivity {
  orders_changed: number;
  share_changed: number;
  ranges: BIProfileRange[];
}

/** BIProfileCategoryRow(category: 'str', revenue_q: 'int', share: 'float', ready_beverage_q: 'int') */
export interface BIProfileCategoryRow {
  category: string;
  revenue_q: number;
  share: number;
  ready_beverage_q: number;
}

/** BIStrikeCell(weekday: 'int', band: 'str', orders: 'int', with_beverage: 'int', rate: 'float') */
export interface BIStrikeCell {
  weekday: number;
  band: string;
  orders: number;
  with_beverage: number;
  rate: number;
}

/** BIProfileBeverage(orders_with_beverage: 'int', strike_rate: 'float', prepared_rate: 'float', ready_revenue_q: 'int', ready_share: 'float', local_orders: 'int', per_local_order: 'str', beverage_only_orders: 'int', beverage_only_share: 'float', beverage_only_ticket_q: 'int', beverage_only_by_band: 'tuple[int, ...]', by_weekday_band: 'tuple[BIStrikeCell, ...]', by_weekday: 'tuple[BIStrikeCell, ...]', by_band: 'tuple[BIStrikeCell, ...]') */
export interface BIProfileBeverage {
  orders_with_beverage: number;
  strike_rate: number;
  prepared_rate: number;
  ready_revenue_q: number;
  ready_share: number;
  local_orders: number;
  per_local_order: string;
  beverage_only_orders: number;
  beverage_only_share: number;
  beverage_only_ticket_q: number;
  beverage_only_by_band: number[];
  by_weekday_band: BIStrikeCell[];
  by_weekday: BIStrikeCell[];
  by_band: BIStrikeCell[];
}

/** BIRevpashRow(band: 'str', title: 'str', hours: 'int', revenue_local_q: 'int', days: 'int', seats: 'int', revpash_q: 'int') */
export interface BIRevpashRow {
  band: string;
  title: string;
  hours: number;
  revenue_local_q: number;
  days: number;
  seats: number;
  revpash_q: number;
}

/** A leitura em graus: P(alguém sentou) por cesta = maior peso da cesta. */
export interface BIProfileEstimate {
  seated_orders: number;
  seated_share: number;
  seated_revenue_q: number;
  seated_revenue_share: number;
  takeaway_orders: number;
  takeaway_share: number;
  weighted_orders: number;
  unweighted_orders: number;
  seated_by_band: number[];
  orders_by_band: number[];
}

/** BIProfilesPrevious(date_from: 'str', date_to: 'str', counter_orders: 'int', counter_revenue_q: 'int', rows: 'tuple[BIProfileRow, ...]', estimate: 'BIProfileEstimate') */
export interface BIProfilesPrevious {
  date_from: string;
  date_to: string;
  counter_orders: number;
  counter_revenue_q: number;
  rows: BIProfileRow[];
  estimate: BIProfileEstimate;
}

/** BIConsumptionProfilesReport(date_from: 'str', date_to: 'str', weekday: 'int | None', hour_band: 'str', readings: 'tuple[BIProfileReading, ...]', bands: 'tuple[BIProfileBand, ...]', profiles: 'tuple[BIProfileRow, ...]', counter_orders: 'int', counter_revenue_q: 'int', delivery_orders: 'int', delivery_revenue_q: 'int', revenue_total_q: 'int', coverage: 'float', days_with_sales: 'int', estimate: 'BIProfileEstimate', sensitivity: 'BIProfileSensitivity', categories: 'tuple[BIProfileCategoryRow, ...]', category_lines_revenue_q: 'int', category_header_gap_q: 'int', beverage: 'BIProfileBeverage', revpash: 'tuple[BIRevpashRow, ...]', seats: 'int', seats_source: 'str', previous: 'BIProfilesPrevious') */
export interface BIConsumptionProfilesReport {
  date_from: string;
  date_to: string;
  weekday: number | null;
  hour_band: string;
  readings: BIProfileReading[];
  bands: BIProfileBand[];
  profiles: BIProfileRow[];
  counter_orders: number;
  counter_revenue_q: number;
  delivery_orders: number;
  delivery_revenue_q: number;
  revenue_total_q: number;
  coverage: number;
  days_with_sales: number;
  estimate: BIProfileEstimate;
  sensitivity: BIProfileSensitivity;
  categories: BIProfileCategoryRow[];
  category_lines_revenue_q: number;
  category_header_gap_q: number;
  beverage: BIProfileBeverage;
  revpash: BIRevpashRow[];
  seats: number;
  seats_source: string;
  previous: BIProfilesPrevious;
}
