import { describe, expect, it } from "vitest";

import { stationTerminalHint } from "../app/presentation/stationOccupancy";

describe("stationTerminalHint", () => {
  it("balcão livre mostra só o ref", () => {
    expect(stationTerminalHint({ ref: "pdv-main", label: "PDV", active_devices: 0, has_open_shift: false })).toBe(
      "pdv-main",
    );
  });

  it("diz quantos dispositivos já usam o balcão e se o caixa está aberto", () => {
    expect(stationTerminalHint({ ref: "pdv-main", label: "PDV", active_devices: 1, has_open_shift: true })).toBe(
      "pdv-main · 1 dispositivo já usa este balcão · caixa aberto",
    );
    expect(stationTerminalHint({ ref: "pdv-main", label: "PDV", active_devices: 3 })).toBe(
      "pdv-main · 3 dispositivos já usam este balcão",
    );
  });

  it("resposta antiga sem ocupação não inventa nada", () => {
    expect(stationTerminalHint({ ref: "pdv-main", label: "PDV" })).toBe("pdv-main");
  });
});
