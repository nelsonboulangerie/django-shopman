import { describe, expect, it } from "vitest";

import { stationDevicesNotice } from "../app/presentation/cash";
import { cashReportStationRefusal } from "../app/presentation/cashReport";
import type { POSCashRuntimeProjection } from "../app/types/pos";

function runtime(extra: Partial<POSCashRuntimeProjection>): POSCashRuntimeProjection {
  return {
    has_open_shift: false,
    shift_id: null,
    terminal_ref: "pdv-main",
    terminal_label: "PDV",
    operator_username: "joyce",
    opened_at: "",
    ...extra,
  } as POSCashRuntimeProjection;
}

describe("stationDevicesNotice: vários dispositivos no mesmo balcão (D-007)", () => {
  it("com um dispositivo só não há o que dizer", () => {
    expect(stationDevicesNotice(runtime({ station_devices: 1 }))).toBe("");
    expect(stationDevicesNotice(runtime({}))).toBe("");
    expect(stationDevicesNotice(null)).toBe("");
  });

  it("diz quantos dispositivos dividem a gaveta", () => {
    expect(stationDevicesNotice(runtime({ station_devices: 2 }))).toBe(
      "Há 2 dispositivos neste balcão, na mesma gaveta.",
    );
  });

  it("com o caixa já aberto, diz que a venda entra no mesmo turno", () => {
    expect(stationDevicesNotice(runtime({ station_devices: 3, has_open_shift: true }))).toBe(
      "Há 3 dispositivos neste balcão, na mesma gaveta. Caixa já aberto: o que for vendido aqui entra no mesmo turno.",
    );
  });
});

describe("cashReportStationRefusal: o 409 da estação no relatório X/Z", () => {
  it("balcão errado tem mensagem própria, não erro genérico", () => {
    const refusal = cashReportStationRefusal(409, "pos_terminal_mismatch");
    expect(refusal?.title).toBe("Este relatório é de outro balcão");
    expect(refusal?.message).toContain("balcão onde você está");
  });

  it("dispositivo que não é balcão também é nomeado", () => {
    expect(cashReportStationRefusal(409, "pos_station_required")?.title).toBe("Este dispositivo não é um balcão");
  });

  it("outros erros seguem o caminho de antes", () => {
    expect(cashReportStationRefusal(409, "outra_coisa")).toBeNull();
    expect(cashReportStationRefusal(403, "pos_terminal_mismatch")).toBeNull();
    expect(cashReportStationRefusal(undefined, "")).toBeNull();
  });
});
