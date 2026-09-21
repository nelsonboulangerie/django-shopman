import { beforeEach, describe, expect, it, vi } from "vitest";
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

  // ── Números vencidos na tela (a mensagem "dados desatualizados", 21/09) ──
  // A projeção vale 90 s a partir de quando CHEGOU a este dispositivo. Vencida,
  // a própria tela busca números novos antes de desistir do toque.

  const T0 = Date.parse("2026-09-21T15:00:00Z");
  const boardData = () =>
    env.useFetchMock.mock.results.at(-1)!.value.data as { value: unknown };

  // boardPayload vale 120 s (11:59:00 → 12:01:00).
  function expireAfterReceipt(seconds = 121) {
    vi.setSystemTime(T0 + seconds * 1_000);
  }

  it("expired and the server does not answer: blocks before POST, preserves the input, says nothing was saved", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(T0);
    try {
      env.fetchData.value = boardPayload();
      const payload = {
        recipe_id: 5,
        quantity: "12",
        target_date: "2026-07-06",
        position_ref: "forno",
        expected_rev: null,
      };
      const { plan } = useProductionBoard();
      expireAfterReceipt();
      const result = await plan("PAO-001", payload);

      expect(env.refresh).toHaveBeenCalledOnce(); // tentou buscar antes de desistir
      expect(result.blocked?.code).toBe("stale_projection");
      expect(env.fetchMock).not.toHaveBeenCalled();
      expect(payload.quantity).toBe("12");
      const [detail, options] = env.sonner.error.mock.calls[0]!;
      expect(detail).toMatch(/^Nada foi salvo/);
      expect(detail).toContain("continua aqui");
      expect(options).toEqual(
        expect.objectContaining({ action: expect.objectContaining({ label: "Tentar de novo" }) }),
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("expired but nothing changed: fetches fresh numbers and sends the tap without bothering the operator", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(T0);
    try {
      env.fetchData.value = boardPayload();
      const { start } = useProductionBoard();
      const data = boardData();
      env.refresh.mockImplementationOnce(async () => {
        data.value = boardPayload({
          generated_at: "2099-01-01T12:01:30Z",
          source_revision: "board:2",
          fresh_until: "2099-01-01T12:03:00Z",
        });
      });
      expireAfterReceipt();
      const res = await start("PAO-001", 42, 3, "30");

      expect(res.ok).toBe(true);
      expect(env.sonner.error).not.toHaveBeenCalled();
      expect(env.fetchMock).toHaveBeenCalledWith(
        "/api/v1/backstage/production/42/start/",
        expect.objectContaining({
          body: expect.objectContaining({ expected_rev: 3, source_revision: "board:2" }),
        }),
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("the device clock running ahead of the server no longer refuses a board that just arrived", async () => {
    // Relógio do tablet 10 min à frente: o `fresh_until` do servidor já "passou"
    // pelo relógio local no instante em que chega. Antes: toda ação recusada.
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(Date.parse("2099-01-01T12:10:00Z"));
    try {
      env.fetchData.value = boardPayload();
      const res = await useProductionBoard().start("PAO-001", 42, 3, "30");
      expect(res.ok).toBe(true);
      expect(env.refresh).toHaveBeenCalledOnce(); // só o reconcile pós-POST
    } finally {
      vi.useRealTimers();
    }
  });

  it("the board refreshed under an open dialog and the batch changed elsewhere: refuses instead of overwriting in silence", async () => {
    // O diálogo mostrava rev 3; o poll trouxe rev 4 (outra bancada ajustou).
    // Antes, o POST mandava a rev 4 da projeção e sobrescrevia a outra tela.
    env.fetchData.value = boardPayload({
      actions: [
        { ref: "plan:42", enabled: true, proof: "plan-42-proof", expected_rev: 4 },
        { ref: "start:42", enabled: true, proof: "start-proof", expected_rev: 4 },
      ],
    });
    const { plan, start } = useProductionBoard();

    const planned = await plan("PAO-001", {
      recipe_id: 5,
      work_order_id: 42,
      quantity: "40",
      target_date: "2026-07-06",
      position_ref: "forno",
      expected_rev: 3,
    });
    const started = await start("PAO-001", 42, 3, "30");

    expect(planned.blocked?.code).toBe("changed_elsewhere");
    expect(started.blocked?.code).toBe("changed_elsewhere");
    expect(env.fetchMock).not.toHaveBeenCalled();
    expect(env.sonner.error).toHaveBeenCalledWith(
      expect.stringContaining("outra tela alterou esta fornada"),
    );
  });

  it("a server-side stale refusal refreshes on its own and asks only to confirm again", async () => {
    env.fetchData.value = boardPayload();
    env.fetchMock.mockRejectedValueOnce({
      data: {
        detail: "Nada foi salvo: os números desta tela passaram do prazo antes de o pedido chegar.",
        error: {
          code: "stale_projection",
          age_seconds: 91,
          sent_rev: 3,
          current_rev: null,
          current: null,
          recovery: { action: "refresh", label: "Atualizar os números" },
        },
      },
    });

    const result = await useProductionBoard().start("PAO-001", 42, 3, "30");
    expect(result.ok).toBe(false);
    expect(env.sonner.error).toHaveBeenCalledWith(
      "Nada foi salvo: os números desta tela passaram do prazo antes de o pedido chegar.",
      { description: "Os números já foram atualizados — confira e confirme de novo." },
    );
    expect(env.refresh).toHaveBeenCalledOnce(); // sem depender de um toque
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
