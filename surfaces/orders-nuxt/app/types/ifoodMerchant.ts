// A loja no iFood, ao vivo — espelho de shopman/backstage/projections/ifood_merchant_console.py.
// GET /api/v1/backstage/ifood/{merchants,merchant,interruptions,opening-hours}/
// DELETE /api/v1/backstage/ifood/interruptions/<id>/ (só pausa feita no Portal).
// Integração desligada: `{ enabled: false }` e nada mais.

export interface IFoodOff {
  enabled: false;
}

export interface IFoodMerchantRow {
  id: string;
  name: string;
  corporate_name: string;
  is_current: boolean;
}

export interface IFoodMerchants {
  enabled: true;
  merchants: IFoodMerchantRow[];
  error: string;
}

export interface IFoodStatusCheck {
  /** id da validação no iFood (``is-connected``), em texto secundário. */
  code: string;
  /** Nome de gente da validação ("Conexão com a casa"). */
  label: string;
  state: string;
  state_label: string;
  title: string;
  description: string;
}

export interface IFoodOperationStatus {
  operation: string;
  sales_channel: string;
  available: boolean;
  state: string;
  state_label: string;
  title: string;
  description: string;
  checks: IFoodStatusCheck[];
}

export interface IFoodMerchantDetail {
  enabled: true;
  merchant_id: string;
  /** ``code``: o código do iFood por trás da palavra (``DISABLED``); ``hint``: explicação curta. */
  detail: { label: string; value: string; code: string; hint: string }[];
  detail_error: string;
  available: boolean | null;
  operations: IFoodOperationStatus[];
  status_error: string;
  checked_at_display: string;
}

export type IFoodPauseOrigin = "switch" | "calendar" | "manager" | "portal";

export interface IFoodInterruptionRow {
  id: string;
  description: string;
  starts_at_display: string;
  ends_at_display: string;
  origin: IFoodPauseOrigin;
  origin_label: string;
  in_effect: boolean;
  removable: boolean;
  /** false: o iFood aceitou a pausa (devolveu o id), mas a lista dele ainda não a traz. */
  listed_by_ifood: boolean;
}

export interface IFoodRefusedPause {
  origin_label: string;
  starts_at_display: string;
  ends_at_display: string;
  error: string;
}

export interface IFoodInterruptions {
  enabled: true;
  items: IFoodInterruptionRow[];
  refused: IFoodRefusedPause[];
  error: string;
  checked_at_display: string;
}

export interface IFoodDayHours {
  day: string;
  label: string;
  house: string;
  ifood: string;
  matches: boolean;
}

export interface IFoodOpeningHours {
  enabled: true;
  days: IFoodDayHours[];
  matches: boolean | null;
  governs: boolean;
  error: string;
  checked_at_display: string;
}
