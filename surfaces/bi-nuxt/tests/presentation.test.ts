import { describe, expect, it } from "vitest";
import {
  WEEKDAY_LABELS,
  coverageLabel,
  formatMinutes,
  formatMoney,
  formatMoneyCompact,
  formatQty,
  hourLabel,
  shortDate,
} from "~/presentation/bi";

describe("presentation/bi", () => {
  it("formata centavos em pt-BR", () => {
    expect(formatMoney(123456).replace(/ /g, " ")).toBe("R$ 1.234,56");
    expect(formatMoney(-200).replace(/ /g, " ")).toBe("-R$ 2,00");
  });

  it("compacta valores grandes para tiles", () => {
    expect(formatMoneyCompact(123456789).replace(/ /g, " ")).toBe("R$ 1.234,6 mil");
    expect(formatMoneyCompact(4000).replace(/ /g, " ")).toBe("R$ 40,00");
  });

  it("quantidades e minutos trocam ponto por vírgula", () => {
    expect(formatQty("38.5")).toBe("38,5");
    expect(formatMinutes("23.5")).toBe("23,5 min");
  });

  it("datas curtas e rótulos", () => {
    expect(shortDate("2026-08-14")).toBe("14/08");
    expect(hourLabel(5)).toBe("5h");
    expect(WEEKDAY_LABELS[0]).toBe("seg");
  });

  it("cobertura sempre carrega o denominador", () => {
    expect(coverageLabel(3, 12)).toBe("3 de 12 fornadas medidas");
    expect(coverageLabel(0, 0)).toBe("sem fornadas no período");
  });
});
