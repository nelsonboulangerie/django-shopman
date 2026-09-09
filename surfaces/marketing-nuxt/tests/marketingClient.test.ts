import { describe, expect, it, vi } from "vitest";
import {
  MARKETING_V2_BOARD_PATH,
  createMarketingV2Client,
  type MarketingActionKind,
  type MarketingV2Transport,
} from "~/generated/marketingClient";

describe("generated Marketing v2 client", () => {
  it("uses only the OpenAPI paths and same-origin session transport", async () => {
    const calls: Array<{ href: string; options: unknown }> = [];
    const transport: MarketingV2Transport = async <T>(href: string, options: unknown) => {
      calls.push({ href, options });
      return {} as T;
    };
    const client = createMarketingV2Client(transport);

    await client.getMarketingBoard();
    await client.getMarketingAnnouncement(42);

    expect(calls).toEqual([
      {
        href: MARKETING_V2_BOARD_PATH,
        options: { method: "GET", credentials: "same-origin" },
      },
      {
        href: "/api/v1/backstage/marketing/v2/announcements/42/",
        options: { method: "GET", credentials: "same-origin" },
      },
    ]);
  });

  it("rejects an invalid resource id before touching the transport", () => {
    const transport = vi.fn() as MarketingV2Transport;
    const client = createMarketingV2Client(transport);

    expect(() => client.getMarketingAnnouncement(0)).toThrow(RangeError);
    expect(transport).not.toHaveBeenCalled();
  });

  it("exports the exact Action enum instead of widening it by hand", () => {
    const action: MarketingActionKind = "reconcile_unknown_delivery";
    expect(action).toBe("reconcile_unknown_delivery");
  });
});
