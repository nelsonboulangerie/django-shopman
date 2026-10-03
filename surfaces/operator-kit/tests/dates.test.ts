import { describe, expect, it } from "vitest";

import {
  calendarRange,
  customPeriod,
  customPeriodError,
  dayLabel,
  goToDate,
  isCurrentPeriod,
  isoDate,
  otherDayCaption,
  periodAnchor,
  periodLabel,
  periodFromQuery,
  periodOfDay,
  periodToQuery,
  PAST_PERIOD_PRESETS,
  quickDayOptions,
  resolvePeriod,
  STORE_TIME_ZONE,
  stepPeriod,
  todayIso,
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

  it("a ponte dos quadros: um dia vira seleção e volta", () => {
    expect(periodOfDay("day", "", TODAY)).toEqual(sel("day"));
    expect(periodOfDay("day", TODAY, TODAY)).toEqual(sel("day"));
    expect(periodOfDay("day", "2026-10-02", TODAY)).toEqual(sel("day", "2026-10-02"));
    // Um dia qualquer da semana de hoje é a semana de hoje.
    expect(periodOfDay("week", "2026-10-03", TODAY)).toEqual(sel("week"));
    expect(periodAnchor(sel("day"), TODAY)).toBe(TODAY);
    expect(periodAnchor(sel("week", "2026-10-07"), TODAY)).toBe("2026-10-07");
  });

  it("o rótulo diz o dia da semana e o intervalo, sem travessão", () => {
    expect(periodLabel(sel("day"), resolvePeriod(sel("day"), bi), TODAY)).toBe("Hoje, qui 01/10");
    expect(periodLabel(sel("28d"), resolvePeriod(sel("28d"), bi), TODAY)).toBe("Últimos 28 dias · 04/09 a 01/10");
    expect(periodLabel(sel("week"), resolvePeriod(sel("week"), { today: TODAY }), TODAY)).toBe(
      "Semana · 28/09 a 04/10",
    );
    const label = periodLabel(sel("custom", "2026-09-01", "2026-09-05"), { date_from: "2026-09-01", date_to: "2026-09-05" }, TODAY);
    expect(label).toBe("Personalizado · 01/09 a 05/09");
    expect(label).not.toMatch(/[–—]/);
  });
});

describe("Tipo 2: o período universal (Período, Próximos, Últimos, Personalizado)", () => {
  const board = { today: TODAY };

  it("Próximos N dias começam hoje e acompanham a virada", () => {
    expect(resolvePeriod(sel("next7d"), board)).toEqual({ date_from: TODAY, date_to: "2026-10-07" });
    expect(resolvePeriod(sel("next28d"), board)).toEqual({ date_from: TODAY, date_to: "2026-10-28" });
    expect(isCurrentPeriod(sel("next7d"))).toBe(true);
    expect(periodLabel(sel("next7d"), resolvePeriod(sel("next7d"), board), TODAY)).toBe(
      "Próximos 7 dias · 01/10 a 07/10",
    );
  });

  it("› nos Próximos anda N dias; ‹ volta até hoje e para ali", () => {
    const later = stepPeriod(sel("next7d"), 1, board)!;
    expect(later).toEqual(sel("next7d", "2026-10-08"));
    expect(resolvePeriod(later, board)).toEqual({ date_from: "2026-10-08", date_to: "2026-10-14" });
    expect(stepPeriod(later, -1, board)).toEqual(sel("next7d"));
    expect(stepPeriod(sel("next7d"), -1, board)).toBeNull();
    // Com max, o passo que sairia dele não existe.
    expect(stepPeriod(sel("next7d"), 1, { today: TODAY, max: "2026-10-05" })).toBeNull();
  });

  it("trocar para uma janela recomeça em hoje; voltar ao Dia guarda a âncora", () => {
    expect(withPreset(sel("week", "2026-10-20"), "next7d", board)).toEqual(sel("next7d"));
    expect(withPreset(sel("next7d", "2026-10-08"), "day", board)).toEqual(sel("day", "2026-10-08"));
    expect(periodAnchor(sel("next7d", "2026-10-08"), TODAY)).toBe("2026-10-08");
  });

  it("o B.I. continua com tudo o que tinha, e só olha para trás", () => {
    expect(PAST_PERIOD_PRESETS).toEqual(["day", "week", "month", "year", "7d", "28d", "3m", "6m", "1y", "5y", "max"]);
    expect(PAST_PERIOD_PRESETS.some((key) => key.startsWith("next"))).toBe(false);
  });

  it("a semana começa na segunda, inclusive vista do domingo", () => {
    // Domingo 04/10 ainda é a semana de segunda 28/09.
    expect(calendarRange("week", "2026-10-04")).toEqual({ date_from: "2026-09-28", date_to: "2026-10-04" });
    // Segunda 05/10 abre a semana seguinte.
    expect(calendarRange("week", "2026-10-05")).toEqual({ date_from: "2026-10-05", date_to: "2026-10-11" });
    // A semana que atravessa o mês e o ano.
    expect(calendarRange("week", "2026-12-31")).toEqual({ date_from: "2026-12-28", date_to: "2027-01-03" });
  });

  it("virada de mês e de ano: o mês tem o tamanho dele, e ‹ › nunca pulam um mês", () => {
    expect(calendarRange("month", "2028-02-15")).toEqual({ date_from: "2028-02-01", date_to: "2028-02-29" });
    // De 31/01, o mês seguinte é fevereiro (e não 03/03, como `setMonth` daria).
    const jan31 = { today: "2027-01-31" };
    const feb = stepPeriod(sel("month"), 1, jan31)!;
    expect(resolvePeriod(feb, jan31)).toEqual({ date_from: "2027-02-01", date_to: "2027-02-28" });
    const dec = stepPeriod(sel("month"), -1, jan31)!;
    expect(resolvePeriod(dec, jan31)).toEqual({ date_from: "2026-12-01", date_to: "2026-12-31" });
    // Os últimos 7 dias atravessam a virada do mês.
    expect(resolvePeriod(sel("7d"), { today: "2026-10-03" })).toEqual({ date_from: "2026-09-27", date_to: "2026-10-03" });
    // Os próximos 7 dias também.
    expect(resolvePeriod(sel("next7d"), { today: "2026-10-29" })).toEqual({ date_from: "2026-10-29", date_to: "2026-11-04" });
  });

  it("o hoje da loja é o de America/Sao_Paulo, qualquer que seja o fuso do dispositivo", () => {
    // 23h30 de quinta em Londrina = 02h30 de sexta em UTC.
    const lateThursday = new Date(Date.UTC(2026, 9, 2, 2, 30));
    expect(todayIso(lateThursday, STORE_TIME_ZONE)).toBe("2026-10-01");
    expect(todayIso(lateThursday, "UTC")).toBe("2026-10-02");
    // Meia-noite e meia em Londrina já é o dia seguinte.
    expect(todayIso(new Date(Date.UTC(2026, 9, 2, 3, 30)), STORE_TIME_ZONE)).toBe("2026-10-02");
    // Virada do mês e do ano.
    expect(todayIso(new Date(Date.UTC(2027, 0, 1, 2, 0)), STORE_TIME_ZONE)).toBe("2026-12-31");
  });

  it("o personalizado diz por que não aplica, em vez de o servidor cortar em silêncio", () => {
    expect(customPeriodError("2026-10-01", "2026-10-31", { maxSpanDays: 62 })).toBe("");
    expect(customPeriodError("2026-10-01", "2026-12-31", { maxSpanDays: 62 })).toBe("No máximo 62 dias por vez.");
    expect(customPeriodError("2026-09-01", "2026-10-05", { max: TODAY })).toBe("A última data possível é 01/10.");
    expect(customPeriodError("2023-12-01", "2024-01-05", { min: "2024-01-01" })).toBe("A primeira data possível é 01/01.");
    expect(customPeriodError("", "2026-10-05", {})).toBe("Escolha as duas datas.");
    // Datas invertidas valem (o controle troca).
    expect(customPeriodError("2026-10-10", "2026-10-01", { maxSpanDays: 62 })).toBe("");
  });

  describe("na URL", () => {
    const options = {
      presets: ["day", "week", "next7d", "7d"],
      custom: true,
      fallback: sel("week"),
    };

    it("o padrão não ocupa a URL; o resto vai e volta igual", () => {
      expect(periodToQuery(sel("week"), options.fallback)).toEqual({});
      const cases = [
        sel("day", "2026-10-08"),
        sel("week", "2026-10-20"),
        sel("next7d"),
        sel("next7d", "2026-10-08"),
        sel("7d", "", "2026-09-20"),
        sel("custom", "2026-10-01", "2026-10-15"),
      ];
      for (const selection of cases) {
        expect(periodFromQuery(periodToQuery(selection, options.fallback), options)).toEqual(selection);
      }
      expect(periodToQuery(sel("custom", "2026-10-01", "2026-10-15"), options.fallback)).toEqual({
        period: "custom",
        from: "2026-10-01",
        to: "2026-10-15",
      });
    });

    it("o que o consumidor não aceita, ou não se lê, cai no padrão", () => {
      expect(periodFromQuery({}, options)).toEqual(sel("week"));
      expect(periodFromQuery({ period: "year" }, options)).toEqual(sel("week"));
      expect(periodFromQuery({ period: "mes" }, options)).toEqual(sel("week"));
      expect(periodFromQuery({ period: "custom", from: "2026-10-01" }, options)).toEqual(sel("week"));
      expect(periodFromQuery({ period: "custom", from: "2026-10-01", to: "2026-10-05" }, { ...options, custom: false })).toEqual(
        sel("week"),
      );
      expect(periodFromQuery({ period: "day", from: "ontem" }, options)).toEqual(sel("day"));
      // Personalizado invertido na URL é trocado.
      expect(periodFromQuery({ period: "custom", from: "2026-10-15", to: "2026-10-01" }, options)).toEqual(
        sel("custom", "2026-10-01", "2026-10-15"),
      );
    });
  });
});
