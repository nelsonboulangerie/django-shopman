import { describe, expect, it } from "vitest";
import type { ChangeHabitLike, ChangeMixLike, ForecastBasisLike } from "~/presentation/bi";
import {
  DATA_EPOCH,
  CONTEXT_EXAMPLES,
  EXPLORE_DIMENSION_LABELS,
  EXPLORE_EXAMPLES,
  aggregateBucket,
  availableExamples,
  WEEKDAY_LABELS,
  basisHeadline,
  basisNotes,
  bucketLabel,
  bucketSalesDays,
  cashOrdersNote,
  changeHabitNotes,
  changeMixCaveat,
  changeMixLabel,
  coinFloorHint,
  coverageLabel,
  delta,
  formatExploreValue,
  formatHours,
  formatMinutes,
  formatMoney,
  formatMoneyCompact,
  formatPercent,
  formatQty,
  hourLabel,
  missingLabel,
  rangeLabel,
  rangeText,
  resolveWindowRange,
  revpashHint,
  sensitivityHeadline,
  shortDate,
  shortDateWithYear,
  strikeMatrix,
  scenarioReportHeadline,
  scenarioStatusLabel,
  sourceConflictLabel,
  sourceLabel,
  sourcesCaption,
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

describe("aggregateBucket — a série longa não soma o que não se soma", () => {
  // ⚠️ Antes disto a página somava TUDO. Com "1 ano" + "Ticket médio" + "Tempo",
  // a barra da semana mostrava ~7× o ticket real — formatada como reais,
  // "R$ 178,50", perfeitamente convincente. Rendimento passava de 100%.
  const semana = [10000, 12000, 11000, 9000, 13000, 14000, 10500];

  it("soma o que é aditivo (faturamento, pedidos, quantidade)", () => {
    expect(aggregateBucket(semana, "sum")).toBe(79500);
  });

  it("tira a média do ticket médio, em vez de multiplicar por sete", () => {
    const media = aggregateBucket(semana, "mean");
    expect(media).toBeCloseTo(11357.14, 1);
    // A prova de que o bug morreu: a média fica na ordem de grandeza do DIA.
    expect(media).toBeLessThan(Math.max(...semana) * 1.01);
  });

  it("pega o maior no pico de salão, porque pico não acumula", () => {
    expect(aggregateBucket([4, 9, 6], "max")).toBe(9);
  });

  it("rendimento agregado não passa de 100%", () => {
    expect(aggregateBucket([98, 95, 101, 99], "mean")).toBeLessThan(101);
  });

  it("balde vazio é zero, e não NaN nem -Infinity", () => {
    expect(aggregateBucket([], "sum")).toBe(0);
    expect(aggregateBucket([], "mean")).toBe(0);
    expect(aggregateBucket([], "max")).toBe(0);
  });

  it("regra desconhecida cai em soma — o default que o servidor também usa", () => {
    expect(aggregateBucket([1, 2, 3], "qualquer-coisa")).toBe(6);
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

  // ── Troco ──────────────────────────────────────────────────────────────────

  const habit = (over: Partial<ChangeHabitLike> = {}): ChangeHabitLike => ({
    band: "interquartile",
    measured_days: 34,
    measured_orders: 1420,
    unmeasured_orders: 0,
    window_from: "2026-02-18",
    window_to: "2026-08-16",
    ...over,
  });

  const mix = (over: Partial<ChangeMixLike> = {}): ChangeMixLike => ({
    tendency: "mostly_coins",
    coin_value_percent: 18,
    small_change_percent: 82,
    sample_size: 1180,
    ...over,
  });

  // A tela pode falar de TENDÊNCIA e de valor; peça, nunca. Ninguém registra
  // moeda a moeda num balcão, e uma frase com contagem de peças faria a casa
  // conferir a gaveta contra um número que o sistema inventou.
  it("a denominação sai como tendência e o aviso vem junto", () => {
    expect(changeMixLabel(mix())).toBe("A maior parte sai em dinheiro miúdo, abaixo de R$ 5");
    expect(changeMixLabel(mix({ tendency: "mostly_notes" }))).toBe("A maior parte sai em notas");
    expect(changeMixLabel(mix({ tendency: "coisa_nova" }))).toBe(
      "Não dá para dizer como o troco se reparte",
    );
    expect(changeMixCaveat(mix())).toContain(
      "nunca quais moedas e notas saíram da gaveta",
    );
    expect(changeMixCaveat(mix({ sample_size: 1 }))).toContain("1 troco.");
  });

  it("o piso de moeda explica a aritmética antes da tendência", () => {
    expect(coinFloorHint(mix())).toBe(
      "Os centavos de um troco não fecham em nota, então essa parte sai sempre em moeda. " +
        "A maior parte sai em dinheiro miúdo, abaixo de R$ 5.",
    );
  });

  // Base curta e base confortável não podem sair com a mesma frase: a faixa
  // quer dizer coisas diferentes, e o gestor decide quanta folga levar.
  it("a base curta declara que a faixa mostra os extremos", () => {
    expect(changeHabitNotes(habit({ band: "full_range", measured_days: 12 }))[1]).toContain(
      "menor e o maior dia medido",
    );
    expect(changeHabitNotes(habit())[1]).toBe("Metade dos dias medidos ficou dentro dessa faixa.");
  });

  it("venda em dinheiro sem valor recebido aparece como buraco de medição", () => {
    expect(changeHabitNotes(habit())).toHaveLength(3);
    const notes = changeHabitNotes(habit({ unmeasured_orders: 1 }));
    expect(notes).toHaveLength(4);
    expect(notes[2]).toContain("1 venda em dinheiro ficou de fora");
    expect(notes[2]).toContain("Ausência de medição não é troco zero");
    expect(changeHabitNotes(habit({ unmeasured_orders: 9 }))[2]).toContain(
      "9 vendas em dinheiro ficaram de fora",
    );
  });

  // O limite que define a confiança tem de estar escrito na tela, e não só no
  // código: o histórico antigo conta as vendas em dinheiro, nunca o troco.
  it("a prestação de contas separa o que o histórico antigo sabe do que não sabe", () => {
    const notes = changeHabitNotes(habit());
    expect(notes[0]).toContain("1.420 vendas em dinheiro medidas em 34 dias");
    expect(notes[0]).toContain("entre 18/02 e 16/08");
    expect(notes[notes.length - 1]).toContain("nunca o troco");
  });

  it("o motivo de ausência do troco vira frase própria", () => {
    expect(missingLabel("troco_sem_base")).toContain("Ainda não sabemos");
    expect(missingLabel("sem_mix_de_pagamento")).toContain("pagou em dinheiro");
  });

  it("as vendas em dinheiro previstas saem com a fatia e o tamanho da amostra", () => {
    expect(cashOrdersNote(41.6, 34, 12)).toBe(
      "42 vendas em dinheiro prováveis: 34% do movimento do dia, que é a fatia dos 12 dias parecidos.",
    );
  });
});

describe("presentation/bi — perfis de consumo", () => {
  it("formata o percentual que a projection já arredondou", () => {
    expect(formatPercent(16.7)).toBe("16,7%");
    expect(formatPercent(50)).toBe("50%");
  });

  it("a faixa piso–teto vira texto, e faixa fechada vira ponto", () => {
    expect(rangeText({ min_orders: 1234, max_orders: 1500, min_share: 16.7, max_share: 20.1 })).toBe(
      "1.234–1.500 pedidos (16,7–20,1%)",
    );
    expect(rangeText({ min_orders: 7, max_orders: 7, min_share: 3.5, max_share: 3.5 })).toBe(
      "7 pedidos (3,5%)",
    );
    expect(rangeText({ min_orders: 1, max_orders: 1, min_share: 1, max_share: 1 })).toBe("1 pedido (1%)");
  });

  it("a sensibilidade diz quantos mudam, sem inventar quando não há base", () => {
    expect(sensitivityHeadline(0, 0, 0)).toBe("Sem pedidos de balcão no recorte.");
    expect(sensitivityHeadline(0, 0, 10)).toBe("Nenhum pedido muda de perfil entre piso e teto.");
    expect(sensitivityHeadline(1, 16.7, 6)).toBe(
      "1 pedido muda de perfil entre piso e teto (16,7% de 6).",
    );
  });

  it("a matriz dia × faixa nasce das células planas, na ordem das faixas", () => {
    const cells = [
      { weekday: 4, band: "lunch", orders: 10, with_beverage: 4, rate: 40 },
      { weekday: 4, band: "morning", orders: 5, with_beverage: 1, rate: 20 },
    ];
    const matrix = strikeMatrix(cells, ["morning", "lunch"]);
    expect(matrix).toHaveLength(7);
    expect(matrix[4]!.label).toBe("sex");
    expect(matrix[4]!.cells.map((c) => c?.rate ?? null)).toEqual([20, 40]);
    expect(matrix[0]!.cells).toEqual([null, null]);
  });

  it("o denominador do RevPASH fica à vista", () => {
    expect(revpashHint(24, 3, 26)).toBe("24 assentos × 3 h × 26 dias");
    expect(revpashHint(24, 2, 1)).toBe("24 assentos × 2 h × 1 dia");
  });
});

describe("presentation/bi — fontes", () => {
  it("nomeia a fonte para gente, e o que não é a casa é histórico", () => {
    expect(sourceLabel("shopman")).toBe("Shopman");
    expect(sourceLabel("yooga")).toBe("histórico Yooga");
    expect(sourceLabel("seed")).toBe("histórico de demonstração");
  });

  it("hora e dia da semana avisam quando somam histórico", () => {
    expect(sourcesCaption(["shopman"])).toBe("");
    expect(sourcesCaption(["shopman", "yooga"])).toBe(" · inclui histórico Yooga");
  });

  it("o dia em que o nativo apagou histórico vira frase com os dois números", () => {
    expect(
      sourceConflictLabel({ date: "2026-08-03", native_orders: 1, historical_dropped: 112, source: "yooga" }),
    ).toBe("03/08: 1 pedido nativo apagou 112 vendas do histórico Yooga nesse dia");
  });
});

describe("presentation/bi — cenários com IA", () => {
  const report = {
    generated_at: "2026-08-19T14:05:00-03:00",
    focus_label: "Vendas",
    window_from: "2026-07-23",
    window_to: "2026-08-19",
    status: "done",
    duration_ms: 11800,
    model: "claude-opus-5",
    scenarios: [{}, {}, {}],
  };

  it("o cabeçalho diz foco, quando e a janela que a IA viu", () => {
    expect(scenarioReportHeadline(report)).toMatch(/^Vendas · \d{2}\/\d{2} \d{2}:\d{2} · janela 23\/07–19\/08$/);
  });

  it("custo e latência ficam declarados; falha é falha, não cenário", () => {
    expect(scenarioStatusLabel(report)).toBe("3 cenários · 12 s · claude-opus-5");
    expect(scenarioStatusLabel({ ...report, status: "failed", scenarios: [] })).toContain("falhou");
  });
});
