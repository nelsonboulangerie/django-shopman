import { describe, expect, it } from "vitest";
import {
  addonStatusLabel,
  choiceRule,
  parsePriceQ,
  splitIfoodReason,
} from "~/presentation/channelAddons";

import {
  channelCatalogTabs,
  pickChannelCatalogTab,
  snapshotLabel,
} from "~/presentation/channelCatalog";

describe("parsePriceQ", () => {
  it.each([
    ["12,50", 1250],
    ["R$ 3", 300],
    ["1.234,56", 123456],
    ["2.5", 250],
    ["0", 0],
  ])("%s → %d centavos", (text, cents) => {
    expect(parsePriceQ(text)).toBe(cents);
  });
  it.each(["", "abc", "1,234", "-2", "12,5,0"])("%s não é preço", (text) => {
    expect(parsePriceQ(text)).toBeNull();
  });
});

describe("choiceRule", () => {
  it("diz se é opcional ou obrigatório e quantos", () => {
    expect(choiceRule(0, 1)).toBe("Opcional, escolhe 1");
    expect(choiceRule(0, 3)).toBe("Opcional, até 3");
    expect(choiceRule(1, 1)).toBe("Obrigatório, escolhe 1");
    expect(choiceRule(1, 3)).toBe("Obrigatório, de 1 a 3");
  });
  it("rotula o estado", () => {
    expect(addonStatusLabel(true)).toBe("Ativo");
    expect(addonStatusLabel(false)).toBe("Pausado");
  });
});

describe("abas do catálogo do canal", () => {
  it("Complementos só no iFood", () => {
    expect(channelCatalogTabs("ifood").map((t) => t.value)).toEqual([
      "categories",
      "addons",
      "bindings",
    ]);
    expect(channelCatalogTabs("web").map((t) => t.value)).toEqual([
      "categories",
      "bindings",
    ]);
  });
  it("aba desconhecida ou de outro canal volta para Categorias", () => {
    expect(pickChannelCatalogTab("addons", "ifood")).toBe("addons");
    expect(pickChannelCatalogTab("addons", "web")).toBe("categories");
    expect(pickChannelCatalogTab(undefined, "ifood")).toBe("categories");
  });
  it("rotula a captura com data de Brasília, sem o ISO cru", () => {
    expect(
      snapshotLabel({
        id: 1,
        captured_at: "2026-11-17T15:26:44.058036+00:00",
        context: "DEFAULT",
        item_count: 9,
      }),
    ).toBe("Captura nº 1 · 17/11/2026 12:26 · DEFAULT · 9 anúncios");
  });
});

describe("splitIfoodReason", () => {
  it("separa a frase do operador do texto original do iFood", () => {
    expect(
      splitIfoodReason(
        "A foto não foi aceita pelo iFood: formato, tamanho ou endereço inválido. | iFood: image could not be processed (ProductDto.imagePath)",
      ),
    ).toEqual({
      text: "A foto não foi aceita pelo iFood: formato, tamanho ou endereço inválido.",
      original: "image could not be processed (ProductDto.imagePath)",
    });
    expect(splitIfoodReason("Informe o nome.")).toEqual({
      text: "Informe o nome.",
      original: "",
    });
  });
});
