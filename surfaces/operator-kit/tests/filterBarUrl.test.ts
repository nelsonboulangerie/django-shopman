import { describe, expect, it } from "vitest";

import {
  chipLabel,
  filtersFromQuery,
  filtersToQuery,
  isActive,
  mergeFilterQuery,
  needsSearch,
  rangeText,
  searchOptions,
  setValues,
  toggleOption,
} from "../app/presentation/filterBar";
import type { ActiveFilters, FilterDimension } from "../app/types/filters";

// O filtro universal: vários campos, vários valores, e tudo na URL. Estes testes
// prendem a ida e a volta da querystring, que é o que garante que recarregar,
// voltar do detalhe ou mandar o link devolvem o MESMO recorte.

const payment: FilterDimension = {
  id: "payment",
  label: "Pagamento",
  type: "multi-select",
  options: [
    { value: "pix", label: "Pix", count: 12 },
    { value: "card", label: "Cartão", count: 7 },
    { value: "cash", label: "Dinheiro", count: 3 },
  ],
};
const status: FilterDimension = {
  id: "status",
  label: "Situação",
  type: "multi-select",
  options: [
    { value: "completed", label: "Concluído" },
    { value: "cancelled", label: "Cancelado" },
  ],
};
const published: FilterDimension = { id: "published", label: "Publicado", type: "boolean", options: [] };
const kind: FilterDimension = {
  id: "kind",
  label: "Tipo",
  type: "single-select",
  options: [{ value: "a", label: "A" }, { value: "b", label: "B" }],
};
const customer: FilterDimension = { id: "customer", label: "Cliente", type: "text", options: [] };
const total: FilterDimension = {
  id: "total",
  label: "Total",
  type: "number-range",
  options: [],
  formatValue: (v) => `R$ ${v}`,
};
const closed: FilterDimension = { id: "closed", label: "Fechado em", type: "date-range", options: [] };

const all = [payment, status, published, kind, customer, total, closed];

describe("vários campos, vários valores", () => {
  it("acumula valores no mesmo campo e campos diferentes convivem", () => {
    let filters: ActiveFilters = {};
    filters = toggleOption(filters, payment, "pix");
    filters = toggleOption(filters, payment, "card");
    filters = toggleOption(filters, status, "cancelled");
    expect(filters).toEqual({ payment: ["pix", "card"], status: ["cancelled"] });
    expect(chipLabel(payment, filters)).toBe("Pagamento: Pix, Cartão");
    expect(chipLabel(status, filters)).toBe("Situação: Cancelado");
  });

  it("campo digitado: setValues grava, vazio apaga", () => {
    expect(setValues({}, "customer", ["  maria "])).toEqual({ customer: ["maria"] });
    expect(setValues({ customer: ["maria"] }, "customer", [""])).toEqual({});
    expect(setValues({}, "total", ["", ""])).toEqual({});
    expect(setValues({}, "total", ["1000", ""])).toEqual({ total: ["1000", ""] });
  });

  it("intervalo com um lado aberto conta como ativo; dois lados abertos não", () => {
    expect(isActive({ total: ["", "5000"] }, "total")).toBe(true);
    expect(isActive({ total: ["", ""] }, "total")).toBe(false);
  });

  it("chip de intervalo e de texto se leem como frase", () => {
    expect(rangeText(total, ["10", "50"])).toBe("R$ 10 a R$ 50");
    expect(rangeText(total, ["10", ""])).toBe("a partir de R$ 10");
    expect(rangeText(total, ["", "50"])).toBe("até R$ 50");
    expect(chipLabel(closed, { closed: ["2026-10-01", "2026-10-03"] })).toBe("Fechado em: 01/10 a 03/10");
    expect(chipLabel(closed, { closed: ["2026-10-01", "2026-10-01"] })).toBe("Fechado em: 01/10");
    expect(chipLabel(customer, { customer: ["maria"] })).toBe("Cliente: maria");
  });
});

describe("busca nas opções", () => {
  it("liga sozinha a partir de 8 opções, ou quando o campo pede", () => {
    expect(needsSearch(payment)).toBe(false);
    const many = { ...payment, options: Array.from({ length: 8 }, (_, i) => ({ value: `v${i}`, label: `Opção ${i}` })) };
    expect(needsSearch(many)).toBe(true);
    expect(needsSearch({ ...payment, searchable: true })).toBe(true);
  });

  it("ignora acento e caixa", () => {
    expect(searchOptions(payment.options, "cartao").map((o) => o.value)).toEqual(["card"]);
    expect(searchOptions(payment.options, "PIX").map((o) => o.value)).toEqual(["pix"]);
    expect(searchOptions(payment.options, "")).toHaveLength(3);
  });
});

describe("URL", () => {
  const filters: ActiveFilters = {
    payment: ["pix", "card"],
    status: ["completed"],
    published: ["true"],
    customer: ["maria souza"],
    total: ["", "5000"],
    closed: ["2026-10-01", "2026-10-03"],
  };

  it("serializa uma chave por campo, só os ativos", () => {
    expect(filtersToQuery(all, filters)).toEqual({
      payment: "pix,card",
      status: "completed",
      published: "true",
      customer: "maria souza",
      total: "..5000",
      closed: "2026-10-01..2026-10-03",
    });
    expect(filtersToQuery(all, {})).toEqual({});
  });

  it("ida e volta devolvem o mesmo recorte", () => {
    expect(filtersFromQuery(all, filtersToQuery(all, filters))).toEqual(filters);
  });

  it("descarta valor malformado em vez de virar filtro que não casa nada", () => {
    expect(
      filtersFromQuery(all, {
        published: "talvez",
        kind: "a,b",
        total: "abc..50",
        closed: "ontem..2026-10-03",
        payment: "pix,,pix,card",
        other: "x",
      }),
    ).toEqual({ kind: ["a"], total: ["", "50"], closed: ["", "2026-10-03"], payment: ["pix", "card"] });
  });

  it("aceita valor repetido do router (pega o primeiro)", () => {
    expect(filtersFromQuery([payment], { payment: ["pix,cash", "card"] })).toEqual({ payment: ["pix", "cash"] });
  });

  it("mergeFilterQuery troca só as chaves dos campos e zera a página", () => {
    const current = { from: "2026-10-01", q: "ana", page: "3", payment: "cash" };
    expect(mergeFilterQuery(current, all, { status: ["cancelled"] }, ["page"])).toEqual({
      from: "2026-10-01",
      q: "ana",
      status: "cancelled",
    });
  });
});
