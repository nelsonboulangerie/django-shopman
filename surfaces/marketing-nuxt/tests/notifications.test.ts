import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  announcementSourceId,
  notificationAction,
  notificationOwnerLabel,
  notificationReasonLabel,
  notificationStateLabel,
} from "~/presentation/notifications";
import type { MarketingActionProjectionV2 } from "~/types/campaign";
import type { MarketingNotification } from "~/types/notifications";

function action(
  kind: MarketingActionProjectionV2["kind"],
  href: string,
  resourceRef = "announcement:42",
  method: MarketingActionProjectionV2["method"] = "GET",
): MarketingActionProjectionV2 {
  return {
    ref: `${resourceRef}:${kind}:v3`,
    resource_ref: resourceRef,
    kind,
    label: `presentation.marketing.action.${kind}`,
    priority: "primary",
    enabled: true,
    reason: "",
    href,
    method,
    payload_schema: "none",
    idempotency: "none",
    confirmation: {
      mode: "none",
      token_required: false,
      consequence_code: "",
      step_up: "none",
      dual_control: false,
    },
    eligible_count: 1,
    required_capabilities: [],
    creates_external_effect: false,
  };
}

function notification(
  over: Partial<MarketingNotification> = {},
): MarketingNotification {
  return {
    pk: 7,
    category: "marketing_approval",
    title: "Revisão necessária",
    message: "Confira o anúncio antes de publicar.",
    lifecycle: "unseen",
    severity: "action_required",
    source: {
      condition: "announcement_review",
      ref: "announcement:42",
      version: 3,
    },
    owner: { user_id: 9, role: "product" },
    escalation: { role: "ops", at: null },
    expires_at: "2026-09-09T10:00:00-03:00",
    seen_at: null,
    acknowledged_at: null,
    resolved_at: null,
    version: 1,
    created_at: "2026-09-09T09:00:00-03:00",
    created_at_display: "09/09 às 09:00",
    actions: [
      action("open_announcement", "/announcements/42#review"),
      action(
        "mark_notification_seen",
        "/api/v1/backstage/notifications/7/read/",
        "notification:7",
        "POST",
      ),
      action(
        "acknowledge_notification",
        "/api/v1/backstage/notifications/7/acknowledge/",
        "notification:7",
        "POST",
      ),
    ],
    ...over,
  };
}

describe("notification Actions", () => {
  it("accepts only the exact source, resource, method and anchored review path", () => {
    const row = notification();

    expect(notificationAction(row, "open_announcement")?.href).toBe(
      "/announcements/42#review",
    );
    expect(notificationAction(row, "mark_notification_seen")?.method).toBe(
      "POST",
    );
    expect(
      notificationAction(row, "acknowledge_notification")?.resource_ref,
    ).toBe("notification:7");
  });

  it("rejects stale, foreign, absolute and method-swapped Actions", () => {
    const variants = [
      action("open_announcement", "/announcements/41#review"),
      action("open_announcement", "//evil.example/announcements/42#review"),
      action(
        "open_announcement",
        "/announcements/42#review",
        "announcement:41",
      ),
      action(
        "open_announcement",
        "/announcements/42#review",
        "announcement:42",
        "POST",
      ),
    ];

    for (const invalid of variants) {
      expect(
        notificationAction(
          notification({ actions: [invalid] }),
          "open_announcement",
        ),
      ).toBeNull();
    }
  });

  it("does not infer an announcement from malformed or unrelated sources", () => {
    expect(announcementSourceId(notification())).toBe(42);
    expect(
      announcementSourceId(
        notification({
          source: {
            condition: "announcement_review",
            ref: "announcement:0",
            version: 1,
          },
        }),
      ),
    ).toBeNull();
    expect(
      announcementSourceId(
        notification({
          source: { condition: "other", ref: "announcement:42", version: 1 },
        }),
      ),
    ).toBeNull();
  });

  it("keeps lifecycle, responsibility and disabled reasons explicit", () => {
    expect(notificationStateLabel("seen")).toBe("Visto");
    expect(notificationStateLabel("resolved")).toBe("Resolvido");
    expect(notificationOwnerLabel("ops")).toBe("Operações");
    expect(notificationReasonLabel("missing_capability")).toContain("acesso");
  });

  it("keeps an explicit DOM anchor around the canonical review context", () => {
    const page = readFileSync(
      fileURLToPath(
        new URL("../app/pages/announcements/[id].vue", import.meta.url),
      ),
      "utf8",
    );

    expect(page).toMatch(
      /<section[\s\S]*id="review"[\s\S]*aria-label="Revisão do anúncio"/,
    );
  });
});
