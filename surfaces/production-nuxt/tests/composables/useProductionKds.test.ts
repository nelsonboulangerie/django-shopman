import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useProductionKds } from "~/composables/useProductionKds";

const env = installNuxtGlobals();

function kdsPayload(cards: unknown[] = [], overrides: Record<string, unknown> = {}) {
  return {
    kds: {
      cards,
      total_count: cards.length,
      late_count: 0,
      generated_at: "2099-01-01T11:59:00Z",
      source_revision: "kds:1",
      fresh_until: "2099-01-01T12:01:00Z",
      contract_version: 1,
      actions: [
        {
          ref: "advance_step:7",
          enabled: true,
          proof: "advance-proof",
          expected_rev: 4,
        },
        {
          ref: "void:7",
          enabled: true,
          proof: "void-proof",
          expected_rev: 5,
        },
      ],
      ...overrides,
    },
  };
}

describe("useProductionKds — read derivations", () => {
  beforeEach(() => env.reset());

  it("derives cards/totalCount/lateCount", () => {
    env.fetchData.value = kdsPayload([{ pk: 1 }, { pk: 2 }], { late_count: 1 });
    const { cards, totalCount, lateCount } = useProductionKds();
    expect(cards.value).toHaveLength(2);
    expect(totalCount.value).toBe(2);
    expect(lateCount.value).toBe(1);
  });

  it("degrades to empties when payload null", () => {
    env.fetchData.value = null;
    const { cards, totalCount, lateCount } = useProductionKds();
    expect(cards.value).toEqual([]);
    expect(totalCount.value).toBe(0);
    expect(lateCount.value).toBe(0);
  });
});

describe("useProductionKds — adaptive cadence under pressure", () => {
  beforeEach(() => env.reset());

  it("tightens the poll to 10s when something is late, 30s at rest (visibility-aware)", () => {
    env.fetchData.value = kdsPayload([{ pk: 1 }], { late_count: 2 });
    useProductionKds();
    // useAdaptivePoll(refresh, intervalFn) — capture the cadence function it was given.
    const intervalFn = env.adaptivePoll.mock.calls[0]?.[1] as () => number;
    expect(intervalFn()).toBe(10_000);
  });

  it("stays at the routine 30s cadence when nothing is late", () => {
    env.fetchData.value = kdsPayload([{ pk: 1 }], { late_count: 0 });
    useProductionKds();
    const intervalFn = env.adaptivePoll.mock.calls[0]?.[1] as () => number;
    expect(intervalFn()).toBe(30_000);
  });
});

describe("useProductionKds — per-WO writes", () => {
  beforeEach(() => env.reset());

  it("advanceStep / voidOrder hit the right endpoints (o finish vive no quiosque de QC)", async () => {
    env.fetchData.value = kdsPayload();
    const { advanceStep, voidOrder } = useProductionKds();

    await advanceStep(7, 4);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/production/7/advance-step/",
      expect.objectContaining({
        method: "POST",
        body: expect.objectContaining({
          expected_rev: 4,
          projection_generated_at: "2099-01-01T11:59:00Z",
          source_revision: "kds:1",
          fresh_until: "2099-01-01T12:01:00Z",
          contract_version: 1,
          action_ref: "advance_step:7",
          action_proof: "advance-proof",
          idempotency_key: expect.any(String),
        }),
      }),
    );

    await voidOrder(7, 5, "queimou");
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/production/7/void/",
      expect.objectContaining({
        body: expect.objectContaining({
          reason: "queimou",
          expected_rev: 5,
          projection_generated_at: "2099-01-01T11:59:00Z",
          source_revision: "kds:1",
          fresh_until: "2099-01-01T12:01:00Z",
          contract_version: 1,
          action_ref: "void:7",
          action_proof: "void-proof",
          idempotency_key: expect.any(String),
        }),
      }),
    );
  });

  it("guards a second in-flight action on the same WO", async () => {
    env.fetchData.value = kdsPayload();
    let release!: () => void;
    env.fetchMock.mockImplementationOnce(() => new Promise<void>((r) => (release = r)));
    const { voidOrder, isBusy } = useProductionKds();

    const first = voidOrder(7, 5, "queimou");
    expect(isBusy(7)).toBe(true);
    const second = await voidOrder(7, 5, "queimou");
    expect(second.ok).toBe(false);
    expect(env.fetchMock).toHaveBeenCalledTimes(1);

    release();
    await first;
    expect(isBusy(7)).toBe(false);
  });

  it("returns the shortage (retryable with force) instead of toasting", async () => {
    env.fetchData.value = kdsPayload();
    env.fetchMock.mockRejectedValueOnce({ data: { error: { code: "order_shortage" } } });
    const { voidOrder } = useProductionKds();
    const res = await voidOrder(7, 5, "estorno");
    expect(res.shortage?.code).toBe("order_shortage");
    expect(env.sonner.error).not.toHaveBeenCalled();
  });

  it("toasts on a non-shortage failure", async () => {
    env.fetchData.value = kdsPayload();
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "erro" } });
    const { advanceStep } = useProductionKds();
    expect((await advanceStep(7, 4)).ok).toBe(false);
    expect(env.sonner.error).toHaveBeenCalledWith("erro");
  });

  it("blocks advance and void while offline without consuming the form input", async () => {
    env.fetchData.value = kdsPayload();
    env.isOnline.value = false;
    const reason = "queimou";
    const { advanceStep, voidOrder } = useProductionKds();

    expect((await advanceStep(7, 4)).blocked?.code).toBe("offline");
    expect((await voidOrder(7, 5, reason)).blocked?.code).toBe("offline");
    expect(reason).toBe("queimou");
    expect(env.fetchMock).not.toHaveBeenCalled();
  });
});
