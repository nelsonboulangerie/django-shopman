// A corrida que ninguém aceitou ou que foi cancelada (#2737): o cartão some quando
// o pedido já está numa corrida em edição ou foi dispensado, e "Chamar de novo"
// devolve a corrida INTEIRA com a mesma letra quando ela segue livre.
import { describe, expect, it } from "vitest";

import { rideFromFailed, visibleFailedRides, type FailedRide } from "~/presentation/deliveries";

const failed = (over: Partial<FailedRide> = {}): FailedRide => ({
  key: "R-77",
  message: "Ninguém aceitou a corrida B (14h20).",
  refs: ["WEB-A47", "WEB-C03"],
  codes: ["A47", "C03"],
  places: "Centro",
  number: 2,
  ...over,
});

describe("visibleFailedRides", () => {
  it("mostra a corrida que falhou", () => {
    expect(visibleFailedRides([failed()], [], [])).toHaveLength(1);
  });
  it("esconde a dispensada", () => {
    expect(visibleFailedRides([failed()], [], ["R-77"])).toEqual([]);
  });
  it("esconde a que tem pedido já em edição", () => {
    expect(visibleFailedRides([failed()], [{ number: 1, refs: ["WEB-C03"] }], [])).toEqual([]);
  });
});

describe("rideFromFailed", () => {
  it("volta inteira, com a mesma letra quando ela está livre", () => {
    expect(rideFromFailed(failed(), [1, 2, 3], [])).toEqual({ number: 2, refs: ["WEB-A47", "WEB-C03"] });
  });
  it("pega a próxima livre quando a letra dela está em edição", () => {
    expect(rideFromFailed(failed(), [1, 2, 3], [{ number: 2, refs: ["X"] }])).toEqual({ number: 1, refs: ["WEB-A47", "WEB-C03"] });
  });
  it("pega a próxima livre quando outra corrida já usa a letra", () => {
    expect(rideFromFailed(failed({ number: null }), [3, 4], [])?.number).toBe(3);
  });
  it("sem letra livre, não monta nada", () => {
    expect(rideFromFailed(failed(), [], [])).toBeNull();
  });
});
