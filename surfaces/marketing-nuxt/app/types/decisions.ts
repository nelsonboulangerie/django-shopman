// Espelho de `shopman/backstage/projections/marketing_decisions.py`.
// A projeção só leva códigos, contagens, datas e nomes de cadastro; a frase em
// pt-BR mora em `~/presentation/decisions.ts`.

export type DecisionKind = "review" | "retry_failed" | "reconcile_unknown";

export type AutomaticCheckState =
  "checking" | "confirmed" | "accepted" | "failed" | "still_unknown";

export type DeliveryKind = "direct_message" | "publication" | "";

/** Duas grandezas, nunca somadas: postagens públicas e pessoas com mensagem. */
export interface DecisionReach {
  posts: number;
  people: number;
}

export interface DecisionFailure {
  platform_ref: string;
  delivery_kind: DeliveryKind;
  count: number;
  reason_code: string;
}

export interface DecisionItem {
  ref: string;
  kind: DecisionKind;
  announcement_id: number;
  announcement_version: number;
  campaign_name: string;
  trigger: string;
  product_name: string;
  /** A foto que o anúncio leva, ou a do produto; vazia sem foto. */
  image_url: string;
  /** O fato do lote: quantas unidades e quando saiu ("24 un saíram às 10:01"). */
  lot_quantity: string;
  lot_finished_at: string | null;
  /** Falha: as outras plataformas que já entregaram, e quantas pessoas receberam. */
  delivered_platform_refs: string[];
  delivered_people: number;
  platform_refs: string[];
  reach: DecisionReach;
  deadline_at: string | null;
  scheduled_for: string | null;
  created_at: string;
  failures: DecisionFailure[];
  href: string;
}

export interface AutomaticCheck {
  ref: string;
  announcement_id: number;
  campaign_name: string;
  platform_ref: string;
  delivery_kind: DeliveryKind;
  state: AutomaticCheckState;
  target_count: number;
  checked_at: string | null;
  href: string;
}

export interface ScheduledItem {
  ref: string;
  announcement_id: number;
  campaign_name: string;
  trigger: string;
  product_name: string;
  image_url: string;
  platform_refs: string[];
  reach: DecisionReach;
  scheduled_for: string;
  href: string;
}

export interface DecisionQueue {
  generated_at: string;
  shop_timezone: string;
  items: DecisionItem[];
  automatic_checks: AutomaticCheck[];
  scheduled: ScheduledItem[];
  scheduled_today_count: number;
  active_campaign_count: number;
}

export interface DecisionQueueResponse {
  queue: DecisionQueue;
}
