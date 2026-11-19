// WP-G10 (salto S3, "Agenda com cobertura"): o cabeçalho de cada dia da lista de
// Encomendas diz se a Produção cobre o que foi prometido, e o detalhe mostra, por
// produto, o prometido ao lado do planejado. As frases e as somas são do servidor; a
// tela decide o tom, o que a linha não repete e onde mora o atalho da Produção.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import {
  COVERAGE_READ_FAILED,
  COVERAGE_RETRY_LABEL,
  coverageByDate,
  coverageSignature,
  coverageToggleLabel,
  coverageTone,
  dayCoverage,
  PLANNED_CAPTION,
  productionLinkPlace,
  PROMISED_CAPTION,
  URGENT_WITHIN_DAYS,
} from "../app/presentation/preorderCoverage";
import {
  coveredDay,
  day,
  fromStock,
  madeToOrder,
  noBatch,
  product,
} from "./support/preorderCoverage";

describe("o tom do dia: só a falta e o dia sem lote ganham cor", () => {
  it("falta ou não tem lote para hoje ou amanhã: pede alguém agora", () => {
    expect(URGENT_WITHIN_DAYS).toBe(1);
    expect(coverageTone({ state: "short", days_ahead: 0 })).toBe("urgent");
    expect(coverageTone({ state: "short", days_ahead: 1 })).toBe("urgent");
    expect(coverageTone({ state: "no_batch", days_ahead: 1 })).toBe("urgent");
  });

  it("falta ou não tem lote para daqui a dias: aviso, ainda dá para planejar", () => {
    expect(coverageTone({ state: "short", days_ahead: 2 })).toBe("attention");
    expect(coverageTone({ state: "no_batch", days_ahead: 5 })).toBe("attention");
  });

  it("dia coberto e dia que não depende de lote ficam quietos, perto ou longe", () => {
    expect(coverageTone({ state: "covered", days_ahead: 0 })).toBe("quiet");
    expect(coverageTone({ state: "covered", days_ahead: 4 })).toBe("quiet");
    expect(coverageTone({ state: "not_batch_based", days_ahead: 0 })).toBe("quiet");
  });

  it("estado que a tela não conhece não vira falta", () => {
    expect(coverageTone({ state: "", days_ahead: 0 })).toBe("quiet");
    expect(coverageTone({ state: "outro", days_ahead: 0 })).toBe("quiet");
  });
});

describe("o cabeçalho do dia diz a frase do servidor", () => {
  it("a frase não é reescrita nem somada", () => {
    const view = dayCoverage(day());

    expect(view.date).toBe("2026-11-21");
    expect(view.headline).toBe("Faltam 6 Baguete de tradição. Sem lote para Ciabatta.");
    expect(view.tone).toBe("attention");
    expect(view.needsSomeone).toBe(true);
  });

  it("o dia coberto diz que cobre, sem pedir ninguém", () => {
    const view = dayCoverage(coveredDay());

    expect(view.headline).toBe("A produção cobre as encomendas.");
    expect(view.tone).toBe("quiet");
    expect(view.needsSomeone).toBe(false);
  });

  it("o dia que não depende de lote não mostra nada de falta", () => {
    const view = dayCoverage(
      day({
        state: "not_batch_based",
        days_ahead: 0,
        headline: "Nenhum item depende de lote.",
        products: [madeToOrder(), fromStock()],
      }),
    );

    expect(view.tone).toBe("quiet");
    expect(view.needsSomeone).toBe(false);
    expect(view.products.every((line) => line.tone === "quiet")).toBe(true);
    expect(view.products.every((line) => line.label === "")).toBe(true);
  });
});

describe("o detalhe do dia: o prometido ao lado do planejado", () => {
  const view = dayCoverage(day());
  const line = (sku: string) => view.products.find((p) => p.sku === sku)!;

  it("a ordem é a do servidor: primeiro quem pede alguém", () => {
    expect(view.products.map((p) => p.sku)).toEqual([
      "BAGUETE",
      "CIABATTA",
      "CAMPAGNE",
      "CAFE",
      "GELEIA",
    ]);
  });

  it("o produto que falta: os dois números e a frase do servidor", () => {
    expect(line("BAGUETE")).toMatchObject({
      name: "Baguete de tradição",
      promised: "16x",
      planned: "10x",
      label: "Faltam 6 Baguete de tradição",
      tone: "attention",
    });
  });

  it("a conta por extenso não repete os dois números que já estão lado a lado", () => {
    // "As encomendas somam 16x e os lotes, 10x." ao lado de "Prometido 16x" e
    // "Planejado 10x" diria a mesma coisa duas vezes.
    expect(line("BAGUETE").detail).toBe("");
    expect(line("CAMPAGNE").detail).toBe("");
  });

  it("sem lote: o zero planejado e o porquê", () => {
    expect(line("CIABATTA")).toMatchObject({
      promised: "8x",
      planned: "0x",
      label: "Sem lote para Ciabatta",
      detail: "Nenhum lote planejado para o dia.",
      tone: "attention",
    });
    const cancelled = dayCoverage(
      day({ products: [noBatch({ detail: "O lote do dia foi cancelado." })] }),
    );
    expect(cancelled.products[0]!.detail).toBe("O lote do dia foi cancelado.");
  });

  it("o coberto fica quieto: os números bastam", () => {
    expect(line("CAMPAGNE")).toMatchObject({
      promised: "4x",
      planned: "12x",
      label: "",
      tone: "quiet",
    });
  });

  it("feito na hora e revenda: sem planejado, sem cor de falta, com o porquê", () => {
    expect(line("CAFE")).toMatchObject({
      promised: "3x",
      planned: "",
      label: "",
      detail: "Feito na hora: não depende de lote.",
      tone: "quiet",
    });
    expect(line("GELEIA")).toMatchObject({
      promised: "2x",
      planned: "",
      detail: "Sai do estoque: a casa não produz este item.",
      tone: "quiet",
    });
  });

  it("quem pede alguém leva o tom do dia: amanhã é urgente", () => {
    const tomorrow = dayCoverage(day({ days_ahead: 1 }));

    expect(tomorrow.tone).toBe("urgent");
    expect(tomorrow.products.map((p) => p.tone)).toEqual([
      "urgent",
      "urgent",
      "quiet",
      "quiet",
      "quiet",
    ]);
  });

  it("por peso a quantidade vem escrita como a casa escreve", () => {
    const view = dayCoverage(
      day({
        headline: "Falta 0,35 kg de Brioche a granel.",
        products: [
          product({
            sku: "BRIOCHE-KG",
            name: "Brioche a granel",
            unit: "kg",
            promised_display: "1,35 kg",
            planned_display: "1 kg",
            label: "Falta 0,35 kg de Brioche a granel",
          }),
        ],
      }),
    );

    expect(view.products[0]).toMatchObject({ promised: "1,35 kg", planned: "1 kg" });
  });

  it("os nomes das duas colunas", () => {
    expect([PROMISED_CAPTION, PLANNED_CAPTION]).toEqual(["Prometido", "Planejado"]);
  });
});

describe("\"Abrir a Produção\" naquele dia", () => {
  it("o endereço e o nome vêm do servidor", () => {
    expect(dayCoverage(day()).production).toEqual({
      href: "https://producao.exemplo/plan?date=2026-11-21",
      label: "Abrir a Produção",
    });
  });

  it("sem endereço não há atalho", () => {
    const view = dayCoverage(day({ production_url: "", production_label: "" }));

    expect(view.production).toBeNull();
    expect(productionLinkPlace(view)).toBeNull();
  });

  it("no cabeçalho do dia que pede alguém; dentro do detalhe nos demais", () => {
    expect(productionLinkPlace(dayCoverage(day()))).toBe("header");
    expect(productionLinkPlace(dayCoverage(coveredDay()))).toBe("detail");
  });
});

describe("a cobertura casa com o grupo da lista pela data", () => {
  it("um dia por data", () => {
    const byDate = coverageByDate({ days: [coveredDay(), day()] });

    expect(Object.keys(byDate)).toEqual(["2026-11-19", "2026-11-21"]);
    expect(byDate["2026-11-21"]!.headline).toContain("Faltam 6");
  });

  it("sem leitura, vazio: o dia só não mostra a cobertura", () => {
    expect(coverageByDate(null)).toEqual({});
    expect(coverageByDate(undefined)).toEqual({});
    expect(coverageByDate({ days: [] })).toEqual({});
  });
});

describe("quando reler: o conjunto de encomendas da lista", () => {
  const card = (ref: string, commitment_date: string) => ({ ref, commitment_date });

  it("a ordem da fila não conta", () => {
    const a = [card("NB-1", "2026-11-19"), card("NB-2", "2026-11-21")];

    expect(coverageSignature(a)).toBe(coverageSignature([...a].reverse()));
  });

  it("entrou, saiu ou mudou de dia: é outro conjunto", () => {
    const base = coverageSignature([card("NB-1", "2026-11-19")]);

    expect(coverageSignature([card("NB-1", "2026-11-19"), card("NB-2", "2026-11-19")])).not.toBe(base);
    expect(coverageSignature([card("NB-2", "2026-11-19")])).not.toBe(base);
    expect(coverageSignature([card("NB-1", "2026-11-20")])).not.toBe(base);
  });

  it("sem encomenda, vazio: nada é lido", () => {
    expect(coverageSignature([])).toBe("");
  });
});

describe("a copy da tela", () => {
  it("o gesto que abre e fecha o detalhe", () => {
    expect(coverageToggleLabel(false)).toBe("Ver por produto");
    expect(coverageToggleLabel(true)).toBe("Recolher");
  });

  it("a falha de leitura diz o que não foi lido e oferece a saída", () => {
    expect(COVERAGE_READ_FAILED).toBe("Não foi possível ler se a produção cobre as encomendas.");
    expect(COVERAGE_RETRY_LABEL).toBe("Tentar de novo");
  });
});

describe("a página liga a cobertura à lista", () => {
  const page = readFileSync(new URL("../app/pages/index.vue", import.meta.url), "utf8");
  const list = readFileSync(new URL("../app/components/OrderPreorderList.vue", import.meta.url), "utf8");
  const header = readFileSync(new URL("../app/components/PreorderDayCoverage.vue", import.meta.url), "utf8");

  it("a leitura segue TODAS as encomendas da lista, sem os filtros da tela", () => {
    const wiring = page.slice(page.indexOf("usePreorderCoverage("), page.indexOf("usePreorderCoverage(") + 200);
    expect(wiring).toContain("coverageSignature(preorders.value.flatMap(");
    expect(wiring).not.toContain("triagedPreorders");
  });

  it("a falha não vira aviso solto: a saída mora na própria seção, com o pendente", () => {
    expect(list).not.toContain("<NuxtAlert");
    const retry = list.slice(list.indexOf("data-coverage-failed"), list.indexOf("data-coverage-retry") + 80);
    expect(retry).toContain(':loading="coverageReading"');
    expect(retry).toContain("emit('retry-coverage')");
    expect(page).toContain('@retry-coverage="retryPreorderCoverage"');
  });

  it("a frase do dia quebra linha, nunca corta", () => {
    expect(header).not.toMatch(/\btruncate\b|line-clamp|text-ellipsis|whitespace-nowrap/);
    expect(header).toContain("flex-wrap");
    // No celular a frase ganha a linha inteira.
    expect(header).toContain("basis-full");
  });

  it("o atalho da Produção abre na janela dela", () => {
    expect(header).toContain("useOperatorAppLink");
    expect(header.match(/:target="production\.attrs\.target"/g)).toHaveLength(2);
  });
});
