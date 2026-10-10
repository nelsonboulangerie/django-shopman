import { describe, expect, it } from "vitest";
import {
  channelRows,
  hourPoints,
  revenueReading,
  revenueSeries,
  weekdayPoints,
} from "~/presentation/sales";

const day = (date: string, revenue_q: number, orders = 1) => ({
  date,
  orders,
  revenue_q,
  average_ticket_q: orders ? Math.round(revenue_q / orders) : 0,
  source: "shopman",
});

const previous = (revenue_by_day: number[]) => ({
  date_from: "2026-08-01",
  date_to: "2026-08-02",
  orders_total: 0,
  revenue_total_q: 0,
  average_ticket_q: 0,
  revenue_by_day,
});

describe("revenueReading", () => {
  it("põe o faturamento e o mesmo dia da comparação em cada ponto, por dia, em reais", () => {
    const out = revenueReading({
      days: [day("2026-09-01", 1000), day("2026-09-02", 2000)],
      previous: previous([500, 0]),
    });
    expect(out.span).toBe("dia");
    expect(out.points).toEqual([
      { label: "01/09", values: { revenue: 10, previous: 5 } },
      { label: "02/09", values: { revenue: 20, previous: 0 } },
    ]);
  });

  it("comparação que falta no fim conta zero, não some o ponto", () => {
    const out = revenueReading({ days: [day("2026-09-01", 1000)], previous: previous([]) });
    expect(out.points[0]?.values.previous).toBe(0);
  });

  it("janela longa diz o grão da semana", () => {
    const days = Array.from({ length: 200 }, (_, index) => {
      const date = new Date(Date.UTC(2026, 0, 5 + index)).toISOString().slice(0, 10);
      return day(date, 100);
    });
    expect(revenueReading({ days, previous: previous([]) }).span).toBe("semana");
  });
});

describe("revenueSeries", () => {
  it("a série de comparação leva o nome do recorte, com maiúscula", () => {
    expect(revenueSeries("mesmo período do ano passado").map((item) => item.label)).toEqual([
      "Faturamento",
      "Mesmo período do ano passado",
    ]);
  });
});

describe("pedidos por hora e por dia da semana", () => {
  it("rotula a hora", () => {
    expect(hourPoints([0, 3]).map((point) => point.label)).toEqual(["0h", "1h"]);
  });

  it("o dia em que a casa fecha diz isso no rótulo", () => {
    const out = weekdayPoints([1, 2, 3, 4, 5, 6, 0], [6]);
    expect(out[0]).toEqual({ label: "seg", values: { orders: 1 } });
    expect(out[6]).toEqual({ label: "dom, fechado", values: { orders: 0 } });
  });
});

describe("channelRows", () => {
  it("leva a parte do faturamento de cada canal", () => {
    const rows = channelRows({
      revenue_total_q: 1000,
      by_channel: [
        { channel_ref: "pdv", name: "PDV", kind: "pos", orders: 3, revenue_q: 750 },
        { channel_ref: "web", name: "Loja online", kind: "web", orders: 1, revenue_q: 250 },
      ],
    });
    expect(rows.map((row) => [row.ref, row.orders, row.share])).toEqual([
      ["pdv", 3, "75%"],
      ["web", 1, "25%"],
    ]);
    expect(rows[0]?.icon).toBeTruthy();
  });
});
