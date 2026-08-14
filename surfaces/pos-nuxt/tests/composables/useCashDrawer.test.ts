import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "vue-sonner";
import { computed, ref } from "vue";

import type { POSCashDrawerProjection, POSProjection } from "~/types/pos";
import { useCashDrawer } from "~/composables/useCashDrawer";

import { makeProjection } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const AGENT: POSCashDrawerProjection = {
  adapter: "agent",
  can_kick: true,
  open_on_cash_sale: true,
  agent_url: "http://127.0.0.1:47811",
  token: "token-do-balcao",
  pulse: { pin: 0, on_ms: 50, off_ms: 500 },
};

// `null` = terminal que não declarou gaveta. Não use `undefined`: passar
// `undefined` para um parâmetro com default reativa o default (aqui, AGENT).
function makeDrawer(cash_drawer: POSCashDrawerProjection | null = AGENT) {
  const posValue = ref<POSProjection | null>(
    makeProjection({ cash_drawer: cash_drawer ?? undefined }),
  );
  return useCashDrawer(computed(() => posValue.value));
}

function stubFetch(impl: (url: string, init?: RequestInit) => unknown) {
  const spy = vi.fn((url: string, init?: RequestInit) => Promise.resolve(impl(url, init)));
  vi.stubGlobal("fetch", spy);
  return spy;
}

const okResponse = (body: unknown) => ({ ok: true, status: 200, json: () => Promise.resolve(body) });

describe("useCashDrawer — o caminho físico da gaveta", () => {
  beforeEach(() => vi.mocked(toast.error).mockClear());
  afterEach(() => vi.unstubAllGlobals());

  it("manda token, motivo e o pulso que o terminal configurou", async () => {
    const fetchSpy = stubFetch(() => okResponse({ ok: true, queue: "TM-T20" }));
    const drawer = makeDrawer();

    expect(await drawer.kick("cash_sale")).toBe(true);

    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(url).toBe("http://127.0.0.1:47811/kick");
    expect(JSON.parse(init!.body as string)).toEqual({
      token: "token-do-balcao",
      reason: "cash_sale",
      pulse: { pin: 0, on_ms: 50, off_ms: 500 },
    });
  });

  it("balcão de gaveta com chave não bate no agente", async () => {
    const fetchSpy = stubFetch(() => okResponse({ ok: true }));
    const drawer = makeDrawer({ adapter: "manual", can_kick: false, open_on_cash_sale: false });

    expect(await drawer.kick("cash_sale")).toBe(false);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("terminal sem gaveta configurada não bate no agente", async () => {
    const fetchSpy = stubFetch(() => okResponse({ ok: true }));
    const drawer = makeDrawer(null);

    expect(await drawer.kick("cash_sale")).toBe(false);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("gaveta que não abriu AVISA — falha calada é o operador culpando a chave", async () => {
    stubFetch(() => ({ ok: false, status: 502, json: () => Promise.resolve({ error: "fila inexistente" }) }));
    const drawer = makeDrawer();

    expect(await drawer.kick("cash_sale")).toBe(false);
    expect(vi.mocked(toast.error).mock.calls[0]![0]).toContain("fila inexistente");
  });

  it("agente desligado vira instrução, não nome de exceção", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    const drawer = makeDrawer();

    expect(await drawer.kick("cash_sale")).toBe(false);
    expect(vi.mocked(toast.error).mock.calls[0]![0]).toContain("não está rodando");
  });

  it("nunca lança: a venda já aconteceu, e a tela não pode cair junto", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("qualquer coisa"))));
    const drawer = makeDrawer();

    await expect(drawer.kick("cash_sale")).resolves.toBe(false);
  });

  it("opensOnCashSale respeita o dono que desligou a abertura automática", () => {
    expect(makeDrawer({ ...AGENT, open_on_cash_sale: false }).opensOnCashSale.value).toBe(false);
    expect(makeDrawer().opensOnCashSale.value).toBe(true);
  });

  it("a sonda relata a fila, sem prometer que a gaveta abriu", async () => {
    stubFetch(() => okResponse({ ok: true, queue: "TM-T20" }));
    const drawer = makeDrawer();

    const result = await drawer.probe();
    expect(result.ok).toBe(true);
    expect(result.message).toContain("TM-T20");
  });

  it("a sonda devolve o motivo do CUPS quando a fila não aceita trabalho", async () => {
    stubFetch(() => okResponse({ ok: false, reason: "fila pausada" }));
    const drawer = makeDrawer();

    expect(await drawer.probe()).toEqual({ ok: false, message: "fila pausada" });
  });

  it("testar gaveta num balcão de chave explica em vez de falhar", async () => {
    const drawer = makeDrawer({ adapter: "manual", can_kick: false, open_on_cash_sale: false });
    expect((await drawer.probe()).message).toContain("chave");
  });
});

describe("useCashDrawer — a tela diz por que não dá", () => {
  it("usa o motivo que o servidor mandou", () => {
    const drawer = makeDrawer({
      adapter: "manual", can_kick: false, open_on_cash_sale: false,
      reason: "Este balcão abre a gaveta com a chave — o PDV não tem como abrir.",
    });
    expect(drawer.unavailableReason.value).toContain("chave");
  });

  it("terminal que não mandou motivo ainda assim explica algo útil", () => {
    // Card mudo é pior que card ausente: o operador fica sem próximo passo.
    expect(makeDrawer(null).unavailableReason.value).toContain("Terminais do PDV");
  });
});
