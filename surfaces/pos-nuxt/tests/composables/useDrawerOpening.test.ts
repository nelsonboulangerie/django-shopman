import { afterEach, describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";

import { useCounterAgent } from "~/composables/useCounterAgent";
import { useDrawerOpening } from "~/composables/useDrawerOpening";
import type { Action, POSProjection } from "~/types/pos";

import { makeProjection } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const AGENT_DRAWER = {
  adapter: "agent",
  can_kick: true,
  open_on_cash_sale: true,
  agent_url: "http://127.0.0.1:47811",
  token: "token-do-balcao",
  pulse: { pin: 0, on_ms: 50, off_ms: 500 },
} satisfies POSProjection["cash_drawer"];

const RELAY = { available: true, online: true, terminal_label: "Balcão", reason: "" };

/** O tablet: o agente do Balcão não responde nesta máquina. */
function tabletNetwork() {
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
}

/** O PC do Balcão: o agente responde na loopback, e cada chute fica anotado. */
function counterNetwork(kicks: string[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      if (String(url).endsWith("/kick")) kicks.push(JSON.parse(String(init?.body)).reason);
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ok: true, queue: "balcao" }) });
    }),
  );
}

function make(opts: { projection?: Partial<POSProjection>; actionCall: ReturnType<typeof vi.fn> }) {
  const posValue = ref<POSProjection | null>(makeProjection({ cash_drawer: AGENT_DRAWER, ...opts.projection }));
  const pos = computed(() => posValue.value);
  const actions = computed<Action[]>(() => []);
  const drawer = useCounterAgent(pos);
  return useDrawerOpening({ pos, actions, action: { call: opts.actionCall }, drawer });
}

describe("useDrawerOpening — a gaveta aberta pelo tablet, com autoria", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("no tablet, a venda em dinheiro NÃO abre a gaveta: vira o cartão para o Balcão", async () => {
    tabletNetwork();
    const actionCall = vi.fn();
    const opening = make({ projection: { drawer_relay: RELAY }, actionCall });

    await opening.afterCashSale({ orderRef: "1012", tabDisplay: "6", changeQ: 4500 }, true);

    expect(actionCall).not.toHaveBeenCalled();
    expect(opening.pendingCash.value).toEqual([{ orderRef: "1012", tabDisplay: "6", changeQ: 4500 }]);
  });

  it("no Balcão, a venda em dinheiro chuta e registra a abertura por venda", async () => {
    const kicks: string[] = [];
    counterNetwork(kicks);
    const actionCall = vi.fn().mockResolvedValue({ ok: true });
    const opening = make({ projection: { drawer_relay: RELAY }, actionCall });

    await opening.afterCashSale({ orderRef: "1012", tabDisplay: "", changeQ: 0 }, true);
    await Promise.resolve();

    expect(kicks).toEqual(["cash_sale"]);
    expect(actionCall).toHaveBeenCalledWith("/api/v1/backstage/pos/cash/drawer-open/", {
      body: { purpose: "sale", order_ref: "1012", via: "local" },
    });
    expect(opening.pendingCash.value).toEqual([]);
  });

  it("o tablet pede pelo relay, acompanha o pulso e o cartão some quando abriu", async () => {
    vi.useFakeTimers();
    tabletNetwork();
    const actionCall = vi.fn((path: string) => {
      if (path.includes("drawer-pulse")) {
        return Promise.resolve({ pulse: { state: "sent", message: "Gaveta do Balcão aberta." } });
      }
      return Promise.resolve({ ok: true, entry_id: 7, pulse: { ref: "abc", state: "sending", message: "" } });
    });
    const opening = make({ projection: { drawer_relay: RELAY }, actionCall });
    await opening.afterCashSale({ orderRef: "1012", tabDisplay: "6", changeQ: 4500 }, true);

    const done = opening.open({ purpose: "sale", orderRef: "1012" });
    await vi.advanceTimersByTimeAsync(1500);
    expect(await done).toBe(true);

    expect(actionCall).toHaveBeenNthCalledWith(1, "/api/v1/backstage/pos/cash/drawer-open/", {
      body: { purpose: "sale", order_ref: "1012", via: "relay" },
    });
    expect(opening.state.value).toBe("sent");
    expect(opening.pendingCash.value).toEqual([]);
  });

  it("o Balcão que não responde: a tela diz que NÃO abriu e o cartão fica", async () => {
    vi.useFakeTimers();
    tabletNetwork();
    const actionCall = vi.fn((path: string) => {
      if (path.includes("drawer-pulse")) {
        return Promise.resolve({
          pulse: { state: "expired", message: "O Balcão não respondeu: a gaveta não abriu." },
        });
      }
      return Promise.resolve({ ok: true, pulse: { ref: "abc", state: "sending", message: "" } });
    });
    const opening = make({ projection: { drawer_relay: RELAY }, actionCall });
    await opening.afterCashSale({ orderRef: "1012", tabDisplay: "6", changeQ: 0 }, true);

    const done = opening.open({ purpose: "sale", orderRef: "1012" });
    await vi.advanceTimersByTimeAsync(1500);
    expect(await done).toBe(false);

    expect(opening.state.value).toBe("expired");
    expect(opening.message.value).toMatch(/não abriu/);
    expect(opening.pendingCash.value).toHaveLength(1);
  });

  it("sem rede, nem chega ao servidor e diz isso", async () => {
    tabletNetwork();
    const actionCall = vi.fn().mockRejectedValue({ status: 0 });
    const opening = make({ projection: { drawer_relay: RELAY }, actionCall });

    expect(await opening.open({ purpose: "no_sale", reason: "Troco" })).toBe(false);
    expect(opening.state.value).toBe("offline");
    expect(opening.message.value).toMatch(/não abriu/);
  });

  it("sem relay pareado, a recusa do servidor chega à tela", async () => {
    tabletNetwork();
    const actionCall = vi.fn();
    const opening = make({
      projection: {
        drawer_relay: { available: false, online: false, terminal_label: "Balcão", reason: "Sem credencial do relay." },
      },
      actionCall,
    });

    expect(await opening.open({ purpose: "no_sale", reason: "Troco" })).toBe(false);
    expect(actionCall).not.toHaveBeenCalled();
    expect(opening.message.value).toBe("Sem credencial do relay.");
  });
});
