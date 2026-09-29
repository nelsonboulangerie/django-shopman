import { computed } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useDanfePrint } from "../../app/composables/useDanfePrint";
import { danfeLine } from "../../app/presentation/danfe";
import type { OrderCardProjection, StationDeviceAgent } from "../../app/types/orders";

const env = installNuxtGlobals();

const AGENT: StationDeviceAgent = { can_print: true, agent_url: "http://127.0.0.1:9123", token: "t", reason: "" };
const NO_AGENT: StationDeviceAgent = { can_print: false, reason: "Sem agente." };

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "DLV-1",
    danfe_printable: true,
    danfe_printed: false,
    danfe_state: "",
    danfe_problem: "",
    ...over,
  } as OrderCardProjection;
}

describe("danfeLine: o que o card diz", () => {
  it("some quando não há nota (ou é iFood)", () => {
    expect(danfeLine(card({ danfe_printable: false }))).toBeNull();
  });

  it("impressa: o gesto é reimprimir", () => {
    expect(danfeLine(card({ danfe_printed: true, danfe_state: "printed" }))).toMatchObject({
      status: "DANFE impressa",
      action: "Reimprimir DANFE",
      attention: false,
    });
  });

  it("na fila da impressora: está saindo, e o botão espera", () => {
    expect(danfeLine(card({ danfe_state: "sending" }))).toMatchObject({
      status: "DANFE saindo na impressora",
      sending: true,
    });
  });

  it("não saiu: pede atenção e traz o motivo do servidor", () => {
    expect(danfeLine(card({ danfe_state: "not_printed", danfe_problem: "A impressora não respondeu." }))).toMatchObject({
      status: "DANFE não impressa",
      problem: "A impressora não respondeu.",
      action: "Imprimir DANFE",
      attention: true,
    });
  });

  it("entrega ainda na casa: diz que sai sozinha na saída", () => {
    expect(danfeLine(card({ danfe_state: "on_dispatch" }))?.status).toBe("A DANFE sai sozinha quando a entrega sair");
  });

  it("retirada: fica à mão, sem prometer que sai sozinha", () => {
    expect(danfeLine(card({ danfe_state: "available" }))).toMatchObject({ status: "DANFE disponível", action: "Imprimir DANFE" });
  });

  it("nenhuma frase usa travessão", () => {
    for (const state of ["printed", "sending", "not_printed", "on_dispatch", "available"]) {
      expect(JSON.stringify(danfeLine(card({ danfe_state: state })))).not.toContain("—");
    }
  });
});

describe("useDanfePrint: o botão do card", () => {
  const agentFetch = vi.fn();

  beforeEach(() => {
    env.reset();
    agentFetch.mockReset().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true }) });
    vi.stubGlobal("fetch", agentFetch);
  });

  it("pede ao servidor, que manda para a impressora do despacho", async () => {
    env.fetchMock.mockResolvedValue({ via: "relay", reprint: false, target_label: "Balcão" });
    const refresh = vi.fn();
    const danfe = useDanfePrint(computed(() => NO_AGENT), refresh);

    expect(await danfe.printDanfe("DLV-1")).toBe(true);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/orders/DLV-1/danfe-escpos/",
      { method: "POST", body: { local_agent: false } },
    );
    expect(agentFetch).not.toHaveBeenCalled();
    expect(env.sonner.success).toHaveBeenCalledWith("DANFE do pedido DLV-1 enviada para a impressora de Balcão.");
    expect(refresh).toHaveBeenCalled();
  });

  it("reimpressão diz que é reimpressão", async () => {
    env.fetchMock.mockResolvedValue({ via: "relay", reprint: true, target_label: "Balcão" });
    const danfe = useDanfePrint(computed(() => AGENT), vi.fn());

    await danfe.printDanfe("DLV-1");

    expect(env.sonner.success).toHaveBeenCalledWith(
      "Reimpressão da DANFE do pedido DLV-1 enviada para a impressora de Balcão.",
    );
  });

  it("sem impressora de despacho, relaia ao agente local desta estação", async () => {
    env.fetchMock.mockResolvedValue({ via: "local", reprint: false, payload_b64: "QQ==", title: "danfe:PCK-1" });
    const danfe = useDanfePrint(computed(() => AGENT), vi.fn());

    expect(await danfe.printDanfe("PCK-1")).toBe(true);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/orders/PCK-1/danfe-escpos/",
      { method: "POST", body: { local_agent: true } },
    );
    expect(String(agentFetch.mock.calls[0][0])).toBe("http://127.0.0.1:9123/print");
    expect(env.sonner.success).toHaveBeenCalledWith("DANFE do pedido PCK-1 impressa.");
  });

  it("o agente local que falha diz por quê", async () => {
    env.fetchMock.mockResolvedValue({ via: "local", reprint: false, payload_b64: "QQ==", title: "danfe:PCK-1" });
    agentFetch.mockRejectedValue(new TypeError("Failed to fetch"));
    const danfe = useDanfePrint(computed(() => AGENT), vi.fn());

    expect(await danfe.printDanfe("PCK-1")).toBe(false);
    expect(env.sonner.error).toHaveBeenCalledWith(
      "A DANFE do pedido PCK-1 não saiu: O agente local desta estação não está rodando.",
    );
  });

  it("a recusa do servidor chega com a frase dele", async () => {
    env.fetchMock.mockRejectedValue(
      Object.assign(new Error("conflict"), {
        statusCode: 409,
        status: 409,
        data: { detail: "A DANFE não tem para onde sair. Nenhuma impressora recebe a DANFE pelo servidor." },
      }),
    );
    const danfe = useDanfePrint(computed(() => NO_AGENT), vi.fn());

    expect(await danfe.printDanfe("DLV-1")).toBe(false);
    expect(env.sonner.error).toHaveBeenCalledWith(
      "A DANFE não tem para onde sair. Nenhuma impressora recebe a DANFE pelo servidor.",
    );
  });
});
