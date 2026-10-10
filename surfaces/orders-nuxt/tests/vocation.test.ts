import { describe, expect, it } from "vitest";

import { vocationLabel, vocationNotice, vocationOptions } from "../app/presentation/vocation";

const choices = [
  { ref: "leva", label: "Leva", hint: "Pão, geleia" },
  { ref: "hibrido", label: "Híbrido", hint: "" },
];

describe("vocationOptions / vocationLabel", () => {
  it("as escolhas vêm do servidor, na ordem dele", () => {
    expect(vocationOptions(choices)).toEqual([
      { value: "leva", label: "Leva", hint: "Pão, geleia" },
      { value: "hibrido", label: "Híbrido", hint: "" },
    ]);
    expect(vocationOptions(undefined)).toEqual([]);
  });

  it("vazio é Sem vocação; ref desconhecido aparece cru, não some", () => {
    expect(vocationLabel("", choices)).toBe("Sem vocação");
    expect(vocationLabel("hibrido", choices)).toBe("Híbrido");
    expect(vocationLabel("antigo", choices)).toBe("antigo");
  });
});

describe("vocationNotice", () => {
  const item = (sku: string, name = sku) => ({ sku, name });

  it("sem pendente não há aviso", () => {
    expect(vocationNotice([])).toBeNull();
    expect(vocationNotice(undefined)).toBeNull();
  });

  it("singular e um nome", () => {
    expect(vocationNotice([item("BOLO", "Bolo")])).toEqual({
      count: 1, headline: "1 produto à venda sem vocação", names: "Bolo", firstSku: "BOLO",
    });
  });

  it("até três nomes, ligados por e", () => {
    const notice = vocationNotice([item("A", "Bolo"), item("B", "Pão"), item("C", "Torta")])!;
    expect(notice.headline).toBe("3 produtos à venda sem vocação");
    expect(notice.names).toBe("Bolo, Pão e Torta");
  });

  it("mais de três: os três primeiros e quantos faltam", () => {
    const notice = vocationNotice(["A", "B", "C", "D", "E"].map((sku) => item(sku)))!;
    expect(notice.names).toBe("A, B, C e mais 2");
    expect(notice.firstSku).toBe("A");
  });

  it("produto sem nome aparece pelo SKU", () => {
    expect(vocationNotice([item("X1", "")])!.names).toBe("X1");
  });
});
