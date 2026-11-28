// A Via Pedido no Gestor (P2-19 do mapa de cenários): o mesmo papel e a mesma rota do
// PDV, pela impressora desta estação. Sem impressora, o gesto continua à vista e diz
// por quê.
import { computed } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { createOrderTicketPrinter } from "../../app/composables/useOrderTicketPrint";
import { orderTicketMenuItem, orderTicketPrintedMessage } from "../../app/presentation/orderTicket";
import type { StationDeviceAgent } from "../../app/types/orders";

const env = installNuxtGlobals();

const AGENT: StationDeviceAgent = { can_print: true, agent_url: "http://127.0.0.1:9123", token: "t", reason: "" };
const NO_AGENT: StationDeviceAgent = {
  can_print: false,
  reason: "Este dispositivo não tem impressora configurada.",
};

describe("orderTicketMenuItem: o item do ⋯", () => {
  it("com impressora: o gesto inteiro, pronto", () => {
    expect(orderTicketMenuItem(AGENT)).toEqual({
      label: "Imprimir Via Pedido",
      icon: "i-lucide-printer",
      disabled: false,
    });
  });

  it("sem impressora: à vista, apagado e dizendo por quê e onde sai", () => {
    expect(orderTicketMenuItem(NO_AGENT)).toMatchObject({
      label: "Imprimir Via Pedido",
      disabled: true,
      description: "Este dispositivo não tem impressora.",
      title:
        "Este dispositivo não tem impressora configurada. A Via Pedido sai no dispositivo que tem impressora.",
    });
  });

  it("imprimindo: espera, para não sair duas", () => {
    expect(orderTicketMenuItem(AGENT, { printing: true })).toMatchObject({
      label: "Imprimindo a Via Pedido…",
      disabled: true,
    });
  });

  it("o resultado diz quando saiu como 2ª via", () => {
    expect(orderTicketPrintedMessage("WEB-6", false)).toBe("Via Pedido do pedido WEB-6 impressa.");
    expect(orderTicketPrintedMessage("WEB-6", true)).toBe(
      "Via Pedido do pedido WEB-6 impressa, marcada como 2ª via.",
    );
  });

  it("nenhuma frase usa travessão", () => {
    const text = JSON.stringify([
      orderTicketMenuItem(AGENT),
      orderTicketMenuItem(NO_AGENT),
      orderTicketMenuItem(AGENT, { printing: true }),
      orderTicketPrintedMessage("X", true),
    ]);
    expect(text).not.toContain("—");
  });
});

describe("createOrderTicketPrinter: a impressão", () => {
  const agentFetch = vi.fn();

  beforeEach(() => {
    env.reset();
    agentFetch.mockReset().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true }) });
    vi.stubGlobal("fetch", agentFetch);
  });

  it("pede o papel à rota do PDV e manda ao agente desta estação", async () => {
    env.fetchMock.mockResolvedValue({ payload_b64: "QQ==", title: "filipeta:WEB-6", reprint: false });
    const printer = createOrderTicketPrinter(computed(() => AGENT));

    expect(await printer.print("WEB-6")).toBe(true);
    expect(env.fetchMock).toHaveBeenCalledWith("/api/v1/backstage/orders/WEB-6/ticket-escpos/", { method: "POST" });
    expect(String(agentFetch.mock.calls[0][0])).toBe("http://127.0.0.1:9123/print");
    expect(JSON.parse(agentFetch.mock.calls[0][1].body)).toMatchObject({
      payload_b64: "QQ==",
      title: "filipeta:WEB-6",
    });
    expect(env.sonner.success).toHaveBeenCalledWith("Via Pedido do pedido WEB-6 impressa.");
  });

  it("a segunda sai marcada como 2ª via, como o servidor decidiu", async () => {
    env.fetchMock.mockResolvedValue({ payload_b64: "QQ==", title: "filipeta:WEB-6", reprint: true });
    const printer = createOrderTicketPrinter(computed(() => AGENT));

    await printer.print("WEB-6");

    expect(env.sonner.success).toHaveBeenCalledWith(
      "Via Pedido do pedido WEB-6 impressa, marcada como 2ª via.",
    );
  });

  it("sem impressora não pede papel nenhum (nem carimba) e diz por quê", async () => {
    const printer = createOrderTicketPrinter(computed(() => NO_AGENT));

    expect(await printer.print("WEB-6")).toBe(false);
    expect(env.fetchMock).not.toHaveBeenCalled();
    expect(env.sonner.error).toHaveBeenCalledWith(
      "A Via Pedido do pedido WEB-6 não saiu. Este dispositivo não tem impressora configurada. "
        + "A Via Pedido sai no dispositivo que tem impressora.",
    );
  });

  it("o agente que falha diz por quê", async () => {
    env.fetchMock.mockResolvedValue({ payload_b64: "QQ==", title: "filipeta:WEB-6", reprint: false });
    agentFetch.mockRejectedValue(new TypeError("Failed to fetch"));
    const printer = createOrderTicketPrinter(computed(() => AGENT));

    expect(await printer.print("WEB-6")).toBe(false);
    expect(env.sonner.error).toHaveBeenCalledWith(
      "A Via Pedido do pedido WEB-6 não saiu: O agente local desta estação não está rodando.",
    );
  });
});
