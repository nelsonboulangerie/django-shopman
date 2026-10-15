import { describe, expect, it } from "vitest";

import {
  changedFieldKeys,
  cloneFormValues,
  dirtyCountLabel,
  isFormDirty,
  sameFormValue,
} from "../app/presentation/formShell";

// A regra pura do estado sujo: o que conta como mudança desde o retrato.

describe("estado sujo do cadastro", () => {
  it("compara primitivos, arrays e objetos simples (inclusive NaN)", () => {
    expect(sameFormValue("a", "a")).toBe(true);
    expect(sameFormValue("a", "b")).toBe(false);
    expect(sameFormValue(["a", "b"], ["a", "b"])).toBe(true);
    expect(sameFormValue(["a"], ["a", "b"])).toBe(false);
    expect(sameFormValue({ a: 1, b: ["x"] }, { a: 1, b: ["x"] })).toBe(true);
    expect(sameFormValue({ a: 1 }, { a: 1, b: 2 })).toBe(false);
    expect(sameFormValue(Number.NaN, Number.NaN)).toBe(true);
    expect(sameFormValue(null, undefined)).toBe(false);
  });

  it("lista só as chaves que mudaram, na ordem em que aparecem", () => {
    const before = { sku: "P1", name: "Pão", price: "10,00", tags: ["a"] };
    const after = { sku: "P1", name: "Pão de queijo", price: "10,00", tags: ["a", "b"] };
    expect(changedFieldKeys(before, after)).toEqual(["name", "tags"]);
  });

  it("sem retrato, o formulário não é dado como sujo", () => {
    expect(isFormDirty(null, { sku: "P1" })).toBe(false);
    expect(isFormDirty({ sku: "P1" }, { sku: "P1" })).toBe(false);
    expect(isFormDirty({ sku: "P1" }, { sku: "P2" })).toBe(true);
  });

  it("o clone do retrato desliga do formulário: mexer depois não muda o retrato", () => {
    const source = { sku: "P1", tags: ["a"], social: { brand: "Nelson" } };
    const copy = cloneFormValues(source);
    source.tags.push("b");
    source.social.brand = "Outra";
    expect(copy).toEqual({ sku: "P1", tags: ["a"], social: { brand: "Nelson" } });
  });

  it("o aviso conta as alterações; sem contagem, não afirma número", () => {
    expect(dirtyCountLabel(1)).toBe("1 alteração não salva");
    expect(dirtyCountLabel(2)).toBe("2 alterações não salvas");
    expect(dirtyCountLabel(0)).toBe("Alterações não salvas");
  });
});
