import { describe, expect, it } from "vitest";

import {
  historyApiQuery,
  historyDimensions,
  historyQueryFromRoute,
  historyStatusClass,
  routeQueryFromHistory,
} from "../app/presentation/history";

// Histórico do Gestor: a URL é a fonte (período, busca, página e recortes) e o
// servidor filtra. Estes testes prendem a ida e a volta da URL e a query que vai
// ao endpoint.

describe("historyQueryFromRoute / routeQueryFromHistory", () => {
  it("URL limpa é hoje, sem busca e sem recorte", () => {
    const query = historyQueryFromRoute({});
    expect(query).toEqual({ period: { preset: "day", from: "", to: "" }, q: "", sku: "", page: 1, filters: {} });
    expect(routeQueryFromHistory(query)).toEqual({});
  });

  it("período, busca, página e vários recortes com vários valores vão e voltam", () => {
    const route = {
      period: "custom",
      from: "2026-09-01",
      to: "2026-09-30",
      q: "maria",
      page: "2",
      status: "completed,cancelled",
      payment: "pix,card",
    };
    const query = historyQueryFromRoute(route);
    expect(query.filters).toEqual({ status: ["completed", "cancelled"], payment: ["pix", "card"] });
    expect(routeQueryFromHistory(query)).toEqual(route);
  });

  it("o recorte por produto (o \"Abrir os N pedidos\" do B.I.) vai e volta, e chega ao endpoint", () => {
    const route = { period: "custom", from: "2026-10-03", to: "2026-10-03", sku: "CRO" };
    const query = historyQueryFromRoute(route);
    expect(query.sku).toBe("CRO");
    expect(routeQueryFromHistory(query)).toEqual(route);
    expect(historyApiQuery(query, "2026-10-04")).toEqual({ date_from: "2026-10-03", date_to: "2026-10-03", sku: "CRO" });
  });

  it("período desconhecido ou data malformada cai no padrão", () => {
    expect(historyQueryFromRoute({ period: "decada", from: "2026-09-01" }).period).toEqual({ preset: "day", from: "", to: "" });
    expect(historyQueryFromRoute({ period: "week", from: "ontem" }).period).toEqual({ preset: "week", from: "", to: "" });
  });
});

describe("historyApiQuery", () => {
  it("resolve o período em datas e manda os recortes separados por vírgula", () => {
    const query = historyQueryFromRoute({ period: "week", from: "2026-10-01", payment: "pix,cash", q: "H-1" });
    expect(historyApiQuery(query, "2026-10-03")).toEqual({
      // Semana de segunda a domingo, cortada em hoje: o futuro não tem pedido fechado.
      date_from: "2026-09-28",
      date_to: "2026-10-03",
      q: "H-1",
      payment: "pix,cash",
    });
  });

  it("hoje, sem nada, é só o dia", () => {
    expect(historyApiQuery(historyQueryFromRoute({}), "2026-10-03")).toEqual({ date_from: "2026-10-03", date_to: "2026-10-03" });
  });
});

describe("historyDimensions", () => {
  it("os quatro recortes existem antes da resposta e ganham as opções contadas depois", () => {
    expect(historyDimensions().map((d) => [d.id, d.options.length])).toEqual([
      ["status", 0],
      ["channel", 0],
      ["payment", 0],
      ["fulfillment", 0],
    ]);
    const dims = historyDimensions([
      { id: "payment", label: "Pagamento", options: [{ value: "pix", label: "Pix", count: 4 }] },
    ]);
    expect(dims.find((d) => d.id === "payment")?.options).toEqual([{ value: "pix", label: "Pix", count: 4 }]);
    expect(dims.every((d) => d.type === "multi-select")).toBe(true);
  });
});

describe("historyStatusClass", () => {
  it("traduz o tom do servidor em cor", () => {
    expect(historyStatusClass("danger")).toContain("destructive");
    expect(historyStatusClass("outro")).toContain("muted");
  });
});
