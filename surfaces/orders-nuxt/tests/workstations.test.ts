import { describe, expect, it } from "vitest";

import {
  creatableKinds,
  deviceName,
  deviceUsageLine,
  devicesSummary,
  editableKinds,
} from "../app/presentation/workstations";

const copy = {
  manage_device_never_used: "Ainda não usado",
  manage_device_last_used: "Usado por último em {when}",
  manage_devices_none: "Nenhum dispositivo fixado neste posto.",
  devices_one: "1 dispositivo",
  devices_many: "{n} dispositivos",
};

const kinds = [
  { kind: "cash_desk" as const, label: "Caixa" },
  { kind: "dispatch" as const, label: "Expedição" },
  { kind: "office" as const, label: "Escritório" },
];

function row(over: Record<string, unknown> = {}) {
  return {
    ref: "expedicao",
    label: "Expedição",
    kind: "dispatch" as const,
    kind_label: "Expedição",
    has_cash_desk: false,
    context_label: "Posto Expedição",
    is_active: true,
    devices: [],
    ...over,
  };
}

const device = { id: "1", label: "Chrome no Android", ip_address: "10.0.0.5", created_at: null, last_used_at: null };

describe("cadastro de Postos: apresentação", () => {
  it("o uso do dispositivo diz quando, no fuso da loja", () => {
    expect(deviceUsageLine(device, copy)).toBe("Ainda não usado");
    expect(deviceUsageLine({ ...device, last_used_at: "2026-10-03T17:20:00Z" }, copy)).toBe(
      "Usado por último em 03/10, 14:20",
    );
  });

  it("o nome junta o rótulo e o IP", () => {
    expect(deviceName(device)).toBe("Chrome no Android · 10.0.0.5");
    expect(deviceName({ ...device, ip_address: "" })).toBe("Chrome no Android");
  });

  it("o resumo conta os dispositivos", () => {
    expect(devicesSummary(row(), copy)).toBe("Nenhum dispositivo fixado neste posto.");
    expect(devicesSummary(row({ devices: [device] }), copy)).toBe("1 dispositivo");
    expect(devicesSummary(row({ devices: [device, { ...device, id: "2" }] }), copy)).toBe("2 dispositivos");
  });

  it("o Caixa não se cria aqui, e só o posto com caixa pode ser Caixa", () => {
    expect(creatableKinds(kinds).map((k) => k.kind)).toEqual(["dispatch", "office"]);
    expect(editableKinds(kinds, row()).map((k) => k.kind)).toEqual(["dispatch", "office"]);
    expect(editableKinds(kinds, row({ has_cash_desk: true })).map((k) => k.kind)).toEqual([
      "cash_desk",
      "dispatch",
      "office",
    ]);
  });
});
