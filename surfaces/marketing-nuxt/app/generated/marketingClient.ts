// AUTO-GENERATED — do not edit by hand.
// Source of truth: contracts/openapi/marketing_v2.openapi.json
// Regenerate with: python manage.py export_marketing_client

export interface ActionConfirmationProjectionV2 {
  mode: "none" | "simple" | "summary" | "typed";
  token_required: boolean;
  consequence_code: string;
  step_up: "none" | "password" | "totp";
  dual_control: boolean;
}

export interface AnnouncementFactsProjectionV2 {
  trigger: "" | "production_finished" | "low_stock" | "stock_back" | "product_created" | "manual" | "schedule";
  campaign_ref: string;
  template_ref: string;
  product_ref: string;
}

export interface AnnouncementProjectionV2 {
  ref: string;
  version: number;
  state: "draft" | "pending_review" | "approved" | "publishing" | "settled" | "published" | "failed" | "rejected" | "expired" | "cancelled";
  reason_code: "" | "review_required" | "review_window_expired";
  facts: AnnouncementFactsProjectionV2;
  platform_refs: Array<string>;
  created_at: string;
  age_seconds: number;
  expires_at: string | null;
  expires_in_seconds: number | null;
  scheduled_for: string | null;
  approved_at: string | null;
  rejected_at: string | null;
  published_at: string | null;
  settled_at: string | null;
  audience: AudienceSummaryProjectionV2;
  artifact: ArtifactSummaryProjectionV2 | null;
  readiness: ReadinessProjectionV2;
  delivery: DeliveryAggregateProjectionV2;
}

export interface ArtifactSummaryProjectionV2 {
  ref: string;
  version: number;
  schema_version: number;
  artifact_hash: string;
  created_at: string;
}

export interface AudienceSummaryProjectionV2 {
  source_ref: string;
  version: number;
  eligible_count: number;
  excluded_by_reason: Record<string, number>;
  deduplicated_count: number;
  vip_count: number;
  general_count: number;
  wave_count: number;
  policy_version: string;
  cohort_hash: string;
  calculated_at: string | null;
  expires_at: string | null;
  freshness: FreshnessProjectionV2;
}

export interface DeliveryAggregateProjectionV2 {
  state: "not_started" | "fanout_pending" | "delivering" | "succeeded" | "completed_with_failures" | "unknown" | "cancelled" | "expired" | "legacy_untracked";
  counts: DeliveryCountsProjectionV2;
  target_count: number;
  fanout_expected: number;
  fanout_materialized: number;
  platforms: Array<PlatformDeliveryProjectionV2>;
  freshness: FreshnessProjectionV2;
}

export interface DeliveryCountsProjectionV2 {
  planned: number;
  suppressed: number;
  queued: number;
  sending: number;
  accepted: number;
  confirmed: number;
  failed_retryable: number;
  failed_final: number;
  unknown: number;
  cancelled: number;
  expired: number;
}

export interface FreshnessProjectionV2 {
  state: "fresh" | "stale" | "degraded" | "unavailable";
  as_of: string | null;
  degraded_sources: Array<string>;
}

export interface MarketingActionProjectionV2 {
  ref: string;
  resource_ref: string;
  kind: "acknowledge_alert" | "cancel_announcement" | "configure_platform" | "edit_announcement" | "edit_campaign" | "fire_campaign" | "mark_notification_read" | "open_announcement" | "open_platform" | "publish_announcement_now" | "reconcile_unknown_delivery" | "reject_announcement" | "reschedule_announcement" | "retry_failed_delivery" | "schedule_announcement" | "send_platform_test";
  label: string;
  priority: "primary" | "secondary" | "danger" | "quiet";
  enabled: boolean;
  reason: string;
  href: string;
  method: "GET" | "POST" | "PATCH" | "DELETE";
  payload_schema: string;
  idempotency: "none" | "supported" | "required";
  confirmation: ActionConfirmationProjectionV2;
  eligible_count: number;
  required_capabilities: Array<string>;
  creates_external_effect: boolean;
}

export interface MarketingAnnouncementDataV2 {
  kind: "announcement_detail";
  announcement: AnnouncementProjectionV2;
}

export interface MarketingBoardDataV2 {
  kind: "board";
  pending: Array<AnnouncementProjectionV2>;
  recent: Array<AnnouncementProjectionV2>;
  counters: OperationalCountersProjectionV2;
}

export interface MarketingEnvelopeV2 {
  contract: "marketing.v2";
  generated_at: string;
  shop_timezone: string;
  resource_version: number;
  freshness: FreshnessProjectionV2;
  data: MarketingBoardDataV2 | MarketingAnnouncementDataV2;
  actions: Array<MarketingActionProjectionV2>;
}

export interface OperationalCountersProjectionV2 {
  pending_decision_count: number;
  accepted_unconfirmed_targets_today: number;
  confirmed_targets_today: number;
  failed_final_targets_today: number;
  unknown_targets_open: number;
}

export interface PlatformDeliveryProjectionV2 {
  platform_ref: string;
  state: "not_started" | "fanout_pending" | "delivering" | "succeeded" | "completed_with_failures" | "unknown" | "cancelled" | "expired" | "legacy_untracked";
  counts: DeliveryCountsProjectionV2;
  target_count: number;
  fanout_expected: number;
  fanout_materialized: number;
  lane_count: number;
  complete_lane_count: number;
}

export interface PlatformReadinessProjectionV2 {
  platform_ref: string;
  state: "ready" | "degraded" | "blocked" | "unknown";
  checked_at: string | null;
}

export interface ReadinessProjectionV2 {
  state: "ready" | "degraded" | "blocked" | "unknown";
  platforms: Array<PlatformReadinessProjectionV2>;
}

export type MarketingActionKind = MarketingActionProjectionV2["kind"];
export type MarketingActionMethod = MarketingActionProjectionV2["method"];
export type MarketingActionPriority = MarketingActionProjectionV2["priority"];
export type MarketingFreshnessState = FreshnessProjectionV2["state"];

export interface MarketingV2TransportOptions {
  method: "GET";
  credentials: "same-origin";
}

export type MarketingV2Transport = <T>(
  href: string,
  options: MarketingV2TransportOptions,
) => Promise<T>;

export interface MarketingV2Client {
  getMarketingBoard(): Promise<MarketingEnvelopeV2>;
  getMarketingAnnouncement(announcementId: number): Promise<MarketingEnvelopeV2>;
}

export const MARKETING_V2_BOARD_PATH = "/api/v1/backstage/marketing/v2/" as const;

export function createMarketingV2Client(
  transport: MarketingV2Transport,
): MarketingV2Client {
  const readOptions: MarketingV2TransportOptions = {
    method: "GET",
    credentials: "same-origin",
  };
  return {
    getMarketingBoard: () =>
      transport<MarketingEnvelopeV2>(MARKETING_V2_BOARD_PATH, readOptions),
    getMarketingAnnouncement: (announcementId: number) => {
      if (!Number.isSafeInteger(announcementId) || announcementId <= 0) {
        throw new RangeError("announcementId must be a positive integer");
      }
      return transport<MarketingEnvelopeV2>(
        `/api/v1/backstage/marketing/v2/announcements/${announcementId}/`,
        readOptions,
      );
    },
  };
}
