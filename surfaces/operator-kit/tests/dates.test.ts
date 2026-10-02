import { describe, expect, it } from "vitest";

import {
  calendarRange,
  customPeriod,
  dayLabel,
  goToDate,
  isCurrentPeriod,
  isoDate,
  otherDayCaption,
  periodLabel,
  quickDayOptions,
  resolvePeriod,
  stepPeriod,
  weekdayLong,
  withPreset,
  type PeriodSelection,
} from "../app/presentation/dates";

// 01/10/2026 é quinta-feira.
const TODAY = "2026-10-01";
const sel = (preset: string, from = "", to = ""): PeriodSelection => ({ preset, from, to });

describe("datas locais", () => {
  it("isoDate usa o fuso do dispositivo, nunca UTC", () => {
    // 23h de quinta em qualquer fuso continua sendo quinta.
    expect(isoDate(new Date(2026, 9, 1, 23, 30))).toBe("2026-10-01");
  });

  it("dayLabel diz sempre o dia da semana", () => {
    expect(dayLabel("2026-10-01", TODAY)).toBe("Hoje, qui 01/10");
    expect(dayLabel("2026-10-02", TODAY)).toBe("Amanhã, sex 02/10");
    expect(dayLabel("2026-09-30", TODAY)).toBe("Ontem, qua 30/09");
    expect(dayLabel("2026-09-29", TODAY)).toBe("Ter 29/09");
  });

  it("weekdayLong é por extenso", () => {
    expect(weekdayLong("2026-10-04")).toBe("Domingo");
    expect(weekdayLong("2026-10-05")).toBe("Segunda-feira");
    expect(weekdayLong("2026-10-03")).toBe("Sábado");
  });
});

describe("Tipo 1: quickDayOptions", () => {
  it("hoje, amanhã e a próxima data nominada", () => {
    const [today, tomorrow, next] = quickDayOptions({ today: TODAY, min: TODAY });
    expect([today!.title, today!.caption]).toEqual(["Hoje", "Qui 01/10"]);
    expect([tomorrow!.title, tomorrow!.caption]).toEqual(["Amanhã", "Sex 02/10"]);
    expect([next!.title, next!.caption, next!.iso]).toEqual(["Sábado", "03/10", "2026-10-03"]);
    expect([today, tomorrow, next].every((option) => option!.reason === "")).toBe(true);
  });

  it("dia fechado aparece apagado com o motivo, e a próxima pula o fechado", () => {
    // Sexta 02, sábado 03 e domingo 04 fechados; segunda 05 aberta.
    const open = ["2026-10-01", "2026-10-05", "2026-10-06"];
    const [, tomorrow, next] = quickDayOptions({ today: TODAY, availableDates: open });
    expect(tomorrow!.reason).toBe("fechado");
    expect(tomorrow!.caption).toBe("Sex 02/10 · fechado");
    expect(next!.iso).toBe("2026-10-05");
    expect(next!.title).toBe("Segunda-feira");
  });

  it("depois da última data da lista, quem decide é o servidor", () => {
    const [, , next] = quickDayOptions({ today: TODAY, availableDates: ["2026-10-01"] });
    expect(next!.iso).toBe("2026-10-03");
    expect(next!.reason).toBe("");
  });

  it("respeita min e max", () => {
    const [today, tomorrow, next] = quickDayOptions({ today: TODAY, min: "2026-10-02", max: "2026-10-02" });
    expect(today!.reason).toBe("indisponível");
    expect(tomorrow!.reason).toBe("");
    expect(next!.reason).toBe("fora do prazo");
    expect(next!.caption).toBe("03/10 · fora do prazo");
  });

  it("Outra data mostra a data escolhida fora dos três atalhos", () => {
    const options = quickDayOptions({ today: TODAY });
    expect(otherDayCaption("", options)).toBe("No calendário");
    expect(otherDayCaption("2026-10-02", options)).toBe("No calendário");
    expect(otherDayCaption("2026-10-14", options)).toBe("Qua 14/10");
  });
});

describe("Tipo 2: período", () => {
  const bi = { today: TODAY, max: TODAY, epoch: "2024-01-01" };

  it("calendário corre do início até hoje quando max é hoje (comportamento do B.I.)", () => {
    expect(resolvePeriod(sel("day"), bi)).toEqual({ date_from: TODAY, date_to: TODAY });
    expect(resolvePeriod(sel("week"), bi)).toEqual({ date_from: "2026-09-28", date_to: TODAY });
    expect(resolvePeriod(sel("month"), bi)).toEqual({ date_from: "2026-10-01", date_to: TODAY });
    expect(resolvePeriod(sel("year"), bi)).toEqual({ date_from: "2026-01-01", date_to: TODAY });
  });

  it("janelas móveis, Máx e personalizado", () => {
    expect(resolvePeriod(sel("7d"), bi)).toEqual({ date_from: "2026-09-25", date_to: TODAY });
    expect(resolvePeriod(sel("max"), bi)).toEqual({ date_from: "2024-01-01", date_to: TODAY });
    expect(resolvePeriod(sel("custom", "2025-01-10", "2025-02-10"), bi)).toEqual({
      date_from: "2025-01-10",
      date_to: "2025-02-10",
    });
  });

  it("sem max, a semana é de segunda a domingo (quadros)", () => {
    expect(resolvePeriod(sel("week"), { today: TODAY })).toEqual({ date_from: "2026-09-28", date_to: "2026-10-04" });
    expect(calendarRange("month", "2026-02-10")).toEqual({ date_from: "2026-02-01", date_to: "2026-02-28" });
  });

  it("‹ anda um período igual: dia, semana, mês, ano", () => {
    expect(stepPeriod(sel("day"), -1, bi)).toEqual(sel("day", "2026-09-30"));
    const lastWeek = stepPeriod(sel("week"), -1, bi)!;
    expect(resolvePeriod(lastWeek, bi)).toEqual({ date_from: "2026-09-21", date_to: "2026-09-27" });
    const lastMonth = stepPeriod(sel("month"), -1, bi)!;
    expect(resolvePeriod(lastMonth, bi)).toEqual({ date_from: "2026-09-01", date_to: "2026-09-30" });
    const lastYear = stepPeriod(sel("year"), -1, bi)!;
    expect(resolvePeriod(lastYear, bi)).toEqual({ date_from: "2025-01-01", date_to: "2025-12-31" });
  });

  it("‹ numa janela de N dias recua N dias; voltando a hoje, a janela volta a acompanhar a virada", () => {
    const back = stepPeriod(sel("7d"), -1, bi)!;
    expect(resolvePeriod(back, bi)).toEqual({ date_from: "2026-09-18", date_to: "2026-09-24" });
    expect(stepPeriod(back, 1, bi)).toEqual(sel("7d"));
    const custom = customPeriod("2026-09-10", "2026-09-14");
    expect(stepPeriod(custom, -1, bi)).toEqual(sel("custom", "2026-09-05", "2026-09-09"));
  });

  it("› não passa de max; Máx não anda", () => {
    expect(stepPeriod(sel("day"), 1, bi)).toBeNull();
    expect(stepPeriod(sel("week"), 1, bi)).toBeNull();
    expect(stepPeriod(sel("7d"), 1, bi)).toBeNull();
    expect(stepPeriod(sel("max"), -1, bi)).toBeNull();
    // Sem max (quadros), o futuro é o assunto.
    expect(stepPeriod(sel("day"), 1, { today: TODAY })).toEqual(sel("day", "2026-10-02"));
  });

  it("voltar ao período de hoje limpa a âncora", () => {
    expect(stepPeriod(sel("day", "2026-09-30"), 1, bi)).toEqual(sel("day"));
    expect(isCurrentPeriod(sel("day"))).toBe(true);
    expect(isCurrentPeriod(sel("day", "2026-09-30"))).toBe(false);
    expect(isCurrentPeriod(customPeriod(TODAY, TODAY))).toBe(false);
  });

  it("trocar de granularidade guarda a âncora; ir para um dia mantém a granularidade", () => {
    expect(withPreset(sel("day", "2026-09-24"), "week", bi)).toEqual(sel("week", "2026-09-24"));
    expect(withPreset(sel("day", "2026-09-30"), "week", bi)).toEqual(sel("week"));
    expect(withPreset(sel("day", "2026-09-24"), "28d", bi)).toEqual(sel("28d"));
    expect(goToDate(sel("week"), "2026-10-20", { today: TODAY })).toEqual(sel("week", "2026-10-20"));
  });

  it("o rótulo diz o dia da semana e o intervalo, sem travessão", () => {
    expect(periodLabel(sel("day"), resolvePeriod(sel("day"), bi), TODAY)).toBe("Hoje, qui 01/10");
    expect(periodLabel(sel("28d"), resolvePeriod(sel("28d"), bi), TODAY)).toBe("28D · 04/09 a 01/10");
    expect(periodLabel(sel("week"), resolvePeriod(sel("week"), { today: TODAY }), TODAY)).toBe(
      "Semana · 28/09 a 04/10",
    );
    const label = periodLabel(sel("custom", "2026-09-01", "2026-09-05"), { date_from: "2026-09-01", date_to: "2026-09-05" }, TODAY);
    expect(label).toBe("Personalizado · 01/09 a 05/09");
    expect(label).not.toMatch(/[–—]/);
  });
});
