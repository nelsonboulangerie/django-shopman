// A loja no iFood, ao vivo (homologação do módulo Merchant, DEV-2026-044): as
// frases que dizem o que o iFood respondeu e o que fazer com cada pausa.
import { describe, expect, it } from "vitest";
import {
  availabilityLine,
  checkColor,
  hoursLine,
  operationColor,
  pauseHint,
  pausePeriod,
} from "../app/presentation/ifoodMerchant";
import type {
  IFoodInterruptionRow,
  IFoodMerchantDetail,
  IFoodOpeningHours,
} from "../app/types/ifoodMerchant";

const detail = (over: Partial<IFoodMerchantDetail> = {}): IFoodMerchantDetail => ({
  enabled: true,
  merchant_id: "m",
  detail: [],
  detail_error: "",
  available: true,
  operations: [],
  status_error: "",
  checked_at_display: "21/11 11h",
  ...over,
});

const pause = (over: Partial<IFoodInterruptionRow> = {}): IFoodInterruptionRow => ({
  id: "p",
  description: "",
  starts_at_display: "21/11 11h",
  ends_at_display: "21/11 11h30",
  origin: "portal",
  origin_label: "Portal do Parceiro",
  in_effect: true,
  removable: true,
  ...over,
});

const week = (over: Partial<IFoodOpeningHours> = {}): IFoodOpeningHours => ({
  enabled: true,
  days: [],
  matches: true,
  governs: true,
  error: "",
  checked_at_display: "11h",
  ...over,
});

describe("disponibilidade", () => {
  it("diz se o iFood está recebendo pedido agora", () => {
    expect(availabilityLine(detail())).toBe("O iFood está recebendo pedidos desta loja.");
    expect(availabilityLine(detail({ available: false }))).toContain("NÃO está recebendo");
  });
  it("com o status recusado, a frase é a do erro, não esta", () => {
    expect(availabilityLine(detail({ status_error: "403" }))).toBe("");
  });
  it("cor só chama atenção no que não está OK", () => {
    expect(operationColor("OK")).toBe("success");
    expect(operationColor("WARNING")).toBe("warning");
    expect(operationColor("ERROR")).toBe("error");
    expect(checkColor("OK")).toBe("success");
    expect(checkColor("CLOSED")).toBe("neutral");
  });
});

describe("pausas", () => {
  it("o período tem início e fim", () => {
    expect(pausePeriod(pause())).toBe("21/11 11h até 21/11 11h30");
  });
  it("a pausa do Gestor sai ligando o iFood de novo; a do Portal tem botão", () => {
    expect(pauseHint(pause())).toBe("");
    expect(pauseHint(pause({ origin: "switch", removable: false }))).toContain("ligue o iFood de novo");
    expect(pauseHint(pause({ origin: "calendar", removable: false }))).toContain("calendário");
  });
});

describe("horário", () => {
  it("iguais, diferentes ou sem grade", () => {
    expect(hoursLine(week())).toBe("O horário no iFood é igual ao da casa.");
    expect(hoursLine(week({ matches: false }))).toContain("diferente");
    expect(hoursLine(week({ governs: false }))).toContain("Portal do Parceiro");
  });
});
