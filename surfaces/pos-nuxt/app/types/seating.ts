// Contrato da leitura `/api/v1/backstage/pos/seating/` (Projection
// `backstage/projections/seating.py`): a planta do salão de hoje, o total que o B.I.
// usa e o histórico de cada mudança.

export type SpotShape = "round" | "square" | "long" | "stool";

export interface SeatingSpotProjection {
  ref: string;
  label: string;
  short_label: string;
  area: string;
  kind: "table" | "counter";
  shape: SpotShape;
  seats: number;
  counts_in_capacity: boolean;
  plan_x: number | null;
  plan_y: number | null;
  rotation: number;
  /** Desde quando a mesa existe, atravessando as versões (ISO) ou null = sempre. */
  since: string | null;
  since_label: string;
  born_today: boolean;
}

export interface SeatingHistoryEntry {
  id: number;
  at: string;
  at_label: string;
  who: string;
  ref: string;
  action: string;
  summary: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export interface SeatingTotals {
  capacity_seats: number;
  capacity_spots: number;
  extra_seats: number;
}

export interface SeatingResponse {
  today: string;
  today_label: string;
  revision: string;
  spots: SeatingSpotProjection[];
  totals: SeatingTotals;
  shapes: { value: SpotShape; label: string }[];
  max_seats: number;
  history: SeatingHistoryEntry[];
  saved?: { changed: number; created: number; versioned: number; removed: number };
}
