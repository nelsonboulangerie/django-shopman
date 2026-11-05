import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { cashMovementDoneMessage, closeShiftDevicesWarning, formatOpenedAt, shiftOpenedLine } from "../app/presentation/cash";
import { closingSteps } from "../app/presentation/closing";
import type { POSCashRuntimeProjection } from "../app/types/pos";

// Beta test de 05/11/2026, frente do caixa e do Fim do dia.

describe("a hora do turno é a do balcão (PDV2-24, PDV-19)", () => {
  // 11:45 em UTC = 08:45 em Brasília, qualquer que seja o fuso do dispositivo.
  const opened = "2026-11-05T11:45:00+00:00";

  it("'Turno aberto em' sai no fuso da loja", () => {
    expect(formatOpenedAt(opened)).toBe("05/11, 08:45");
  });

  it("o Fim do dia diz quem ABRIU, não quem opera agora", () => {
    expect(shiftOpenedLine({ terminalLabel: "PDV principal", openedAt: opened, openedBy: "admin" }))
      .toBe("PDV principal · turno aberto às 08:45 por admin");
    expect(shiftOpenedLine({ terminalLabel: "PDV principal", openedAt: opened }))
      .toBe("PDV principal · turno aberto às 08:45");
  });
});

describe("fechar o caixa avisa os outros dispositivos da gaveta (PDV-20)", () => {
  const runtime = (devices: number) => ({ station_devices: devices }) as POSCashRuntimeProjection;

  it("diz quantos param de vender", () => {
    expect(closeShiftDevicesWarning(runtime(5)))
      .toBe("Os outros 4 dispositivos desta gaveta param de vender até alguém abrir o caixa de novo.");
    expect(closeShiftDevicesWarning(runtime(2))).toContain("O outro dispositivo");
    expect(closeShiftDevicesWarning(runtime(1))).toBe("");
    expect(closeShiftDevicesWarning(null)).toBe("");
  });

  it("o passo fechado diz 'contado': a conferência é da retaguarda", () => {
    const [cash] = closingSteps({ cashOpen: false, counted: 0, total: 0, step: "count", dayClosed: false });
    expect(cash!.detail).toBe("contado");
  });
});

describe("o relatório de caixa só onde ele abre (PDV-21)", () => {
  const closing = null;
  it("fora de um balcão o card não aparece, nem para quem audita", async () => {
    const { endOfDayTiles } = await import("../app/presentation/cash");
    const keys = (atCounter?: boolean) =>
      endOfDayTiles({ shiftOpen: true, canAuditCash: true, atCounter, dayClosing: closing }).map((t) => t.key);
    expect(keys(true)).toContain("cash_report");
    expect(keys(undefined)).toContain("cash_report");
    expect(keys(false)).not.toContain("cash_report");
  });
});

const source = (...parts: string[]) =>
  readFileSync(fileURLToPath(new URL(`../app/${parts.join("/")}`, import.meta.url)), "utf8");

describe("o movimento aceito diz o valor (op:PDV-11, PDV-10)", () => {
  it("entrada e saída com o valor por extenso", () => {
    // O formatBRL usa espaço inquebrável depois do R$.
    const plain = (text: string) => text.replace(/\s/g, " ");
    expect(plain(cashMovementDoneMessage("suprimento", "50"))).toBe("R$ 50,00 entrou na gaveta.");
    expect(plain(cashMovementDoneMessage("sangria", "5.000,00"))).toBe("R$ 5.000,00 saiu da gaveta.");
  });

  it("o caixa confirma o movimento e o troco atendido antes do aviso do comprovante", () => {
    const cash = source("composables", "usePosCashSession.ts");
    expect(cash).toContain("toast.success(cashMovementDoneMessage(payload.kind, payload.amount));");
    expect(cash).toContain('toast.success("Pedido de troco atendido.");');
  });

  it("gaveta e impressora sem configuração falam com o balcão, sem Admin", () => {
    const agent = source("composables", "useCounterAgent.ts");
    expect(agent).not.toContain("no Admin");
    expect(agent).toContain("Gaveta não configurada neste balcão. Chame o gerente.");
  });
});

describe("Atalhos de venda não perdem a mudança calados (PDV-22)", () => {
  it("sair com mudança não gravada pede confirmação, como o Salão", () => {
    const page = source("pages", "settings", "shortcuts.vue");
    expect(page).toContain("onBeforeRouteLeave(async () => {");
    expect(page).toContain("if (!changed.value) return true;");
    expect(page).toContain('title: "Sair sem gravar os atalhos?"');
  });
});

describe("Pedir troco: o rótulo da moeda não corta (PDV-15)", () => {
  it("a moeda cresce com o rótulo em vez de ter largura fixa", () => {
    const page = source("pages", "session", "index.vue");
    expect(page).toContain("'h-12 min-w-12 justify-center rounded-full px-2'");
    expect(page).not.toContain("'size-12 justify-center rounded-full'");
  });
});
