// A loja no iFood — espelho de shopman/backstage/projections/ifood_store.py.
// GET /api/v1/backstage/ifood/store/ · POST …/pause/ · POST …/resume/

export type IFoodPauseState = "pending_create" | "active" | "pending_remove" | "removed" | "failed";

export interface IFoodPause {
  ref: number;
  state: IFoodPauseState;
  state_label: string;
  reason: string;
  starts_at: string;
  ends_at: string;
  ends_at_display: string;
  requested_by: string;
  requested_at_display: string;
  removed_by: string;
  error: string;
}

export interface IFoodPauseOption {
  key: string;
  label: string;
  enabled: boolean;
  reason: string;
}

export interface IFoodStoreProjection {
  enabled: boolean;
  governs: boolean;
  can_pause: boolean;
  shop_open: boolean;
  shop_message: string;
  ifood_available: boolean | null;
  ifood_status_label: string;
  ifood_checked_at_display: string;
  ifood_problems: string[];
  diverges: boolean;
  pause: IFoodPause | null;
  last_pause: IFoodPause | null;
  options: IFoodPauseOption[];
}
