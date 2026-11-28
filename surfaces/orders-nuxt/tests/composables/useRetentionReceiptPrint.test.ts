// O recibo do valor retido no Gestor (#3538): sai sozinho no fim do "Não retirado",
// pela impressora desta estação, e o menu do pedido reimprime. Sem impressora, o gesto
// continua à vista e diz por quê, e lembra que o cliente tem o recibo no link.
import { computed } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useRetentionReceiptPrint } from "../../app/composables/useRetentionReceiptPrint";
import {
  retentionReceiptMenuItem,
  retentionReceiptPrintedMessage,
} from "../../app/presentation/retentionReceipt";
import type { StationDeviceAgent } from "../../app/types/orders";

const env = installNuxtGlobals();

const AGENT: StationDeviceAgent = { can_print: true, agent_url: "http://127.0.0.1:9123", token: "t", reason: "" };
const NO_AGENT: StationDeviceAgent = {
  can_print: false,
  reason: "Este dispositivo não tem impressora configurada.",
};
const NO_PRINTER_TITLE =
  "Este dispositivo não tem impressora configurada. O recibo sai no dispositivo que tem impressora, "
  + "e o cliente também o vê no link do pedido.";

describe("retentionReceiptMenuItem: o item do ⋯", () => {
  it("com impressora: imprimir, e reimprimir depois da primeira", () => {
    expect(retentionReceiptMenuItem(AGENT)).toEqual({
      label: "Imprimir recibo do valor retido",
      icon: "i-lucide-receipt",
      disabled: false,
    });
    expect(retentionReceiptMenuItem(AGENT, { printed: true }).label).toBe("Reimprimir recibo do valor retido");
  });

  it("sem impressora: à vista, apagado e dizendo por quê", () => {
    expect(retentionReceiptMenuItem(NO_AGENT)).toMatchObject({
      disabled: true,
      description: "Este dispositivo não tem impressora.",
      title: NO_PRINTER_TITLE,
    });
  });

  it("imprimindo: espera, para não sair dois", () => {
    expect(retentionReceiptMenuItem(AGENT, { printing: true })).toMatchObject({
      label: "Imprimindo o recibo do valor retido…",
      disabled: true,
    });
  });

  it("nenhuma frase usa travessão", () => {
    const text = JSON.stringify([
      retentionReceiptMenuItem(AGENT),
      retentionReceiptMenuItem(NO_AGENT),
      retentionReceiptPrintedMessage("X", true),
    ]);
    expect(text).not.toContain("—");
  });
});

describe("useRetentionReceiptPrint: a impressão", () => {
  const agentFetch = vi.fn();

  beforeEach(() => {
    env.reset();
    agentFetch.mockReset().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true }) });
    vi.stubGlobal("fetch", agentFetch);
  });

  it("pede o papel à rota do recibo e manda ao agente desta estação", async () => {
    env.fetchMock.mockResolvedValue({ payload_b64: "QQ==", title: "recibo-retido:WEB-6", reprint: false });
    const printer = useRetentionReceiptPrint(computed(() => AGENT));

    expect(await printer.print("WEB-6")).toBe(true);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/orders/WEB-6/retention-receipt-escpos/",
      { method: "POST" },
    );
    expect(JSON.parse(agentFetch.mock.calls[0][1].body)).toMatchObject({ payload_b64: "QQ==", title: "recibo-retido:WEB-6" });
    expect(env.sonner.success).toHaveBeenCalledWith("Recibo do valor retido do pedido WEB-6 impresso.");
  });

  it("a segunda sai marcada como 2ª via, como o servidor decidiu", async () => {
    env.fetchMock.mockResolvedValue({ payload_b64: "QQ==", title: "recibo-retido:WEB-6", reprint: true });
    const printer = useRetentionReceiptPrint(computed(() => AGENT));

    await printer.print("WEB-6");

    expect(env.sonner.success).toHaveBeenCalledWith(
      "Recibo do valor retido do pedido WEB-6 impresso, marcado como 2ª via.",
    );
  });

  it("sem impressora não pede papel nenhum (nem carimba) e diz por quê", async () => {
    const printer = useRetentionReceiptPrint(computed(() => NO_AGENT));

    expect(await printer.print("WEB-6")).toBe(false);
    expect(env.fetchMock).not.toHaveBeenCalled();
    expect(env.sonner.error).toHaveBeenCalledWith(
      `O recibo do valor retido do pedido WEB-6 não saiu. ${NO_PRINTER_TITLE}`,
    );
  });
});
