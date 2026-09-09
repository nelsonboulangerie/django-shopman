import type { MarketingActionProjectionV2 } from "~/types/campaign";

export type NotificationLifecycle =
  "unseen" | "seen" | "acknowledged" | "resolved" | "expired";

export type NotificationSeverity =
  "information" | "action_required" | "warning" | "critical";

export interface MarketingNotification {
  pk: number;
  category: string;
  title: string;
  message: string;
  lifecycle: NotificationLifecycle;
  severity: NotificationSeverity;
  source: { condition: string; ref: string; version: number };
  owner: { user_id: number; role: string };
  escalation: { role: string; at: string | null };
  expires_at: string | null;
  seen_at: string | null;
  acknowledged_at: string | null;
  resolved_at: string | null;
  version: number;
  created_at: string;
  created_at_display: string;
  actions: MarketingActionProjectionV2[];
}

export interface MarketingNotificationsResponse {
  schema_version: 2;
  shop_timezone: string;
  as_of: string;
  notifications: MarketingNotification[];
  page: { limit: number; has_more: boolean; next_cursor: string };
  counts: { unseen: number; unresolved: number };
}
