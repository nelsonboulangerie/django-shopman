import { describe, expect, it } from "vitest";

import {
  QUEUE_COLLAPSE_PX,
  QUEUE_COLUMN_MIN_PX,
  allQueueColumnsOpen,
  defaultQueueLayout,
  isDefaultQueueLayout,
  nextOpenQueueKey,
  normalizeQueueLayout,
  openQueueColumn,
  queueColumnForKey,
  queueGridTemplate,
  queueStripLabel,
  resizeQueueColumns,
  showAllQueueColumns,
  toggleQueueColumn,
  isOnlyQueueColumn,
  onlyQueueColumn,
} from "../app/presentation/queueColumns";

const KEYS = ["intake", "prep", "expedition"] as const;

describe("colunas de fila: arrumação padrão e higiene", () => {
  it("quem nunca mexeu vê todas abertas, em partes iguais", () => {
    const layout = defaultQueueLayout(KEYS);
    expect(isDefaultQueueLayout(layout, KEYS)).toBe(true);
    expect(queueGridTemplate(layout, KEYS)).toBe("minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr)");
  });

  it("guardado estranho é higienizado: coluna nova entra aberta, peso volta para a faixa, lixo some", () => {
    const layout = normalizeQueueLayout(KEYS, {
      intake: { open: false, weight: 99 },
      prep: { open: "sim", weight: -3 },
      sumida: { open: true, weight: 1 },
    });
    expect(layout).toEqual({
      intake: { open: false, weight: 4 },
      prep: { open: true, weight: 0.25 },
      expedition: { open: true, weight: 1 },
    });
  });

  it("nunca sai uma tela com todas recolhidas", () => {
    const fechadas = Object.fromEntries(KEYS.map((key) => [key, { open: false, weight: 1 }]));
    expect(allQueueColumnsOpen(normalizeQueueLayout(KEYS, fechadas), KEYS)).toBe(true);
    expect(normalizeQueueLayout(KEYS, null)).toEqual(defaultQueueLayout(KEYS));
  });
});

describe("recolher e abrir", () => {
  it("posto Saída: Entrada e Preparo recolhidas viram faixas de 56 px", () => {
    let layout = defaultQueueLayout(KEYS);
    layout = toggleQueueColumn(layout, KEYS, "intake");
    layout = toggleQueueColumn(layout, KEYS, "prep");
    expect(queueGridTemplate(layout, KEYS)).toBe("56px 56px minmax(0, 1fr)");
  });

  it("recolher a última aberta não faz nada", () => {
    let layout = toggleQueueColumn(defaultQueueLayout(KEYS), KEYS, "intake");
    layout = toggleQueueColumn(layout, KEYS, "prep");
    expect(toggleQueueColumn(layout, KEYS, "expedition")).toBe(layout);
  });

  it("tocar na faixa abre; abrir a aberta não muda nada", () => {
    const fechada = toggleQueueColumn(defaultQueueLayout(KEYS), KEYS, "prep");
    expect(openQueueColumn(fechada, "prep").prep!.open).toBe(true);
    const aberta = defaultQueueLayout(KEYS);
    expect(openQueueColumn(aberta, "prep")).toBe(aberta);
  });

  it("Mostrar as 3 colunas volta ao padrão, larguras inclusive", () => {
    expect(isDefaultQueueLayout(showAllQueueColumns(KEYS), KEYS)).toBe(true);
  });

  it("teclas 1, 2 e 3 apontam as colunas pela posição; outras teclas, nada", () => {
    expect(queueColumnForKey("1", KEYS)).toBe("intake");
    expect(queueColumnForKey("3", KEYS)).toBe("expedition");
    expect(queueColumnForKey("4", KEYS)).toBeNull();
    expect(queueColumnForKey("0", KEYS)).toBeNull();
    expect(queueColumnForKey("r", KEYS)).toBeNull();
  });
});

describe("arrastar a alça", () => {
  const base = defaultQueueLayout(KEYS);
  const pair = { left: "intake", right: "prep", leftPx: 400, rightPx: 400 };

  it("o que uma ganha a outra perde; a terceira fica onde estava", () => {
    const layout = resizeQueueColumns(base, KEYS, { ...pair, deltaPx: 100, final: true });
    expect(layout.intake!.weight).toBe(1.25);
    expect(layout.prep!.weight).toBe(0.75);
    expect(layout.expedition).toEqual(base.expedition);
  });

  it("durante o arraste nenhuma fica mais estreita que o mínimo, e nada recolhe", () => {
    const layout = resizeQueueColumns(base, KEYS, { ...pair, deltaPx: -390, final: false });
    expect(layout.intake!.open).toBe(true);
    expect(layout.intake!.weight).toBeCloseTo((2 * QUEUE_COLUMN_MIN_PX) / 800, 2);
  });

  it("solta além do ponto: a coluna recolhe (arrastar até o fim recolhe)", () => {
    const layout = resizeQueueColumns(base, KEYS, { ...pair, deltaPx: -(400 - QUEUE_COLLAPSE_PX + 1), final: true });
    expect(layout.intake!.open).toBe(false);
    expect(layout.prep!.open).toBe(true);
  });

  it("para a direita até o fim recolhe a vizinha", () => {
    const layout = resizeQueueColumns(base, KEYS, { ...pair, deltaPx: 380, final: true });
    expect(layout.prep!.open).toBe(false);
  });

  it("a alça divide com a próxima ABERTA, pulando a recolhida", () => {
    const layout = toggleQueueColumn(base, KEYS, "prep");
    expect(nextOpenQueueKey(layout, KEYS, "intake")).toBe("expedition");
    expect(nextOpenQueueKey(layout, KEYS, "expedition")).toBeNull();
  });
});

describe("nome acessível da faixa", () => {
  it("diz o que abre e o que há dentro, sem travessão", () => {
    expect(queueStripLabel("Preparo", 7, 1)).toBe("Abrir a coluna Preparo: 7 pedidos, 1 atrasado");
    expect(queueStripLabel("Entrada", 1, 0)).toBe("Abrir a coluna Entrada: 1 pedido");
    expect(queueStripLabel("Fila", 2, 3, ["item", "itens"])).toBe("Abrir a coluna Fila: 2 itens, 3 atrasados");
    expect(queueStripLabel("Saída", 2, 2)).not.toMatch(/[—–]/);
  });
});

describe("posto de saída: só uma coluna aberta", () => {
  const keys = ["intake", "prep", "expedition"];
  it("recolhe as outras e guarda os pesos", () => {
    const start = { intake: { open: true, weight: 1.5 }, prep: { open: true, weight: 1 }, expedition: { open: false, weight: 2 } };
    const only = onlyQueueColumn(start, keys, "expedition");
    expect(only).toEqual({ intake: { open: false, weight: 1.5 }, prep: { open: false, weight: 1 }, expedition: { open: true, weight: 2 } });
    expect(isOnlyQueueColumn(only, keys, "expedition")).toBe(true);
    expect(isOnlyQueueColumn(start, keys, "expedition")).toBe(false);
  });
  it("coluna que não existe não mexe em nada", () => {
    const start = { intake: { open: true, weight: 1 }, prep: { open: true, weight: 1 }, expedition: { open: true, weight: 1 } };
    expect(onlyQueueColumn(start, keys, "nada")).toBe(start);
  });
});
