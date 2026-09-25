import { computed, nextTick, ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useDanfePrint } from "../../app/composables/useDanfePrint";
import { danfeAutoPrintRefs, danfeLine } from "../../app/presentation/danfe";
import type { OrderCardProjection, StationDeviceAgent, TwoZoneQueueProjection } from "../../app/types/orders";

const env = installNuxtGlobals();

const AGENT: StationDeviceAgent = { can_print: true, agent_url: "http://127.0.0.1:9123", token: "t", reason: "" };

function card(ref: string, over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return { ref, danfe_printable: true, danfe_printed: false, danfe_auto_print: false, ...over } as OrderCardProjection;
}

function queueWith(transit: OrderCardProjection[], pickup: OrderCardProjection[] = []): TwoZoneQueueProjection {
  return {
    intake: [],
    preparing_count: 0,
    prep: [],
    expedition_pickup: pickup,
    expedition_delivery: [],
    expedition_delivery_transit: transit,
    expedition_delivery_count: transit.length,
    expedition_count: transit.length + pickup.length,
    total_count: transit.length + pickup.length,
    service_day: "2026-09-25",
    service_day_ends_at: "2026-09-26T00:00:00-03:00",
  } as TwoZoneQueueProjection;
}

async function settle() {
  for (let i = 0; i < 5; i++) {
    await nextTick();
    await Promise.resolve();
  }
}

describe("danfeLine — o que o card diz", () => {
  it("some quando não há nota (ou é iFood)", () => {
    expect(danfeLine(card("A", { danfe_printable: false }))).toBeNull();
  });

  it("depois da primeira, o gesto é reimprimir", () => {
    expect(danfeLine(card("A", { danfe_printed: true }))).toEqual({ status: "DANFE impressa", action: "Reimprimir DANFE" });
  });

  it("a entrega recém-despachada diz que a DANFE está saindo", () => {
    expect(danfeLine(card("A", { danfe_auto_print: true }))?.status).toBe("DANFE saindo para a sacola");
  });

  it("a retirada oferece imprimir, sem prometer que sai sozinha", () => {
    expect(danfeLine(card("A"))).toEqual({ status: "DANFE não impressa", action: "Imprimir DANFE" });
  });
});

describe("danfeAutoPrintRefs — o que sai sem ninguém pedir", () => {
  it("só o que o servidor marcou, e uma vez por aba", () => {
    const queue = queueWith([card("DLV-1", { danfe_auto_print: true }), card("DLV-2")], [card("PCK-1")]);

    expect(danfeAutoPrintRefs(queue, new Set())).toEqual(["DLV-1"]);
    expect(danfeAutoPrintRefs(queue, new Set(["DLV-1"]))).toEqual([]);
    expect(danfeAutoPrintRefs(null, new Set())).toEqual([]);
  });
});

describe("useDanfePrint — a estação imprime a DANFE da sacola", () => {
  const agentFetch = vi.fn();

  beforeEach(() => {
    env.reset();
    agentFetch.mockReset().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true }) });
    vi.stubGlobal("fetch", agentFetch);
  });

  it("nota autorizada DEPOIS do despacho: imprime quando o quadro relê, uma vez só", async () => {
    env.fetchMock.mockResolvedValue({ payload_b64: "QQ==", title: "danfe:DLV-1", reprint: false });
    const queue = ref<TwoZoneQueueProjection | null>(queueWith([card("DLV-1")]));
    const refresh = vi.fn();
    useDanfePrint(computed(() => queue.value), computed(() => AGENT), refresh);
    await settle();
    expect(env.fetchMock).not.toHaveBeenCalled();

    // A autorização chega (SSE → refetch): o servidor marca a automática.
    queue.value = queueWith([card("DLV-1", { danfe_auto_print: true })]);
    await settle();
    // Uma segunda leitura com o mesmo estado não imprime de novo.
    queue.value = queueWith([card("DLV-1", { danfe_auto_print: true })]);
    await settle();

    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/orders/DLV-1/danfe-escpos/",
      { method: "POST", body: { auto: true } },
    );
    expect(agentFetch).toHaveBeenCalledTimes(1);
    expect(String(agentFetch.mock.calls[0][0])).toBe("http://127.0.0.1:9123/print");
    expect(env.sonner.success).toHaveBeenCalledWith("DANFE do pedido DLV-1 impressa — vai na sacola.");
  });

  it("estação sem impressora não tenta a automática nem grita", async () => {
    const queue = computed(() => queueWith([card("DLV-1", { danfe_auto_print: true })]));
    useDanfePrint(queue, computed(() => ({ can_print: false, reason: "Sem agente." })), vi.fn());
    await settle();

    expect(env.fetchMock).not.toHaveBeenCalled();
    expect(env.sonner.error).not.toHaveBeenCalled();
  });

  it("a outra estação já imprimiu (409): a automática se cala", async () => {
    env.fetchMock.mockRejectedValue(Object.assign(new Error("conflict"), { statusCode: 409, status: 409 }));
    const queue = computed(() => queueWith([card("DLV-1", { danfe_auto_print: true })]));
    useDanfePrint(queue, computed(() => AGENT), vi.fn());
    await settle();

    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    expect(agentFetch).not.toHaveBeenCalled();
    expect(env.sonner.error).not.toHaveBeenCalled();
  });

  it("o papel que não saiu avisa e manda reimprimir pelo card", async () => {
    env.fetchMock.mockResolvedValue({ payload_b64: "QQ==", title: "danfe:DLV-1", reprint: false });
    agentFetch.mockRejectedValue(new TypeError("Failed to fetch"));
    const queue = computed(() => queueWith([card("DLV-1", { danfe_auto_print: true })]));
    useDanfePrint(queue, computed(() => AGENT), vi.fn());
    await settle();

    expect(env.sonner.error).toHaveBeenCalledWith(
      "A DANFE do pedido DLV-1 não saiu: O agente local desta estação não está rodando. Reimprima pelo card.",
    );
  });

  it("reimprimir à mão manda auto=false e diz que foi reimpressa", async () => {
    env.fetchMock.mockResolvedValue({ payload_b64: "QQ==", title: "danfe:PCK-1", reprint: true });
    const danfe = useDanfePrint(computed(() => queueWith([], [card("PCK-1", { danfe_printed: true })])), computed(() => AGENT), vi.fn());

    expect(await danfe.printDanfe("PCK-1")).toBe(true);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/orders/PCK-1/danfe-escpos/",
      { method: "POST", body: { auto: false } },
    );
    expect(env.sonner.success).toHaveBeenCalledWith("DANFE do pedido PCK-1 reimpressa.");
  });

  it("à mão, sem impressora nesta estação, diz o porquê", async () => {
    const danfe = useDanfePrint(computed(() => null), computed(() => ({ can_print: false, reason: "Sem agente aqui." })), vi.fn());

    expect(await danfe.printDanfe("PCK-1")).toBe(false);
    expect(env.sonner.error).toHaveBeenCalledWith("A DANFE não sai nesta estação: Sem agente aqui.");
  });
});
