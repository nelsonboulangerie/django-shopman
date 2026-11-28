import { describe, expect, it } from "vitest";

import { csvMoneyToCents, csvText, parseCsv } from "../app/presentation/csv";

describe("CSV pt-BR", () => {
  it.each([
    ["1.234,56", 123456],
    ["12,50", 1250],
    ["12.50", 1250],
  ])("lê %s como %i centavos", (source, expected) => {
    expect(csvMoneyToCents(source)).toBe(expected);
  });

  it("escreve BOM, ponto e vírgula, vírgula decimal e cabeçalho escapado", () => {
    expect(
      csvText({ header: ['Preço; "atual"'], rows: [[1234.56]] }),
    ).toBe('\uFEFF"Preço; ""atual"""\n1234,56');
  });

  it("atribui à própria linha o campo que sobra", () => {
    expect(parseCsv("Nome;Preço\nPão;12,50;sobra").errors).toEqual([
      { row: 2, detail: "A linha tem 3 campos; o cabeçalho tem 2." },
    ]);
  });
});
