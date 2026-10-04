// "Sobrou ou faltou?" (V4-BI, prévia `bi-sobra4.html`): as frases que a leitura do dia
// mostra saem daqui, e cada uma é a da prévia com o dado real.
import { describe, expect, it } from "vitest";
import type { BIOverShortReport, BIOverShortRow } from "~/types/bi";
import { BI_SECTIONS, biSections, swipeNeighbours } from "~/presentation/biSections";
import { cashAnswer, customersAnswer, salesAnswer } from "~/presentation/bi";
import {
  barGeometry,
  barScale,
  carryLabel,
  clientCount,
  compareName,
  compareOptions,
  historyDaysLabel,
  lotsLine,
  ordersLinkLabel,
  unavailableText,
  collectionsOf,
  compareCaption,
  dayCaption,
  dayName,
  filterRows,
  hiddenRowsSummary,
  historyHeading,
  historyText,
  inTypical,
  outcomeText,
  overShortAnswer,
  overShortTitle,
  overUnit,
  planLabel,
  shortUnit,
  soldoutText,
  typicalLine,
  typicalName,
  verdictMeta,
  versusTypicalText,
} from "~/presentation/overShort";

function row(overrides: Partial<BIOverShortRow>): BIOverShortRow {
  return {
    sku: "CRO",
    name: "Croissant Manteiga",
    collection_ref: "folhados",
    collection: "Folhados",
    verdict: "short",
    made: "44",
    sold: "44",
    leftover: "0",
    soldout_at: "10:40",
    lost_estimate: "14",
    typical_sold: "50",
    typical_made: "48",
    history: ["short", "short", "short", "over"],
    leftover_cost_q: null,
    lots: [],
    sales_by_hour: [],
    history_days: ["2026-09-26", "2026-09-19", "2026-09-12", "2026-09-05"],
    planned: "44",
    planned_lots: 0,
    orders: 0,
    alert_requests: 0,
    unavailable: [],
    shift: "",
    ...overrides,
  };
}

const croissant = row({});
const baguete = row({
  sku: "BGT",
  name: "Baguette de Tradition",
  collection_ref: "paes",
  collection: "Pães",
  verdict: "over",
  made: "60",
  sold: "48",
  leftover: "12",
  soldout_at: "",
  lost_estimate: "",
  history: ["over", "over", "right", "over"],
  leftover_cost_q: 6100,
});
const shokupan = row({
  sku: "FORMA",
  name: "Shokupan",
  collection_ref: "paes",
  collection: "Pães",
  verdict: "right",
  made: "18",
  sold: "18",
  soldout_at: "17:50",
  lost_estimate: "",
  typical_sold: "17",
  history: ["right", "right", "right", "right"],
});

// sábado, 03/10/2026; comparação: os 4 sábados anteriores.
const report: BIOverShortReport = {
  day: "2026-10-03",
  weekday_label: "sábado",
  opens_at: "07:00",
  closes_at: "18:00",
  compare_days: ["2026-09-26", "2026-09-19", "2026-09-12", "2026-09-05"],
  previous_day: "2026-10-02",
  next_day: "",
  plan_day: "2026-10-10",
  rows: [croissant, baguete, shokupan],
  summary: {
    short: 1,
    over: 1,
    right: 1,
    lost_estimate: "14",
    leftover_units: "12",
    leftover_cost_q: 6100,
    cost_complete: true,
  },
  typical: { days: 4, short: "2", over: "3", leftover_units: "26", leftover_cost_q: 14000 },
  compare: "typical",
  answer_short: [],
  answer_over: [],
};

describe("o dia e a comparação", () => {
  it("o título é a pergunta, com o dia", () => {
    expect(overShortTitle("2026-10-03", "2026-10-04")).toBe("Sobrou ou faltou ontem?");
    expect(overShortTitle("2026-10-01", "2026-10-04")).toBe("Sobrou ou faltou na quinta 01/10?");
    expect(overShortTitle("2026-09-26", "2026-10-04")).toBe("Sobrou ou faltou no sábado 26/09?");
  });

  it("o controle do dia diz o nome e a data curta", () => {
    expect(dayName("2026-10-03", "2026-10-04")).toBe("Ontem");
    expect(dayCaption("2026-10-03")).toBe("sáb 03/10");
    expect(dayName("2026-09-30", "2026-10-04")).toBe("Quarta");
  });

  it("o típico concorda com o dia da semana", () => {
    expect(typicalName("2026-10-03")).toBe("sábado típico");
    expect(typicalName("2026-09-28")).toBe("segunda típica");
    expect(inTypical("2026-09-28")).toBe("numa segunda típica");
    expect(inTypical("2026-10-03")).toBe("num sábado típico");
  });

  it("a comparação nomeia os dias, do mais antigo ao mais recente", () => {
    expect(compareCaption(report.day, report.compare_days)).toBe("4 sábados: 05/09 a 26/09");
    expect(historyHeading(report.day, report.compare_days)).toBe("Nos 4 sábados");
    expect(compareCaption(report.day, [])).toBe("sem dias de comparação ainda");
  });
});

describe("a resposta", () => {
  it("diz onde faltou (e quando acabou) e onde sobrou (e quanto)", () => {
    expect(overShortAnswer(report)).toBe(
      "Faltou Croissant Manteiga (acabou às 10:40); sobrou Baguette de Tradition (12 un.).",
    );
  });

  it("agrupa quando são vários", () => {
    const two = { rows: [croissant, row({ sku: "CI", name: "Ciabatta" }), shokupan] };
    expect(overShortAnswer(two)).toBe("Faltou Croissant Manteiga e mais 1 (acabou às 10:40).");
  });

  it("dia sem lote e dia todo na medida têm frase própria", () => {
    expect(overShortAnswer({ rows: [] })).toMatch(/Nenhum lote fechado/);
    expect(overShortAnswer({ rows: [shokupan] })).toMatch(/^Tudo na medida/);
  });

  it("os três números trazem a unidade e o típico ao lado", () => {
    expect(shortUnit(report)).toBe("produto · ~14 vendas perdidas (est.)");
    expect(overUnit(report)).toBe("produto · 12 un. · R$ 61 de custo");
    expect(typicalLine(report, "short")).toBe("sábado típico: 2 produtos");
    expect(typicalLine(report, "over")).toBe("sábado típico: 26 un. · R$ 140");
    expect(typicalLine(report, "right")).toBe("acabou depois das 17h ou sobrou até 2");
  });

  it("custo de sobra incompleto se declara", () => {
    const partial = { ...report, summary: { ...report.summary, cost_complete: false } };
    expect(overUnit(partial)).toContain("(parcial)");
  });
});

describe("cada produto", () => {
  it("o veredito tem nome e tom fixos", () => {
    expect(verdictMeta("short")).toMatchObject({ label: "Faltou", tone: "destructive" });
    expect(verdictMeta("over")).toMatchObject({ label: "Sobrou", tone: "warning" });
    expect(verdictMeta("right")).toMatchObject({ label: "Na medida", tone: "success" });
  });

  it("o desfecho da barra, a hora e o histórico", () => {
    expect(outcomeText(croissant)).toBe("~14 perdidas");
    expect(outcomeText(baguete)).toBe("sobrou 12");
    expect(outcomeText(shokupan)).toBe("zerou");
    expect(soldoutText(baguete)).toBe("não acabou");
    expect(historyText(croissant)).toBe("faltou 3 de 4");
    expect(historyText(shokupan)).toBe("na medida 4 de 4");
    expect(historyText(row({ history: [] }))).toBe("sem histórico");
  });

  it("contra o típico", () => {
    expect(versusTypicalText(croissant)).toBe("típico vende ~50; fez 44");
    expect(versusTypicalText(baguete)).toBe("típico ~50; R$ 61 de custo");
    expect(versusTypicalText(shokupan)).toBe("acabou perto de fechar");
  });

  it("a barra compacta usa uma escala comum", () => {
    const scale = barScale(report.rows);
    expect(scale).toBe(60);
    const geometry = barGeometry(croissant, scale);
    expect(Math.round(geometry.made)).toBe(73);
    expect(Math.round(geometry.lost)).toBe(23);
    expect(geometry.lostFrom).toBe(geometry.sold);
    expect(Math.round(geometry.typical!)).toBe(83);
  });

  it("o resto da lista vira uma linha só", () => {
    expect(hiddenRowsSummary([baguete, shokupan])).toBe(
      "+2 produtos: Baguette de Tradition (sobrou 12) · Shokupan (na medida)",
    );
  });

  it("recortes: veredito, coleção e busca sem acento", () => {
    expect(filterRows(report.rows, { verdict: "over", collection: "", query: "" })).toEqual([baguete]);
    expect(filterRows(report.rows, { verdict: "", collection: "paes", query: "" })).toEqual([baguete, shokupan]);
    expect(filterRows(report.rows, { verdict: "", collection: "", query: "croiss" })).toEqual([croissant]);
    expect(filterRows(report.rows, { verdict: "", collection: "", query: "forma" })).toEqual([shokupan]);
    expect(collectionsOf(report.rows)).toEqual([
      { ref: "folhados", name: "Folhados" },
      { ref: "paes", name: "Pães" },
    ]);
  });

  it("o caminho para o plano nomeia o dia", () => {
    expect(planLabel("2026-10-10")).toBe("Abrir o plano de sábado 10/10");
    expect(planLabel("")).toBe("");
  });
});

describe("as outras respostas", () => {
  it("vendas", () => {
    expect(salesAnswer({ orders_total: 120, revenue_total_q: 4820000, previous: { revenue_total_q: 4460000 } })).toBe(
      "R$ 48,2 mil em 120 pedidos, 8% acima do período anterior.",
    );
    expect(salesAnswer({ orders_total: 0, revenue_total_q: 0, previous: { revenue_total_q: 0 } })).toBe(
      "Nenhuma venda no período.",
    );
  });

  it("caixa (auditoria do Dono)", () => {
    expect(cashAnswer({ shifts_total: 12, closings_missing: 2, difference_total_q: -3500 }).replace(/\u00a0/g, " ")).toBe(
      "12 turnos fechados; 2 dias sem fechamento; no acumulado, faltou R$ 35,00.",
    );
    expect(cashAnswer({ shifts_total: 1, closings_missing: 0, difference_total_q: 0 })).toBe(
      "1 turno fechado; no acumulado, a contagem bateu.",
    );
  });

  it("clientes", () => {
    expect(customersAnswer({ at_risk: 14, with_insight: 220, new_by_week: [{ new_customers: 3 }, { new_customers: 5 }] })).toBe(
      "14 clientes em risco de sumir, de 220 com histórico; 8 clientes novos no período.",
    );
  });
});

describe("seções do rail", () => {
  it("oito leituras, com os ícones da prévia", () => {
    expect(BI_SECTIONS.map((s) => s.label)).toEqual([
      "Produção",
      "Vendas",
      "Caixa",
      "Clientes",
      "Perfis",
      "Explorar",
      "Projeção",
      "Cenários",
    ]);
    expect(BI_SECTIONS[0]!.icon).toBe("lucide:chef-hat");
  });

  it("cada seção leva a janela de análise", () => {
    expect(biSections("period=week")[1]!.to).toBe("/sales?period=week");
    expect(biSections("")[0]!.to).toBe("/");
  });
});


describe("V6: a resposta agrupada, a comparação escolhida e o que aconteceu depois", () => {
  it("a resposta fala por coleção e turno, como a prévia", () => {
    const grouped = {
      ...report,
      answer_short: [{ label: "Folhados", kind: "collection", shift: "morning", count: 3 }],
      answer_over: [{ label: "Baguette de Tradition", kind: "product", shift: "afternoon", count: 1 }],
    };
    expect(overShortAnswer(grouped)).toBe("Faltou nos folhados de manhã; sobrou Baguette de Tradition à tarde.");
  });

  it("o artigo da coleção sai da primeira palavra, e o resto vira \"mais N\"", () => {
    const grouped = {
      ...report,
      answer_short: [
        { label: "Bebidas quentes", kind: "collection", shift: "", count: 2 },
        { label: "Mercearia", kind: "collection", shift: "evening", count: 2 },
        { label: "Ciabatta", kind: "product", shift: "afternoon", count: 1 },
      ],
      answer_over: [],
    };
    expect(overShortAnswer(grouped)).toBe("Faltou nas bebidas quentes, na mercearia à noite e mais 1.");
  });

  it("o controle de comparação oferece as três bases, e o nome acompanha", () => {
    expect(compareOptions("2026-10-03").map((option) => `${option.label} (${option.reach})`)).toEqual([
      "sábado típico (4 sábados)",
      "sábado anterior (um só)",
      "sábado típico (8 sábados)",
    ]);
    expect(compareName("2026-10-03", "last")).toBe("sábado anterior");
    expect(inTypical("2026-09-28", "last")).toBe("numa segunda anterior");
    expect(typicalLine({ ...report, compare: "last" }, "short")).toBe("sábado anterior: 2 produtos");
  });

  it("canais que saíram do ar no mesmo minuto vão juntos; Me avise conta clientes", () => {
    expect(unavailableText({ at: "10:40", channels: ["iFood", "Meta", "Google"], automatic: true })).toBe(
      "iFood, Meta e Google indisponíveis às 10:40",
    );
    expect(unavailableText({ at: "11:05", channels: ["Site"], automatic: false })).toBe("Site indisponível às 11:05");
    expect(clientCount(5)).toBe("5 clientes");
    expect(clientCount(1)).toBe("1 cliente");
  });

  it("o lote que o plano tinha e não fechou aparece com o número do plano", () => {
    const lots = [
      { ref: "WO-0412", finished_at: "06:30", qty: "24" },
      { ref: "WO-0418", finished_at: "08:20", qty: "20" },
    ];
    expect(lotsLine(row({ lots, planned_lots: 3, planned: "44" }))).toBe("Sem 3º lote: o plano dizia 44.");
    expect(lotsLine(row({ lots, planned_lots: 2 }))).toBe("2 lotes · 44 un. feitas");
  });

  it("os caminhos ao registro dizem quantos e o que abrem", () => {
    expect(ordersLinkLabel(44)).toBe("Abrir os 44 pedidos");
    expect(ordersLinkLabel(1)).toBe("Abrir o pedido");
    expect(historyDaysLabel("2026-10-03", 4)).toBe("Os 4 sábados");
    expect(historyDaysLabel("2026-10-03", 1)).toBe("O sábado");
    expect(carryLabel("2026-10-10")).toBe("Levar ao plano do próximo sábado");
    expect(carryLabel("2026-10-05")).toBe("Levar ao plano da próxima segunda");
  });

  it("o deslizar do celular segue a ordem do rail e não dá a volta", () => {
    const sections = biSections("period=28d");
    expect(swipeNeighbours(sections, "/sales").previous?.key).toBe("production");
    expect(swipeNeighbours(sections, "/sales").next?.key).toBe("cash");
    expect(swipeNeighbours(sections, "/").previous).toBeNull();
    expect(swipeNeighbours(sections, "/scenarios").next).toBeNull();
    expect(swipeNeighbours(BI_SECTIONS, "/nada").index).toBe(-1);
  });
});
