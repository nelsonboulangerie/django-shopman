import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "vue-sonner";
import { computed, ref } from "vue";

import type { Action, POSProjection } from "~/types/pos";
import { usePosCashSession } from "~/composables/usePosCashSession";

import { makeProjection } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

function makeCashSession(opts: {
  projection?: POSProjection | null;
  actionCall?: ReturnType<typeof vi.fn>;
} = {}) {
  const posValue = ref<POSProjection | null>(
    opts.projection === undefined ? makeProjection() : opts.projection,
  );
  const actionsValue = ref<Action[]>([]);
  const actionCall = opts.actionCall ?? vi.fn().mockResolvedValue({});
  const refresh = vi.fn().mockResolvedValue(undefined);
  const session = usePosCashSession({
    pos: computed(() => posValue.value),
    actions: computed(() => actionsValue.value),
    refresh,
    action: { call: actionCall },
  });
  return { session, posValue, actionCall, refresh };
}

describe("usePosCashSession — sessão de caixa (antesala)", () => {
  beforeEach(() => {
    vi.mocked(toast.error).mockClear();
  });

  it("movementKinds cai no default quando a capability não veio", () => {
    const { session } = makeCashSession();
    expect(session.movementKinds.value).toEqual(["sangria", "suprimento", "ajuste"]);
  });

  it("movementKinds lê a capability do contrato quando presente", () => {
    const projection = makeProjection({
      checkout: {
        intent_version: 1,
        capabilities: { cash_management: { movement_kinds: ["sangria"] } },
      } as POSProjection["checkout"],
    });
    const { session } = makeCashSession({ projection });
    expect(session.movementKinds.value).toEqual(["sangria"]);
  });

  it("shiftRequiredForSale segue o contrato (default seguro = exigido)", () => {
    const { session } = makeCashSession();
    expect(session.shiftRequiredForSale.value).toBe(true);
    const optOut = makeProjection({
      checkout: {
        intent_version: 1,
        capabilities: { cash_management: { requires_open_shift_for_sale: false } },
      } as POSProjection["checkout"],
    });
    const { session: relaxed } = makeCashSession({ projection: optOut });
    expect(relaxed.shiftRequiredForSale.value).toBe(false);
  });

  it("abrir caixa envia valor + terminal, dá refresh e devolve true", async () => {
    const { session, actionCall, refresh } = makeCashSession();
    const ok = await session.openCashShift("50,00");
    expect(ok).toBe(true);
    expect(actionCall).toHaveBeenCalledWith(
      "/api/v1/backstage/pos/cash/open/",
      { body: { opening_amount: "50,00", terminal_ref: "T1" } },
    );
    expect(refresh).toHaveBeenCalled();
  });

  it("falha vira toast e devolve false (sem engolir silenciosamente)", async () => {
    const actionCall = vi.fn().mockRejectedValue(new Error("boom"));
    const { session, refresh } = makeCashSession({ actionCall });
    const ok = await session.closeCashShift({ amount: "10", notes: "" });
    expect(ok).toBe(false);
    expect(toast.error).toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
    expect(session.busy.value).toBe(false);
  });

  it("guarda de reentrância: busy bloqueia novo comando", async () => {
    const { session, actionCall } = makeCashSession();
    session.busy.value = true;
    const ok = await session.registerCashMovement({ kind: "sangria", amount: "5", reason: "troco" });
    expect(ok).toBe(false);
    expect(actionCall).not.toHaveBeenCalled();
  });

  it("fechar turno bloqueante envia shift_id e contagem cega", async () => {
    const { session, actionCall } = makeCashSession();
    await session.closeBlockingShift({ shift_id: 7, amount: "", notes: "turno órfão" });
    expect(actionCall).toHaveBeenCalledWith(
      "/api/v1/backstage/pos/cash/close-blocking/",
      { body: { shift_id: 7, closing_amount: "0", notes: "turno órfão" } },
    );
  });

  it("movimento envia kind/valor/motivo", async () => {
    const { session, actionCall } = makeCashSession();
    await session.registerCashMovement({ kind: "suprimento", amount: "20,00", reason: "troco" });
    expect(actionCall).toHaveBeenCalledWith(
      "/api/v1/backstage/pos/cash/movement/",
      { body: { kind: "suprimento", amount: "20,00", reason: "troco" } },
    );
  });
});

// ── Gaveta ────────────────────────────────────────────────────────────────

const AGENT_DRAWER = {
  adapter: "agent",
  can_kick: true,
  open_on_cash_sale: true,
  agent_url: "http://127.0.0.1:47811",
  token: "token-do-balcao",
  pulse: { pin: 0, on_ms: 50, off_ms: 500 },
} satisfies POSProjection["cash_drawer"];

function makeDrawerSession(opts: { actionCall?: ReturnType<typeof vi.fn> } = {}) {
  const kicks: string[] = [];
  vi.stubGlobal("fetch", vi.fn((_url: string, init?: RequestInit) => {
    kicks.push(JSON.parse(init!.body as string).reason);
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ok: true }) });
  }));
  const made = makeCashSession({
    projection: makeProjection({ cash_drawer: AGENT_DRAWER }),
    actionCall: opts.actionCall,
  });
  return { ...made, kicks };
}

describe("usePosCashSession — a gaveta nos momentos que não imprimem nada", () => {
  beforeEach(() => vi.mocked(toast.error).mockClear());
  afterEach(() => vi.unstubAllGlobals());

  it("sangria abre a gaveta — é onde o gancho do driver nunca chegaria", async () => {
    const { session, kicks } = makeDrawerSession();
    await session.registerCashMovement({ kind: "sangria", amount: "50", reason: "cofre" });
    expect(kicks).toEqual(["sangria"]);
  });

  it("suprimento abre a gaveta", async () => {
    const { session, kicks } = makeDrawerSession();
    await session.registerCashMovement({ kind: "suprimento", amount: "50", reason: "troco" });
    expect(kicks).toEqual(["suprimento"]);
  });

  it("movimento RECUSADO não abre a gaveta", async () => {
    // Gaveta aberta por um lançamento que o servidor negou (PIN errado, caixa
    // fechado) é dinheiro exposto sem nada justificando.
    const actionCall = vi.fn().mockRejectedValue(new Error("recusado"));
    const { session, kicks } = makeDrawerSession({ actionCall });
    await session.registerCashMovement({ kind: "sangria", amount: "50", reason: "cofre" });
    expect(kicks).toEqual([]);
  });

  it("abrir sem venda REGISTRA antes de chutar", async () => {
    const { session, actionCall, kicks } = makeDrawerSession();
    expect(await session.openDrawerWithoutSale("Troco")).toBe(true);
    expect(actionCall).toHaveBeenCalledWith(
      "/api/v1/backstage/pos/cash/drawer-open/",
      { body: { reason: "Troco" } },
    );
    expect(kicks).toEqual(["no_sale"]);
  });

  it("se o registro falhar, a gaveta NÃO abre — senão volta o buraco da chave", async () => {
    const actionCall = vi.fn().mockRejectedValue(new Error("sem turno"));
    const { session, kicks } = makeDrawerSession({ actionCall });
    expect(await session.openDrawerWithoutSale("Troco")).toBe(false);
    expect(kicks).toEqual([]);
  });

  it("balcão de gaveta com chave não oferece o botão", () => {
    const { session } = makeCashSession({
      projection: makeProjection({
        cash_drawer: { adapter: "manual", can_kick: false, open_on_cash_sale: false },
      }),
    });
    expect(session.canOpenDrawer.value).toBe(false);
  });
});
