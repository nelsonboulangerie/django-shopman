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
    expect(session.movementKinds.value).toEqual(["sangria", "suprimento"]);
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

  // O "fechar turno bloqueante" saiu com a custódia da gaveta: não existe mais
  // turno de outra pessoa segurando o terminal, então não há o que destravar.
  // Fechar o caixa é um caminho só (`closeCashShift`), e é da gerência.

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

describe("usePosCashSession — o comprovante sai sozinho e o resultado é registrado", () => {
  beforeEach(() => vi.mocked(toast.error).mockClear());
  afterEach(() => vi.unstubAllGlobals());

  function makeReceiptSession(opts: { agentFails?: boolean } = {}) {
    const agentCalls: string[] = [];
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      agentCalls.push(String(url));
      if (opts.agentFails && String(url).endsWith("/print")) {
        return Promise.reject(new TypeError("Failed to fetch"));
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ok: true }) });
    }));

    const servidor: { path: string; body?: Record<string, unknown>; method?: string }[] = [];
    const actionCall = vi.fn((path: string, opts2?: { method?: string; body?: Record<string, unknown> }) => {
      servidor.push({ path, body: opts2?.body, method: opts2?.method });
      // `includes`, não `endsWith`: o GET agora carrega query (`terminal_ref`,
      // e `reprint=1` na segunda via).
      if (path.includes("/receipt/") && opts2?.method === "GET") {
        return Promise.resolve({ payload_b64: "SEVMTE8=", title: "comprovante:sangria" });
      }
      if (path.includes("/cash/movement/")) {
        return Promise.resolve({ ok: true, entry_id: 77 });
      }
      return Promise.resolve({ ok: true, entry_id: 77 });
    });

    const made = makeCashSession({
      projection: makeProjection({ cash_drawer: AGENT_DRAWER }),
      actionCall,
    });
    return { ...made, servidor, agentCalls };
  }

  it("sangria imprime sozinha — testemunha não pode depender de clique", async () => {
    const { session, servidor, agentCalls } = makeReceiptSession();
    await session.registerCashMovement({ kind: "sangria", amount: "50", reason: "cofre" });
    await new Promise((r) => setTimeout(r, 10));

    expect(agentCalls.some((u) => u.endsWith("/print"))).toBe(true);
    // O comprovante sai da LINHA do livro (`entry_id`), não de um "movimento".
    expect(servidor.some((c) => c.path === "/api/v1/backstage/pos/cash/entry/77/receipt/")).toBe(true);
    const registro = servidor.find((c) => c.path.endsWith("/receipt/") && c.body);
    expect(registro?.body).toMatchObject({ status: "printed" });
  });

  it("papel que NÃO saiu vira registro de falha, com motivo", async () => {
    // Sem isto, papel que faltou pareceria papel que alguém escondeu.
    const { session, servidor } = makeReceiptSession({ agentFails: true });
    await session.registerCashMovement({ kind: "sangria", amount: "50", reason: "cofre" });
    await new Promise((r) => setTimeout(r, 10));

    const registro = servidor.find((c) => c.path.endsWith("/receipt/") && c.body);
    expect(registro?.body?.status).toBe("failed");
    expect(String(registro?.body?.detail)).toContain("não está rodando");
    expect(vi.mocked(toast.error)).toHaveBeenCalled();
  });

  it("a falha de impressão NÃO desfaz o movimento", async () => {
    // O dinheiro já saiu e o registro já existe; travar o caixa porque a
    // impressora emperrou é remédio pior que a doença.
    const { session } = makeReceiptSession({ agentFails: true });
    const ok = await session.registerCashMovement({ kind: "sangria", amount: "50", reason: "cofre" });
    expect(ok).toBe(true);
  });

  it("movimento RECUSADO não imprime nada", async () => {
    // Comprovante de sangria que o servidor negou (PIN errado, caixa fechado)
    // seria papel atestando dinheiro que não saiu.
    const agentCalls: string[] = [];
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      agentCalls.push(String(url));
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ok: true }) });
    }));
    const actionCall = vi.fn().mockRejectedValue(new Error("recusado"));
    const { session } = makeCashSession({
      projection: makeProjection({ cash_drawer: AGENT_DRAWER }),
      actionCall,
    });

    const ok = await session.registerCashMovement({ kind: "sangria", amount: "50", reason: "cofre" });
    await new Promise((r) => setTimeout(r, 10));

    expect(ok).toBe(false);
    expect(agentCalls).toEqual([]);
  });

  it("a segunda via pede ?reprint=1 na linha do livro, imprime e registra", async () => {
    // A porta que a promessa "pode ser reimpresso depois" não tinha: o servidor
    // já aceitava `?reprint=1` e ninguém chamava.
    const { session, servidor, agentCalls } = makeReceiptSession();

    const ok = await session.reprintMovementReceipt(77);
    await new Promise((r) => setTimeout(r, 10));

    expect(ok).toBe(true);
    const pedido = servidor.find((c) => c.method === "GET");
    expect(pedido?.path).toContain("/cash/entry/77/receipt/");
    expect(pedido?.path).toContain("reprint=1");
    // A busca fica presa à GAVETA desta superfície, não ao primeiro terminal.
    expect(pedido?.path).toContain("terminal_ref=T1");
    expect(agentCalls.some((u) => u.endsWith("/print"))).toBe(true);
    const registro = servidor.find((c) => c.path.endsWith("/receipt/") && c.body);
    expect(registro?.body).toMatchObject({ status: "printed" });
  });

  it("o toast de falha oferece 'Tentar de novo' — falha sem porta é beco", async () => {
    // Mesmo dialeto dos comprovantes de venda (PosRecentSales): rótulo e
    // instrução de reinício do agente vieram do #312; a porta da segunda via
    // (`reprint`) é daqui — o retry repete as MESMAS opções.
    const { session } = makeReceiptSession({ agentFails: true });
    await session.registerCashMovement({ kind: "sangria", amount: "50", reason: "cofre" });
    await new Promise((r) => setTimeout(r, 10));

    const chamadas = vi.mocked(toast.error).mock.calls;
    const opcoes = chamadas[chamadas.length - 1]?.[1] as { action?: { label?: unknown } } | undefined;
    expect(opcoes?.action?.label).toBe("Tentar de novo");
  });
});

// ── Pedido de troco ───────────────────────────────────────────────────────
//
// O operador pede troco em vez de atravessar a loja com dinheiro até o cofre. O
// gerente traz, assina, a gaveta abre e a troca acontece no balcão.
//
// ⚠️ A regra que não pode cair: trocar é NET ZERO. Nenhuma destas chamadas pode
// virar movimento de caixa — o esperado do fechamento não pode sentir nada.

describe("usePosCashSession — pedido de troco (o dinheiro fica no balcão)", () => {
  beforeEach(() => vi.mocked(toast.error).mockClear());
  afterEach(() => vi.unstubAllGlobals());

  it("pedir troco envia valor, denominações e observação", async () => {
    const { session, actionCall } = makeCashSession();
    const ok = await session.requestChange({
      amount: "100,00", denominations: [500, 50], note: "acabou moeda",
    });
    expect(ok).toBe(true);
    expect(actionCall).toHaveBeenCalledWith(
      "/api/v1/backstage/pos/cash/change-request/",
      { body: { amount: "100,00", denominations: [500, 50], note: "acabou moeda" } },
    );
  });

  it("a antesala lê os pendentes do cash_runtime", () => {
    const { session } = makeCashSession({
      projection: makeProjection({
        cash_runtime: {
          pending_change_requests: [
            { ref: "a1", amount_q: 10000, amount_display: "R$ 100,00", denominations: [50], note: "", requested_by: "marina", requested_at: "" },
          ],
        } as POSProjection["cash_runtime"],
      }),
    });
    expect(session.pendingChangeRequests.value).toHaveLength(1);
    expect(session.pendingChangeRequests.value[0]!.ref).toBe("a1");
  });

  it("pendentes ausentes viram lista vazia, não explosão", () => {
    const { session } = makeCashSession();
    expect(session.pendingChangeRequests.value).toEqual([]);
  });

  it("atender manda o PIN do gerente para a ref do pedido", async () => {
    const { session, actionCall } = makeCashSession();
    await session.serveChangeRequest({ ref: "a1", managerApproval: { username: "pablo", pin: "4321" } });
    expect(actionCall).toHaveBeenCalledWith(
      "/api/v1/backstage/pos/cash/change-request/a1/serve/",
      { body: { manager_approval: { username: "pablo", pin: "4321" } } },
    );
  });

  it("atender abre a gaveta — é onde a troca acontece", async () => {
    const { session, kicks } = makeDrawerSession();
    await session.serveChangeRequest({ ref: "a1", managerApproval: { username: "pablo", pin: "4321" } });
    expect(kicks).toEqual(["change_request"]);
  });

  it("atendimento RECUSADO não abre a gaveta", async () => {
    // Gaveta aberta por um atendimento que o servidor negou (PIN errado, pedido
    // já resolvido) é dinheiro exposto sem nada justificando.
    const actionCall = vi.fn().mockRejectedValue(new Error("recusado"));
    const { session, kicks } = makeDrawerSession({ actionCall });
    await session.serveChangeRequest({ ref: "a1", managerApproval: { username: "pablo", pin: "4321" } });
    expect(kicks).toEqual([]);
  });

  it("cancelar bate na rota do pedido, sem corpo de dinheiro", async () => {
    const { session, actionCall } = makeCashSession();
    const ok = await session.cancelChangeRequest("a1");
    expect(ok).toBe(true);
    expect(actionCall).toHaveBeenCalledWith(
      "/api/v1/backstage/pos/cash/change-request/a1/cancel/",
      { body: {} },
    );
  });

  it("NENHUMA ação de troco encosta em movimento de caixa nem imprime comprovante", async () => {
    // A prova da regra, do lado da tela: se qualquer uma destas passar por
    // `cash/movement/`, o esperado do fechamento cai por um dinheiro que nunca
    // saiu e o turno fecha com falta fantasma (o defeito desfeito no PR #178).
    const { session, actionCall } = makeCashSession();
    await session.requestChange({ kind: "amount", amount: "50,00", note: "" });
    await session.serveChangeRequest({ ref: "a1", managerApproval: { username: "pablo", pin: "4321" } });
    await session.cancelChangeRequest("a2");
    await new Promise((r) => setTimeout(r, 10));

    const caminhos = actionCall.mock.calls.map((c) => String(c[0]));
    expect(caminhos.some((p) => p.includes("/cash/movement/"))).toBe(false);
    expect(caminhos.some((p) => p.includes("/receipt/"))).toBe(false);
    for (const caminho of caminhos) expect(caminho).toContain("/cash/change-request/");
  });
});

describe("usePosCashSession — devolução em dinheiro de venda cancelada (cancelar não é devolver)", () => {
  beforeEach(() => vi.mocked(toast.error).mockClear());
  afterEach(() => vi.unstubAllGlobals());

  it("a antesala lê as devoluções pendentes do cash_runtime", () => {
    const { session } = makeCashSession({
      projection: makeProjection({
        cash_runtime: {
          pending_cash_refunds: [
            { order_ref: "A01", amount_q: 1200, amount_display: "R$ 12,00", customer_name: "Ana", cancelled_at: "" },
          ],
        } as POSProjection["cash_runtime"],
      }),
    });
    expect(session.pendingCashRefunds.value).toHaveLength(1);
    expect(session.pendingCashRefunds.value[0]!.order_ref).toBe("A01");
  });

  it("pendentes ausentes viram lista vazia", () => {
    const { session } = makeCashSession();
    expect(session.pendingCashRefunds.value).toEqual([]);
  });

  it("devolver manda o PIN do gerente para a rota do pedido", async () => {
    const { session, actionCall } = makeCashSession();
    await session.refundCash({ orderRef: "A01", managerApproval: { username: "pablo", pin: "4321" } });
    expect(actionCall).toHaveBeenCalledWith(
      "/api/v1/backstage/pos/cash/refund/A01/",
      { body: { manager_approval: { username: "pablo", pin: "4321" } } },
    );
  });

  it("devolver abre a gaveta: é de onde as notas saem", async () => {
    const { session, kicks } = makeDrawerSession();
    await session.refundCash({ orderRef: "A01", managerApproval: { username: "pablo", pin: "4321" } });
    expect(kicks).toEqual(["cash_refund"]);
  });

  it("devolução RECUSADA não abre a gaveta", async () => {
    const actionCall = vi.fn().mockRejectedValue(new Error("recusado"));
    const { session, kicks } = makeDrawerSession({ actionCall });
    await session.refundCash({ orderRef: "A01", managerApproval: { username: "pablo", pin: "4321" } });
    expect(kicks).toEqual([]);
  });
});
