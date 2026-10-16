import { describe, expect, it } from "vitest";

import {
  FREE_SCENARIO,
  NO_CROSS,
  crossItems,
  dimensionItems,
  exploreAxisLabel,
  exploreCsv,
  exploreCsvValue,
  exploreResultDescription,
  exploreValueHeader,
  scenarioMenuItems,
} from "~/presentation/explore";

const report = {
  unit: "q",
  metric_label: "Faturamento",
  dimension: "channel",
  dimension_label: "Canal",
  dimension2: "",
  dimension2_label: "",
  date_from: "2026-09-11",
  date_to: "2026-10-08",
  truncated: 0,
  rows: [
    { key: "balcao", label: "Balcão", key2: "", label2: "", value: 123456 },
    { key: "ifood", label: "iFood", key2: "", label2: "", value: 7890 },
  ],
};

describe("seletor de Cenário", () => {
  it("abre com o corte livre e os exemplos; sem salvos, não mostra o grupo vazio", () => {
    const groups = scenarioMenuItems([], [{ name: "Faturamento por hora" }]);
    expect(groups).toEqual([
      [{ label: "Nenhum (corte livre)", value: FREE_SCENARIO }],
      [
        { type: "label", label: "Exemplos" },
        { label: "Faturamento por hora", value: "example:Faturamento por hora" },
      ],
    ]);
  });

  it("os salvos vêm antes dos exemplos, e o favorito leva a estrela como ícone", () => {
    const groups = scenarioMenuItems(
      [
        { id: 7, name: "Sábado", pinned: true },
        { id: 8, name: "Domingo", pinned: false },
      ],
      [],
    );
    expect(groups[1]).toEqual([
      { type: "label", label: "Meus cenários" },
      { label: "Sábado", value: "view:7", icon: "i-lucide-star" },
      { label: "Domingo", value: "view:8" },
    ]);
    expect(groups).toHaveLength(2);
  });

  it("nenhum item tem valor vazio (o Select do Nuxt UI recusa)", () => {
    const values = scenarioMenuItems([{ id: 1, name: "A", pinned: false }], [{ name: "B" }])
      .flat()
      .filter((item) => item.type !== "label")
      .map((item) => item.value);
    expect(values.every(Boolean)).toBe(true);
  });
});

describe("Dimensão e Cruzamento", () => {
  it("as dimensões ganham o nome humano; chave desconhecida fica como veio", () => {
    expect(dimensionItems(["time", "sku", "nova"])).toEqual([
      { label: "Tempo (dia)", value: "time" },
      { label: "Produto", value: "sku" },
      { label: "nova", value: "nova" },
    ]);
  });

  it("o Cruzamento começa por 'Sem cruzamento', com valor próprio", () => {
    expect(crossItems(["weekday"])).toEqual([
      { label: "Sem cruzamento", value: NO_CROSS },
      { label: "Dia da semana", value: "weekday" },
    ]);
  });
});

describe("legenda do resultado", () => {
  it("diz a janela", () => {
    expect(exploreResultDescription(report)).toBe("11/09 a 08/10");
  });

  it("diz quantas linhas o servidor cortou", () => {
    expect(exploreResultDescription({ ...report, truncated: 12 })).toBe(
      "11/09 a 08/10. Mostrando as 2 maiores; 12 linhas ficaram fora.",
    );
  });

  it("o eixo da série diz o grão do balde", () => {
    expect(exploreAxisLabel("day")).toBe("Dia");
    expect(exploreAxisLabel("week")).toBe("Semana");
    expect(exploreAxisLabel("month")).toBe("Mês");
  });
});

describe("CSV do quadro", () => {
  it("dinheiro sai em reais com duas casas e vírgula, com a moeda no cabeçalho", () => {
    expect(exploreCsvValue("q", 123456)).toBe("1234,56");
    expect(exploreCsvValue("qty", 12.5)).toBe(12.5);
    expect(exploreValueHeader(report)).toBe("Faturamento (R$)");
    expect(exploreValueHeader({ unit: "qty", metric_label: "Quantidade vendida" })).toBe("Quantidade vendida");
  });

  it("ranking: dimensão e valor", () => {
    expect(exploreCsv(report)).toEqual({
      header: ["Canal", "Faturamento (R$)"],
      rows: [
        ["Balcão", "1234,56"],
        ["iFood", "78,90"],
      ],
    });
  });

  it("cruzamento: as duas dimensões e o valor", () => {
    const cross = {
      ...report,
      unit: "count",
      metric_label: "Pedidos",
      dimension2: "weekday",
      dimension2_label: "Dia da semana",
      rows: [{ key: "balcao", label: "Balcão", key2: "sat", label2: "Sábado", value: 40 }],
    };
    expect(exploreCsv(cross)).toEqual({
      header: ["Canal", "Dia da semana", "Pedidos"],
      rows: [["Balcão", "Sábado", 40]],
    });
  });

  it("série no tempo: os mesmos baldes do gráfico; ponto sem dado fica vazio", () => {
    const csv = exploreCsv(
      { ...report, dimension: "time", dimension_label: "Tempo (dia)" },
      {
        axisLabel: "Semana",
        points: [
          { label: "15/09", values: { value: 100050 } },
          { label: "22/09", values: { value: null } },
        ],
      },
    );
    expect(csv).toEqual({
      header: ["Semana", "Faturamento (R$)"],
      rows: [
        ["15/09", "1000,50"],
        ["22/09", ""],
      ],
    });
  });
});
