import { describe, expect, it } from "vitest";
import {
  DELIVERY_TOTAL_KEY,
  deliveryAnswer,
  deliveryServiceCsv,
  deliveryServiceRows,
  estimatedRidesHint,
  rideMinutes,
  rideTimingCsv,
  rideTimingRows,
  ridesHint,
} from "~/presentation/delivery";

const nbsp = (text: string) => text.replace(/\u00a0/g, " ");

describe("entregas: custo das entregas e frete", () => {
  it("responde se o frete cobriu as entregas", () => {
    expect(deliveryAnswer({ rides: 0, cost_q: 0, balance_q: 0 })).toBe(
      "Nenhuma corrida no período.",
    );
    expect(
      nbsp(deliveryAnswer({ rides: 2, cost_q: 2000, balance_q: 500 })),
    ).toBe("O frete cobriu as entregas e sobrou R$ 5,00.");
    expect(deliveryAnswer({ rides: 2, cost_q: 2000, balance_q: 0 })).toBe(
      "O frete cobriu as entregas, exatamente.",
    );
    expect(
      nbsp(deliveryAnswer({ rides: 2, cost_q: 2000, balance_q: -1250 })),
    ).toBe("A casa pôs R$ 12,50 do bolso nas entregas.");
  });

  it("diz quantas corridas entraram pela cotação", () => {
    expect(estimatedRidesHint(0)).toBe("");
    expect(estimatedRidesHint(1)).toBe(
      "1 corrida terminou sem valor final e entrou pela cotação.",
    );
    expect(estimatedRidesHint(3)).toBe(
      "3 corridas terminaram sem valor final e entraram pela cotação.",
    );
  });

  it("conta as entregas de cada corrida", () => {
    expect(ridesHint({ rides: 1, deliveries: 1 })).toBe(
      "1 entrega em 1 corrida",
    );
    expect(ridesHint({ rides: 9, deliveries: 12 })).toBe(
      "12 entregas em 9 corridas",
    );
  });
});

describe("entregas: uma linha por serviço e o total embaixo (#3144)", () => {
  const service = (name: string, cost_q: number) => ({
    service: name.toLowerCase(), name, rides: 1, deliveries: 1, cost_q, fee_q: 800,
    balance_q: 800 - cost_q, cost_per_delivery_q: cost_q,
  });
  const report = {
    services: [service("TaOn", 1500), service("Entregadores da casa", 900)],
    rides: 2, deliveries: 2, cost_q: 2400, fee_q: 1600, balance_q: -800, cost_per_delivery_q: 1200,
  };

  it("as linhas dos serviços, na ordem do servidor, e o total por último", () => {
    const rows = deliveryServiceRows(report);
    expect(rows.map((row) => row.name)).toEqual(["TaOn", "Entregadores da casa", "Total"]);
    expect(rows.at(-1)).toMatchObject({ service: DELIVERY_TOTAL_KEY, cost_q: 2400, fee_q: 1600, balance_q: -800 });
  });

  it("sem corrida, sem linha (nem o total sozinho)", () => {
    expect(deliveryServiceRows({ ...report, services: [] })).toEqual([]);
  });

  it("o CSV leva o nome do cadastro e o total", () => {
    const csv = deliveryServiceCsv(deliveryServiceRows(report));
    expect(csv.header[0]).toBe("Serviço");
    expect(csv.rows.map((row) => row[0])).toEqual(["TaOn", "Entregadores da casa", "Total"]);
  });
});

describe("entregas: tempo das corridas por serviço (#2467)", () => {
  const services = [
    { service: "casa", name: "Entregadores da casa", rides: 1, accept_minutes: 0, pickup_minutes: 5, street_minutes: 12, total_minutes: 17 },
    { service: "taon", name: "TaOn", rides: 3, accept_minutes: 4.5, pickup_minutes: 15, street_minutes: null, total_minutes: null },
    { service: DELIVERY_TOTAL_KEY, name: "Total", rides: 4, accept_minutes: 3, pickup_minutes: 12.5, street_minutes: 12, total_minutes: 17 },
  ];

  it("as linhas vêm do servidor como estão: serviços pelo nome e o total embaixo", () => {
    expect(rideTimingRows({ services }).map((row) => row.name)).toEqual(["Entregadores da casa", "TaOn", "Total"]);
    expect(rideTimingRows({ services: [] })).toEqual([]);
  });

  it("cada serviço na mesma linha da tabela de custo; o total sempre embaixo", () => {
    expect(rideTimingRows({ services }, ["taon", "casa"]).map((row) => row.service)).toEqual(["taon", "casa", DELIVERY_TOTAL_KEY]);
    // Serviço sem custo no período (nada fechou valor) vem depois dos que a tabela de custo tem.
    expect(rideTimingRows({ services }, ["taon"]).map((row) => row.service)).toEqual(["taon", "casa", DELIVERY_TOTAL_KEY]);
  });

  it("minutos com vírgula; zero é medida; sem marco no período diz Sem medida", () => {
    expect(rideMinutes(4.5)).toBe("4,5 min");
    expect(rideMinutes(0)).toBe("0 min");
    expect(rideMinutes(null)).toBe("Sem medida");
  });

  it("o CSV em minutos, com a célula vazia onde não houve medida", () => {
    const csv = rideTimingCsv(services);
    expect(csv.header).toEqual(["Serviço", "Corridas", "Até aceitar (min)", "Até a coleta (min)", "Na rua (min)", "Total (min)"]);
    expect(csv.rows[1]).toEqual(["TaOn", 3, "4,5", "15", "", ""]);
    expect(csv.rows[2]?.[0]).toBe("Total");
  });
});
