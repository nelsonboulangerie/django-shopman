import { describe, expect, it } from "vitest";
import type { ForecastBasisLike } from "~/presentation/bi";
import {
  DATA_EPOCH,
  CONTEXT_EXAMPLES,
  EXPLORE_DIMENSION_LABELS,
  EXPLORE_EXAMPLES,
  availableExamples,
  WEEKDAY_LABELS,
  basisHeadline,
  basisNotes,
  bucketLabel,
  bucketSalesDays,
  coverageLabel,
  delta,
  formatExploreValue,
  formatHours,
  formatMinutes,
  formatMoney,
  formatMoneyCompact,
  formatQty,
  hourLabel,
  missingLabel,
  rangeLabel,
  resolveWindowRange,
  shortDate,
  shortDateWithYear,
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

  it("horas sem produto saem legíveis, e zero é resposta", () => {
    expect(formatHours(7)).toBe("7 h");
    expect(formatHours(1.53)).toBe("1,5 h");
    expect(formatHours(0)).toBe("0 h");
    expect(formatExploreValue("hours", 7)).toBe("7 h");
  });

  it("cenários de exemplo só usam a gramática existente", () => {
    // Exemplo com dimensão inventada quebraria na primeira abertura da tela.
    for (const example of EXPLORE_EXAMPLES) {
      expect(EXPLORE_DIMENSION_LABELS[example.config.by]).toBeTruthy();
      if (example.config.by2) {
        expect(EXPLORE_DIMENSION_LABELS[example.config.by2]).toBeTruthy();
      }
    }
  });

  it("a curadoria abre pela pergunta do dia: falta ou sobra", () => {
    expect(EXPLORE_EXAMPLES[0]?.config.metric).toBe("soldout_days");
  });

  it("cenário de contexto só aparece quando o servidor tem o dado", () => {
    // Sem clima nem calendário injetados, a gramática não oferece as dimensões
    // — e um chip que abriria vazio não deve existir na tela.
    const semContexto = availableExamples(["sku", "time", "weekday"]);
    expect(semContexto).toHaveLength(EXPLORE_EXAMPLES.length);

    const comClima = availableExamples(["sku", "time", "temperature"]);
    expect(comClima.length).toBeGreaterThan(EXPLORE_EXAMPLES.length);
    expect(comClima.some((e) => e.config.by === "temperature")).toBe(true);
    // Feriado segue fora: cada bloco de contexto entra por conta própria.
    expect(comClima.some((e) => e.config.by === "day_kind")).toBe(false);
  });

  it("todo cenário de contexto usa dimensão rotulada", () => {
    for (const example of CONTEXT_EXAMPLES) {
      expect(EXPLORE_DIMENSION_LABELS[example.config.by]).toBeTruthy();
    }
  });

  it("datas curtas e rótulos", () => {
    expect(shortDate("2026-08-14")).toBe("14/08");
    expect(hourLabel(5)).toBe("5h");
    expect(WEEKDAY_LABELS[0]).toBe("seg");
  });

  it("cobertura sempre carrega o denominador", () => {
    expect(coverageLabel(3, 12)).toBe("3 de 12 fornadas medidas");
    expect(coverageLabel(0, 0)).toBe("Sem fornadas no período");
  });

  it("delta honesto: sem base vira travessão; tom segue melhorou/piorou", () => {
    expect(delta(100, 0)).toEqual({ text: "—", tone: "neutral" });
    expect(delta(120, 100)).toEqual({ text: "▲ 20% vs Período anterior", tone: "positive" });
    expect(delta(80, 100)).toEqual({ text: "▼ 20% vs Período anterior", tone: "negative" });
    expect(delta(100, 100)).toEqual({ text: "Estável vs Período anterior", tone: "neutral" });
    // Perda subindo é RUIM: downIsGood inverte o tom, nunca o texto.
    expect(delta(120, 100, { downIsGood: true }).tone).toBe("negative");
    expect(delta(80, 100, { downIsGood: true }).tone).toBe("positive");
  });
});

describe("bucketSalesDays", () => {
  const day = (date: string, revenue: number, source = "shopman", orders = 1) => ({
    date, orders: revenue ? orders : 0, revenue_q: revenue, source,
  });

  it("janela curta fica diária", () => {
    const out = bucketSalesDays([day("2026-08-13", 100), day("2026-08-14", 200)]);
    expect(out).toHaveLength(2);
    expect(out[0]!.span).toBe("day");
  });

  it("janela longa agrega por semana começando na segunda", () => {
    const days = Array.from({ length: 130 }, (_, index) => {
      const d = new Date(Date.UTC(2026, 0, 1 + index));
      return day(d.toISOString().slice(0, 10), 100, "yooga");
    });
    const out = bucketSalesDays(days);
    expect(out.length).toBeLessThan(25);
    expect(out[0]!.span).toBe("week");
    expect(out.reduce((sum, bucket) => sum + bucket.revenue_q, 0)).toBe(13000);
    // 2026-01-01 é quinta: o primeiro balde ancora na segunda anterior.
    expect(out[0]!.date).toBe("2025-12-29");
  });

  it("acima de ~2 anos agrega por mês, com rótulo de mês", () => {
    const days = Array.from({ length: 800 }, (_, index) => {
      const d = new Date(Date.UTC(2024, 6, 1 + index));
      return day(d.toISOString().slice(0, 10), 100, "yooga");
    });
    const out = bucketSalesDays(days);
    expect(out[0]!.span).toBe("month");
    expect(out[0]!.date).toBe("2024-07-01");
    expect(bucketLabel(out[0]!.date, out[0]!.span)).toBe("jul/24");
    expect(out.reduce((sum, bucket) => sum + bucket.revenue_q, 0)).toBe(80000);
  });

  it("resolveWindowRange: janelas móveis, Máx e personalizado", () => {
    const today = new Date("2026-08-14T12:00:00Z");
    expect(resolveWindowRange({ preset: "7d", from: "", to: "" }, today)).toEqual({
      date_from: "2026-08-08",
      date_to: "2026-08-14",
    });
    expect(resolveWindowRange({ preset: "max", from: "", to: "" }, today).date_from).toBe(
      DATA_EPOCH,
    );
    expect(
      resolveWindowRange({ preset: "custom", from: "2025-01-10", to: "2025-02-10" }, today),
    ).toEqual({ date_from: "2025-01-10", date_to: "2025-02-10" });
  });

  it("resolveWindowRange: períodos do calendário correm do início até hoje", () => {
    const friday = new Date("2026-08-14T12:00:00Z");
    expect(resolveWindowRange({ preset: "day", from: "", to: "" }, friday)).toEqual({
      date_from: "2026-08-14",
      date_to: "2026-08-14",
    });
    // Semana começa na segunda: sexta 14/08 → segunda 10/08.
    expect(resolveWindowRange({ preset: "week", from: "", to: "" }, friday).date_from).toBe(
      "2026-08-10",
    );
    expect(resolveWindowRange({ preset: "month", from: "", to: "" }, friday).date_from).toBe(
      "2026-08-01",
    );
    expect(resolveWindowRange({ preset: "year", from: "", to: "" }, friday).date_from).toBe(
      "2026-01-01",
    );
  });

  it("semana mista veste a fonte nativa; semana só-histórico fica yooga", () => {
    const days = Array.from({ length: 130 }, (_, index) => {
      const d = new Date(Date.UTC(2026, 0, 5 + index)); // 05/01 é segunda
      return day(d.toISOString().slice(0, 10), 100, index < 7 ? "yooga" : index < 14 ? "shopman" : "yooga");
    });
    const out = bucketSalesDays(days);
    expect(out[0]!.source).toBe("yooga");
    expect(out[1]!.source).toBe("shopman");
  });
});

describe("presentation/bi — projeção", () => {
  const basis = (over: Partial<ForecastBasisLike> = {}): ForecastBasisLike => ({
    sample_size: 14,
    applied: ["weekday", "day_kind"],
    relaxed: [],
    unavailable: [],
    window_from: "2024-08-01",
    window_to: "2026-08-15",
    excluded_closed: 0,
    excluded_disrupted: 0,
    without_sales: 0,
    level_days: 28,
    ...over,
  });

  // A concordância é o risco real aqui: em pt-BR os dias em "-feira" são
  // femininos e flexionam as duas partes no plural. Errar o gênero num número
  // que o padeiro usa para decidir a fornada tira a autoridade do número.
  it("a manchete da base concorda com o dia da semana", () => {
    expect(basisHeadline(basis(), "quarta-feira")).toBe(
      "14 quartas-feiras parecidas, casadas por dia da semana e tipo de dia.",
    );
    expect(basisHeadline(basis({ sample_size: 9 }), "sábado")).toBe(
      "9 sábados parecidos, casados por dia da semana e tipo de dia.",
    );
  });

  it("amostra de um dia fica no singular, e sem critério não inventa oração", () => {
    expect(basisHeadline(basis({ sample_size: 1, applied: ["weekday"] }), "sexta-feira")).toBe(
      "1 sexta-feira parecida, casada por dia da semana.",
    );
    expect(basisHeadline(basis({ sample_size: 1 }), "domingo")).toBe(
      "1 domingo parecido, casado por dia da semana e tipo de dia.",
    );
    expect(basisHeadline(basis({ applied: [] }), "terça-feira")).toBe(
      "14 terças-feiras parecidas.",
    );
  });

  it("três critérios saem com vírgula e 'e' no último", () => {
    expect(basisHeadline(basis({ applied: ["weekday", "day_kind", "season"] }), "quinta-feira")).toBe(
      "14 quintas-feiras parecidas, casadas por dia da semana, tipo de dia e estação.",
    );
  });

  // Afrouxado ≠ indisponível: o primeiro é escolha do cálculo diante de amostra
  // curta, o segundo é dado que a casa não tem. Fundir os dois faria a tela
  // culpar o cálculo por uma ausência de dado, e ninguém saberia o que carregar.
  it("cada ressalva da base é dita por inteiro, e o patamar sempre aparece", () => {
    expect(basisNotes(basis())).toEqual([
      "O patamar aplicado é o movimento típico de agora, medido em 28 dias.",
    ]);
    expect(
      basisNotes(
        basis({
          relaxed: ["season"],
          unavailable: ["temperature"],
          without_sales: 1,
          excluded_closed: 3,
          excluded_disrupted: 2,
        }),
      ),
    ).toEqual([
      "Ignoramos estação: com esse recorte sobravam poucos dias.",
      "Não sabemos temperatura do dia perguntado, então esse recorte não entrou no casamento.",
      "1 dia parecido sem venda registrada ficou de fora: ausência não é zero.",
      "3 dias em que a casa não abriu ficaram de fora.",
      "2 dias atrapalhados por episódio ficaram de fora.",
      "O patamar aplicado é o movimento típico de agora, medido em 28 dias.",
    ]);
  });

  // Motivo desconhecido não pode virar tela em branco: sem base, a página
  // precisa dizer que não sabe, e não deixar o gestor achar que o número sumiu.
  it("motivo de ausência vira frase, inclusive o motivo que não conhecemos", () => {
    expect(missingLabel("amostra_insuficiente")).toBe(
      "Não temos dias parecidos o bastante para dizer.",
    );
    expect(missingLabel("motivo_que_nao_existe")).toBe("Não temos base para projetar este dia.");
  });

  it("a faixa e a data com ano saem no formato da casa", () => {
    expect(rangeLabel(124000, 168000).replace(/ /g, " ")).toBe("R$ 1,2 mil a R$ 1,7 mil");
    expect(shortDateWithYear("2025-05-11")).toBe("11/05/2025");
  });
});
