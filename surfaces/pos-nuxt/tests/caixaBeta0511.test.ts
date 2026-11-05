import { describe, expect, it } from "vitest";

import { closeShiftDevicesWarning, formatOpenedAt, shiftOpenedLine } from "../app/presentation/cash";
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
