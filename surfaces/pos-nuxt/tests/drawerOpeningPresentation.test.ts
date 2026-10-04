import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  autoOpensOnCashSale,
  drawerOpeningFailed,
  drawerOpeningMessage,
  openDrawerLabel,
  pendingCashLine,
  pendingCashTitle,
} from "~/presentation/drawerOpening";

describe("abrir a gaveta pelo tablet — as frases e a decisão", () => {
  it("o cartão diz de qual comanda é o dinheiro, o troco e para onde levar", () => {
    const pending = { orderRef: "1012", tabDisplay: "6", changeQ: 4500 };
    expect(pendingCashTitle(pending)).toBe("Dinheiro da comanda 6");
    // O Intl separa "R$" do número com espaço inseparável.
    expect(pendingCashLine(pending, "Balcão").replace(/\u00a0/g, " ")).toBe("troco R$ 45,00 · leve ao Balcão");
    expect(pendingCashTitle({ ...pending, tabDisplay: "" })).toBe("Dinheiro do pedido 1012");
    expect(pendingCashLine({ ...pending, changeQ: 0 }, "Balcão")).toBe("leve ao Balcão");
  });

  it("o botão leva o nome do terminal", () => {
    expect(openDrawerLabel("Balcão")).toBe("Abrir gaveta do Balcão");
    expect(openDrawerLabel("")).toBe("Abrir gaveta do Balcão");
  });

  it("no tablet a gaveta NUNCA abre sozinha na venda em dinheiro", () => {
    expect(autoOpensOnCashSale({ localAgent: false, openOnCashSale: true })).toBe(false);
    expect(autoOpensOnCashSale({ localAgent: true, openOnCashSale: true })).toBe(true);
    expect(autoOpensOnCashSale({ localAgent: true, openOnCashSale: false })).toBe(false);
  });

  it("nenhum estado de falha finge sucesso", () => {
    for (const state of ["failed", "expired", "offline"] as const) {
      expect(drawerOpeningFailed(state)).toBe(true);
      expect(drawerOpeningMessage(state, "Balcão")).toMatch(/não abriu/);
    }
    expect(drawerOpeningMessage("uncertain", "Balcão")).toMatch(/Olhe a gaveta/);
    expect(drawerOpeningMessage("sent", "Balcão")).toBe("Gaveta do Balcão aberta.");
  });

  it("a frase do servidor vence a da tela", () => {
    expect(drawerOpeningMessage("failed", "Balcão", "A gaveta do Balcão abre com a chave.")).toBe(
      "A gaveta do Balcão abre com a chave.",
    );
  });
});

describe("trava: o operador nunca lê a tolerância do caixa", () => {
  // Decisão do dono (04/10/2026): o fechamento é cego. O veredito (dentro ou
  // fora da tolerância) é do gerente, no relatório do turno. Nenhuma tela do PDV
  // pode trazer a palavra, nem como texto morto.
  const files = [
    "../app/pages/session/closing.vue",
    "../app/pages/session/index.vue",
    "../app/presentation/closing.ts",
    "../app/presentation/cash.ts",
    "../app/presentation/drawerOpening.ts",
    "../app/components/PosDrawerPulseCard.vue",
    "../app/components/PosDenominationCounter.vue",
  ];
  for (const rel of files) {
    it(`${rel} não fala em tolerância`, () => {
      const source = readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
      expect(source.toLowerCase()).not.toMatch(/toler[âa]ncia|tolerance/);
    });
  }
});
