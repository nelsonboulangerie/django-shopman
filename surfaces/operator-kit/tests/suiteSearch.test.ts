// Busca da suíte, a parte pura (V6-BUSCA; fase 2, K6): níveis, contagens, realce e teclas.
import { describe, expect, it } from "vitest";

import {
  SUITE_SEARCH_MIN_LENGTH,
  appCount,
  flattenGroups,
  highlightParts,
  suiteEmptyCopy,
  suiteLevels,
  suiteQueryReady,
  suiteResultColor,
  suiteResultLabel,
  suiteScreenTarget,
  suiteSearchHotkey,
  suiteTotal,
  surfaceRefForKitApp,
  type SuiteSearchGroup,
} from "../app/presentation/suiteSearch";

function result(app: string, key: string, type = "orders") {
  return { key, type, app, app_label: app, place: `${app} › X`, title: key, detail: "", url: `https://${app}.test/${key}`, icon: "user" };
}

const GROUPS: SuiteSearchGroup[] = [
  { type: "orders", label: "Pedidos", results: [result("gestor", "X36"), result("gestor", "U78")] },
  { type: "preorders", label: "Encomendas", results: [result("pos", "E1", "preorders")] },
  { type: "materials", label: "Insumos", results: [result("purchase", "MANTEIGA", "materials")] },
];

describe("níveis", () => {
  it("No app é o app atual; Na suíte, os outros; cada resultado num nível só", () => {
    const levels = suiteLevels(GROUPS, "gestor");
    expect(levels.app.map((item) => [item.result.key, item.typeLabel])).toEqual([
      ["X36", "Pedidos"],
      ["U78", "Pedidos"],
    ]);
    expect(levels.suite.map((item) => [item.result.key, item.typeLabel])).toEqual([
      ["E1", "Encomendas"],
      ["MANTEIGA", "Insumos"],
    ]);
  });

  it("sem app (a Central), tudo é Na suíte", () => {
    const levels = suiteLevels(GROUPS, "");
    expect(levels.app).toEqual([]);
    expect(levels.suite).toHaveLength(4);
  });

  it("o alvo do recorte sai do rótulo da tela", () => {
    expect(suiteScreenTarget("filtrando o quadro")).toBe("o quadro");
    expect(suiteScreenTarget("Filtrando os clientes")).toBe("os clientes");
    expect(suiteScreenTarget("")).toBe("esta tela");
  });

  it("o app do kit vira o nome que o Django usa (o Gestor é `orders` no kit)", () => {
    expect(surfaceRefForKitApp("orders")).toBe("gestor");
    expect(surfaceRefForKitApp("pos")).toBe("pos");
    expect(surfaceRefForKitApp("hub")).toBe("");
    expect(surfaceRefForKitApp(undefined)).toBe("");
  });
});

describe("recorte", () => {
  it("contagens: o total da suíte e o do app vêm da resposta", () => {
    expect(suiteTotal(GROUPS)).toBe(4);
    expect(flattenGroups(GROUPS).map((r) => r.key)).toEqual(["X36", "U78", "E1", "MANTEIGA"]);
    expect(appCount([{ ref: "gestor", label: "Gestor", count: 2 }], "gestor")).toBe(2);
    expect(appCount([], "gestor")).toBe(0);
  });
});

describe("cópia e realce", () => {
  it("menos de duas letras não busca", () => {
    expect(SUITE_SEARCH_MIN_LENGTH).toBe(2);
    expect(suiteQueryReady(" m ")).toBe(false);
    expect(suiteQueryReady("ma")).toBe(true);
  });

  it("marca o termo sem acento e sem caixa", () => {
    expect(highlightParts("X36 · María Santos", "maria")).toEqual([
      { text: "X36 · ", match: false },
      { text: "María", match: true },
      { text: " Santos", match: false },
    ]);
    expect(highlightParts("Croissant", "")).toEqual([{ text: "Croissant", match: false }]);
  });

  it("o vazio diz onde procurou", () => {
    expect(suiteEmptyCopy("maria", "suite", "Gestor")).toBe("Nada na suíte com “maria”.");
    expect(suiteEmptyCopy("maria", "app", "Gestor")).toBe("Nada em Gestor com “maria”.");
  });

  it("o nome acessível diz o que é, onde abre e o detalhe", () => {
    expect(suiteResultLabel({ ...result("gestor", "X36"), place: "Gestor › Pedidos", detail: "Em preparo" })).toBe(
      "X36, Gestor › Pedidos, Em preparo",
    );
  });

  it("o selo do resultado tem a cor do app de destino", () => {
    expect(suiteResultColor("gestor")).toMatch(/^#/);
    expect(suiteResultColor("pos")).toMatch(/^#/);
    expect(suiteResultColor("nao-existe")).toBe("");
  });
});

describe("teclas", () => {
  const input = { tagName: "INPUT" } as unknown as EventTarget;
  const body = { tagName: "BODY" } as unknown as EventTarget;
  const key = (k: string, extra: Partial<KeyboardEvent> = {}) =>
    ({ key: k, ctrlKey: false, metaKey: false, altKey: false, target: body, ...extra }) as KeyboardEvent;

  it("`/` fora de campo e Ctrl K (ou ⌘K) em qualquer lugar abrem a busca", () => {
    expect(suiteSearchHotkey(key("/"))).toBe(true);
    expect(suiteSearchHotkey(key("/", { target: input }))).toBe(false);
    expect(suiteSearchHotkey(key("k", { ctrlKey: true, target: input }))).toBe(true);
    expect(suiteSearchHotkey(key("K", { metaKey: true }))).toBe(true);
    expect(suiteSearchHotkey(key("k"))).toBe(false);
  });

  it("onde o `/` é do campo da tela (PDV), só Ctrl K abre a suíte", () => {
    expect(suiteSearchHotkey(key("/"), { slash: false })).toBe(false);
    expect(suiteSearchHotkey(key("k", { ctrlKey: true }), { slash: false })).toBe(true);
  });
});
