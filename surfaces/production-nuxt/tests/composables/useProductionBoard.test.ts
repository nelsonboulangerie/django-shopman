import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { defaultPlanningDate, useProductionBoard } from "~/composables/useProductionBoard";

const env = installNuxtGlobals();

function boardPayload(overrides: Record<string, unknown> = {}) {
  return {
    board: {
      selected_date: "2026-07-06",
      selected_date_display: "domingo, 6 de julho",
      selected_position_ref: "forno",
      default_position_pk: 1,
      positions: [{ pk: 1, ref: "forno", name: "Forno", is_default: true }],
      access: {},
      generated_at: "2099-01-01T11:59:00Z",
      source_revision: "board:1",
      fresh_until: "2099-01-01T12:01:00Z",
      contract_version: 1,
      actions: [
        {
          ref: "plan:5:2026-07-06:forno",
          enabled: true,
          proof: "plan-proof",
          expected_rev: null,
        },
        {
          ref: "plan_suggested:5:2026-07-06:forno:8",
          enabled: true,
          proof: "suggested-proof",
          expected_rev: null,
        },
        {
          ref: "start:42",
          enabled: true,
          proof: "start-proof",
          expected_rev: 3,
        },
      ],
      base_recipes: [],
      matrix_rows: [{ output_sku: "PAO-001", recipe_name: "Pão", planned_qty: "0" }],
      counts: { planned: 3, started: 1, finished: 0 },
      ...overrides,
    },
  };
}

describe("useProductionBoard — default date", () => {
  beforeEach(() => env.reset());

  it("honra a data inicial recebida (Produção abre em HOJE, não no default de planejamento)", () => {
    env.fetchData.value = boardPayload();
    const { selectedDate } = useProductionBoard("2026-01-15");
    // A grade da Produção passa HOJE explicitamente; o composable não force o
    // default de planejamento (amanhã à tarde) por cima.
    expect(selectedDate.value).toBe("2026-01-15");
  });

  it("sem argumento, mantém o default de planejamento (compatível)", () => {
    env.fetchData.value = boardPayload();
    const { selectedDate } = useProductionBoard();
    expect(selectedDate.value).toBe(defaultPlanningDate());
  });
});

describe("useProductionBoard — read derivations", () => {
  beforeEach(() => env.reset());

  it("derives board/rows/counts/dateDisplay from the fetch payload", () => {
    env.fetchData.value = boardPayload();
    const { board, rows, counts, dateDisplay } = useProductionBoard();
    expect(board.value?.selected_date).toBe("2026-07-06");
    expect(rows.value).toHaveLength(1);
    expect(counts.value?.planned).toBe(3);
    expect(dateDisplay.value).toBe("domingo, 6 de julho");
  });

  it("degrades to safe empties when the payload is null (never throws)", () => {
    env.fetchData.value = null;
    const { board, rows, counts, dateDisplay } = useProductionBoard();
    expect(board.value).toBeNull();
    expect(rows.value).toEqual([]);
    expect(counts.value).toBeNull();
    expect(dateDisplay.value).toBe("");
  });
});

describe("useProductionBoard — plan/start writes", () => {
  beforeEach(() => env.reset());

  it("plan POSTs to the plan endpoint and reconciles via refresh on success", async () => {
    env.fetchData.value = boardPayload();
    const { plan } = useProductionBoard();
    const res = await plan("PAO-001", {
      recipe_id: 5,
      quantity: "12",
      target_date: "2026-07-06",
      position_ref: "forno",
      expected_rev: null,
    });
    expect(res.ok).toBe(true);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/production/plan/",
      expect.objectContaining({
        method: "POST",
        body: expect.objectContaining({
          recipe_id: 5,
          quantity: "12",
          expected_rev: null,
          projection_generated_at: "2099-01-01T11:59:00Z",
          source_revision: "board:1",
          fresh_until: "2099-01-01T12:01:00Z",
          contract_version: 1,
          action_ref: "plan:5:2026-07-06:forno",
          action_proof: "plan-proof",
          idempotency_key: expect.any(String),
        }),
      }),
    );
    expect(env.refresh).toHaveBeenCalledOnce();
  });

  it("start POSTs to the per-WO start endpoint", async () => {
    env.fetchData.value = boardPayload();
    const { start } = useProductionBoard();
    const res = await start("PAO-001", 42, 3, "30");
    expect(res.ok).toBe(true);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/production/42/start/",
      expect.objectContaining({
        method: "POST",
        body: expect.objectContaining({
          quantity: "30",
          expected_rev: 3,
          projection_generated_at: "2099-01-01T11:59:00Z",
          source_revision: "board:1",
          fresh_until: "2099-01-01T12:01:00Z",
          contract_version: 1,
          action_ref: "start:42",
          action_proof: "start-proof",
          idempotency_key: expect.any(String),
        }),
      }),
    );
  });

  it("uses the quantity-bound suggested action and preserves an override proof", async () => {
    env.fetchData.value = boardPayload();
    const { plan } = useProductionBoard();

    await plan("PAO-001", {
      recipe_id: 5,
      quantity: "8.000",
      target_date: "2026-07-06",
      position_ref: "forno",
      expected_rev: null,
      source: "suggested",
      force: true,
      reason: "autorizado",
      override_proof: "shortage-proof",
    });

    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/production/plan/",
      expect.objectContaining({
        body: expect.objectContaining({
          action_ref: "plan_suggested:5:2026-07-06:forno:8",
          action_proof: "suggested-proof",
          override_proof: "shortage-proof",
        }),
      }),
    );
  });

  it("guards against a second in-flight write on the same row (optimistic dedup)", async () => {
    env.fetchData.value = boardPayload();
    let release!: () => void;
    env.fetchMock.mockImplementationOnce(() => new Promise<void>((r) => (release = r)));
    const { plan, isBusy } = useProductionBoard();

    const first = plan("PAO-001", {
      recipe_id: 5,
      quantity: "12",
      target_date: "2026-07-06",
      position_ref: "forno",
      expected_rev: null,
    });
    expect(isBusy("PAO-001")).toBe(true);
    const second = await plan("PAO-001", {
      recipe_id: 5,
      quantity: "9",
      target_date: "2026-07-06",
      position_ref: "forno",
      expected_rev: null,
    });
    expect(second.ok).toBe(false); // rejected while first still in flight
    expect(env.fetchMock).toHaveBeenCalledTimes(1);

    release();
    await first;
    expect(isBusy("PAO-001")).toBe(false); // rolled back after settle
  });

  it("surfaces a structured shortage instead of a toast when the server reports one", async () => {
    env.fetchData.value = boardPayload();
    env.fetchMock.mockRejectedValueOnce({ data: { error: { code: "material_shortage", missing: [] } } });
    const { plan } = useProductionBoard();
    const res = await plan("PAO-001", {
      recipe_id: 5,
      quantity: "12",
      target_date: "2026-07-06",
      position_ref: "forno",
      expected_rev: null,
    });
    expect(res.ok).toBe(false);
    expect(res.shortage?.code).toBe("material_shortage");
    expect(env.sonner.error).not.toHaveBeenCalled();
  });

  it("toasts a friendly message on a generic failure", async () => {
    env.fetchData.value = boardPayload();
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "Banco fora do ar" } });
    const { start } = useProductionBoard();
    const res = await start("PAO-001", 42, 3, "30");
    expect(res.ok).toBe(false);
    expect(env.sonner.error).toHaveBeenCalledWith("Banco fora do ar");
  });

  it("blocks an expired projection before POST and preserves the submitted payload", async () => {
    env.fetchData.value = boardPayload({ fresh_until: "2020-01-01T00:00:00Z" });
    const payload = {
      recipe_id: 5,
      quantity: "12",
      target_date: "2026-07-06",
      position_ref: "forno",
      expected_rev: null,
    };
    const result = await useProductionBoard().plan("PAO-001", payload);

    expect(result.blocked?.code).toBe("stale_projection");
    expect(env.fetchMock).not.toHaveBeenCalled();
    expect(payload.quantity).toBe("12");
    expect(env.sonner.error).toHaveBeenCalledWith(
      expect.stringContaining("desatualizados"),
      expect.objectContaining({ action: expect.objectContaining({ label: "Atualizar dados" }) }),
    );
  });

  it("honors the stale_projection recovery returned by the contract", async () => {
    env.fetchData.value = boardPayload();
    env.fetchMock.mockRejectedValueOnce({
      data: {
        detail: "A projeção venceu.",
        error: {
          code: "stale_projection",
          age_seconds: 91,
          sent_rev: 3,
          current_rev: 4,
          current: null,
          recovery: { action: "refresh", label: "Recarregar quadro" },
        },
      },
    });

    const result = await useProductionBoard().start("PAO-001", 42, 3, "30");
    expect(result.ok).toBe(false);
    expect(env.sonner.error).toHaveBeenCalledWith(
      "A projeção venceu.",
      expect.objectContaining({
        action: expect.objectContaining({ label: "Recarregar quadro" }),
      }),
    );

    const options = env.sonner.error.mock.calls[0]?.[1] as {
      action: { onClick: () => void };
    };
    options.action.onClick();
    expect(env.refresh).toHaveBeenCalledOnce();
  });
});

describe("defaultPlanningDate", () => {
  it("plans today in the morning, tomorrow after noon (baker's calm-afternoon rhythm)", () => {
    expect(defaultPlanningDate(new Date("2026-07-06T12:00:00Z"))).toBe("2026-07-06");
    expect(defaultPlanningDate(new Date("2026-07-06T16:00:00Z"))).toBe("2026-07-07");
  });

  it("uses the bakery clock during the UTC/BRT date gap", () => {
    // 23:30 BRT ainda é 09/set, mas o planejamento já aponta para amanhã.
    expect(defaultPlanningDate(new Date("2026-09-10T02:30:00Z"))).toBe("2026-09-10");
  });
});
