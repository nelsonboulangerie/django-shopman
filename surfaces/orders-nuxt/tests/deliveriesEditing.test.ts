// A coluna Editando honesta (F4b): ordem do percurso, cotação em duas linhas, uma
// maquininha por corrida, troco conferido e o balanço de cada chamada.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import type { DeliveryStopProjection } from "~/generated/ordersContract";
import {
  assignMachines,
  callSummary,
  changeValue,
  failureStops,
  machineShortfall,
  quoteLines,
  rideCalls,
  rideFailureTitle,
  ridesNeedingMachine,
  routeOrder,
  type EditingQuote,
  type RoutePoint,
} from "~/presentation/deliveries";

function stop(ref: string, extra: Partial<DeliveryStopProjection> = {}): DeliveryStopProjection {
  return {
    ref, code: ref.slice(-3), customer: "Ana", place: "Centro", address: "", latitude: 0, longitude: 0,
    stage: "Pronto", volumes: 1, done: false, change_out_suggested_q: 0, needs_machine: false,
    change_label: "", group_refusal: "", error: "", dispatch_action: null, dispatch_again_action: null,
    charge_outdated: null, ...extra,
  };
}

const quote = (extra: Partial<EditingQuote> = {}): EditingQuote => ({
  value_q: 1000, display: "R$ 10,00 · 10 min · 5 km", stops: ["A", "B"], ...extra,
});

describe("ordem do percurso", () => {
  interface Case {
    name: string;
    origin: { latitude: number; longitude: number } | null;
    stops: RoutePoint[];
    expected: string[];
  }
  const fixture = JSON.parse(
    readFileSync(new URL("./fixtures/route-order.json", import.meta.url), "utf8"),
  ) as { cases: Case[] };

  it.each(fixture.cases.map((item) => [item.name, item] as const))("%s (a mesma fixture do pytest)", (_, item) => {
    expect(routeOrder(item.origin, item.stops).map((point) => point.ref)).toEqual(item.expected);
  });

  it("não mexe na lista que recebeu", () => {
    const stops = fixture.cases[0]!.stops;
    const before = stops.map((point) => point.ref);
    routeOrder(fixture.cases[0]!.origin, stops);
    expect(stops.map((point) => point.ref)).toEqual(before);
  });
});

describe("cotação em duas linhas, com o ✔ na mais barata", () => {
  it("juntas mais barato: a linha de juntas leva o ✔ e o destaque", () => {
    expect(quoteLines(quote({ separate_value_q: 1500, saving_q: 500 }), 2)).toEqual([
      { text: "Juntas: R$ 10,00 · 10 min · 5 km ✔", strong: true },
      { text: "Separadas sairiam R$ 15,00", strong: false },
    ]);
  });

  it("separadas mais barato: o ✔ e o destaque passam para separadas", () => {
    expect(quoteLines(quote({ separate_value_q: 700, saving_q: -300 }), 2)).toEqual([
      { text: "Juntas: R$ 10,00 · 10 min · 5 km", strong: false },
      { text: "Separadas sai mais barato: R$ 7,00 ✔", strong: true },
    ]);
  });

  it("sem a comparação (alguma sozinha não cotou), só a de juntas", () => {
    expect(quoteLines(quote(), 2)).toEqual([{ text: "Juntas: R$ 10,00 · 10 min · 5 km", strong: true }]);
  });

  it("uma parada: uma linha, sem 'Juntas'", () => {
    expect(quoteLines(quote(), 1)).toEqual([{ text: "R$ 10,00 · 10 min · 5 km", strong: true }]);
  });

  it("sem cotação: a frase do servidor; sem frase, nada", () => {
    expect(quoteLines(null, 2, "A TaOn não cotou esta corrida agora. Dá para chamar mesmo assim.")).toEqual([
      { text: "A TaOn não cotou esta corrida agora. Dá para chamar mesmo assim.", strong: false },
    ]);
    expect(quoteLines(null, 2)).toEqual([]);
  });

  it("o total na barra só quando todas as corridas cotaram", () => {
    expect(callSummary(5, 2, [quote({ value_q: 1840 }), quote({ value_q: 1290 })])).toBe(
      "5 pedidos em 2 corridas · R$ 31,30",
    );
    expect(callSummary(5, 2, [quote({ value_q: 1840 }), null])).toBe("5 pedidos em 2 corridas");
    expect(callSummary(1, 1, [])).toBe("1 pedido em 1 corrida");
  });
});

describe("uma maquininha por corrida (P1-12)", () => {
  const stops = [
    stop("NB-A01", { needs_machine: true }),
    stop("NB-A02", { needs_machine: true }),
    stop("NB-A03"),
  ];
  const editing = [
    { number: 2, refs: ["NB-A02"] },
    { number: 1, refs: ["NB-A01", "NB-A03"] },
    { number: 3, refs: ["NB-A03"] },
  ];

  it("só as corridas que levam cartão, na ordem das letras", () => {
    expect(ridesNeedingMachine(editing, stops)).toEqual([1, 2]);
  });

  it("cada corrida recebe uma diferente, e a escolha do operador fica", () => {
    expect(assignMachines([1, 2], ["m:1", "m:2"])).toEqual({ 1: "m:1", 2: "m:2" });
    expect(assignMachines([1, 2], ["m:1", "m:2"], { 2: "m:1" })).toEqual({ 1: "m:2", 2: "m:1" });
  });

  it("escolha repetida não passa: a segunda corrida recebe outra", () => {
    expect(assignMachines([1, 2], ["m:1", "m:2"], { 1: "m:1", 2: "m:1" })).toEqual({ 1: "m:1", 2: "m:2" });
  });

  it("faltando maquininha, a corrida fica sem, e a frase diz quantas faltam", () => {
    expect(assignMachines([1, 2], ["m:1"])).toEqual({ 1: "m:1", 2: "" });
    expect(machineShortfall(2, 1)).toBe("Faltam maquininhas: 2 corridas levam cartão e só 1 está livre.");
    expect(machineShortfall(3, 0)).toBe("Faltam maquininhas: 3 corridas levam cartão e nenhuma está livre.");
    expect(machineShortfall(3, 2)).toBe("Faltam maquininhas: 3 corridas levam cartão e só 2 estão livres.");
    expect(machineShortfall(2, 2)).toBe("");
  });

  it("a chamada leva a maquininha DA corrida, nunca a mesma para todas", () => {
    const calls = rideCalls(editing.slice(0, 2), stops, { 1: "m:1", 2: "m:2" });
    expect(calls.map((call) => [call.number, call.machine])).toEqual([[1, "m:1"], [2, "m:2"]]);
  });
});

describe("troco conferido", () => {
  const withChange = stop("NB-A01", { change_out_suggested_q: 2000 });

  it("vale o que o operador digitou; sem mexer, o sugerido", () => {
    expect(changeValue(withChange, {})).toBe("20,00");
    expect(changeValue(withChange, { "NB-A01": " 30,00 " })).toBe("30,00");
  });

  it("apagar o troco é mandar sem troco", () => {
    const calls = rideCalls([{ number: 1, refs: ["NB-A01"] }], [withChange], {}, { "NB-A01": "" });
    expect(calls[0]!.change_out).toEqual({});
  });

  it("troco digitado vai na chamada", () => {
    const calls = rideCalls([{ number: 1, refs: ["NB-A01"] }], [withChange], {}, { "NB-A01": "50,00" });
    expect(calls[0]!.change_out).toEqual({ "NB-A01": "50,00" });
  });
});

describe("balanço por corrida", () => {
  it("recusa do servidor (4xx) é desta corrida: as outras seguem", () => {
    expect(failureStops(400)).toBe(false);
    expect(failureStops(409)).toBe(false);
    expect(failureStops(429)).toBe(false);
  });

  it("sem rede ou servidor fora: para", () => {
    expect(failureStops(0)).toBe(true);
    expect(failureStops(500)).toBe(true);
    expect(failureStops(503)).toBe(true);
  });

  it("o cartão diz qual corrida e quais pedidos", () => {
    expect(rideFailureTitle(2, ["A47", "C03"])).toBe("A corrida B não abriu (A47, C03)");
  });
});
