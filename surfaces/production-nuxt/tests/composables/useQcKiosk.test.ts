import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useQcKiosk } from "~/composables/useQcKiosk";

const env = installNuxtGlobals();

function qcPayload(overrides: Record<string, unknown> = {}) {
  return {
    qc: {
      selected_date: "2026-09-08",
      selected_date_display: "Hoje",
      orders: [],
      closed_count: 0,
      total_count: 0,
      grades: [],
      defects: [],
      recipes: [],
      previous_open_count: 0,
      previous_open_date: "",
      access: {},
      generated_at: "2099-01-01T11:59:00Z",
      source_revision: "qc:1",
      fresh_until: "2099-01-01T12:01:00Z",
      contract_version: 1,
      actions: [
        {
          ref: "finish:42",
          enabled: true,
          proof: "finish-proof",
          expected_rev: 3,
        },
        {
          ref: "quick_finish:7",
          enabled: true,
          proof: "quick-proof",
          expected_rev: null,
        },
      ],
      ...overrides,
    },
  };
}

describe("useQcKiosk — guarded writes", () => {
  beforeEach(() => env.reset());

  it("sends projection metadata on finish and quick-finish", async () => {
    env.fetchData.value = qcPayload();
    const { finish, quickFinish } = useQcKiosk();
    const partition = [{ quantity: "12", quality_grade_ref: "excellent" }];

    await finish(42, 3, "12", partition);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/production/42/finish/",
      expect.objectContaining({
        body: expect.objectContaining({
          projection_generated_at: "2099-01-01T11:59:00Z",
          source_revision: "qc:1",
          fresh_until: "2099-01-01T12:01:00Z",
          contract_version: 1,
          action_ref: "finish:42",
          action_proof: "finish-proof",
        }),
      }),
    );

    await quickFinish(7, "12", partition);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/production/quick-finish/",
      expect.objectContaining({
        body: expect.objectContaining({
          source_revision: "qc:1",
          contract_version: 1,
          action_ref: "quick_finish:7",
          action_proof: "quick-proof",
        }),
      }),
    );
  });

  it("blocks both closing paths on stale data and leaves the partition untouched", async () => {
    env.fetchData.value = qcPayload({ fresh_until: "2020-01-01T00:00:00Z" });
    const partition = [{ quantity: "8", quality_grade_ref: "standard" }];
    const { finish, quickFinish, submitting } = useQcKiosk();

    expect((await finish(42, 3, "8", partition)).blocked?.code).toBe(
      "stale_projection",
    );
    expect((await quickFinish(7, "8", partition)).blocked?.code).toBe(
      "stale_projection",
    );
    expect(env.fetchMock).not.toHaveBeenCalled();
    expect(submitting.value).toBe(false);
    expect(partition).toEqual([{ quantity: "8", quality_grade_ref: "standard" }]);
  });

  it("carries the shortage continuation proof on the force retry", async () => {
    env.fetchData.value = qcPayload();
    const { finish } = useQcKiosk();
    const partition = [{ quantity: "12", quality_grade_ref: "standard" }];

    await finish(
      42,
      3,
      "12",
      partition,
      true,
      "autorizado pelo gestor",
      false,
      "",
      "signed-shortage-proof",
    );

    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/production/42/finish/",
      expect.objectContaining({
        body: expect.objectContaining({
          force: true,
          reason: "autorizado pelo gestor",
          override_proof: "signed-shortage-proof",
        }),
      }),
    );
  });
});
