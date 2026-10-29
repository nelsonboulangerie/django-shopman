import { describe, expect, it } from "vitest";
import {
  deliveryAnswer,
  estimatedRidesHint,
  ridesHint,
} from "~/presentation/delivery";

const nbsp = (text: string) => text.replace(/\u00a0/g, " ");

describe("entregas: custo da TaOn e frete", () => {
  it("responde se o frete cobriu a TaOn", () => {
    expect(deliveryAnswer({ rides: 0, cost_q: 0, balance_q: 0 })).toBe(
      "Nenhuma corrida da TaOn no período.",
    );
    expect(
      nbsp(deliveryAnswer({ rides: 2, cost_q: 2000, balance_q: 500 })),
    ).toBe("O frete cobriu a TaOn e sobrou R$ 5,00.");
    expect(deliveryAnswer({ rides: 2, cost_q: 2000, balance_q: 0 })).toBe(
      "O frete cobriu a TaOn, exatamente.",
    );
    expect(
      nbsp(deliveryAnswer({ rides: 2, cost_q: 2000, balance_q: -1250 })),
    ).toBe("A casa pôs R$ 12,50 do bolso nas entregas.");
  });

  it("diz quantas corridas entraram pela cotação", () => {
    expect(estimatedRidesHint(0)).toBe("");
    expect(estimatedRidesHint(1)).toBe(
      "1 corrida terminou sem valor final da TaOn e entrou pela cotação.",
    );
    expect(estimatedRidesHint(3)).toBe(
      "3 corridas terminaram sem valor final da TaOn e entraram pela cotação.",
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
