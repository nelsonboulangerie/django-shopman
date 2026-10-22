import { describe, expect, it } from "vitest";

import { useGridEdit } from "../app/composables/useGridEdit";
import {
  editKey,
  parseGrid,
  parseMoneyCell,
  splitEditKey,
} from "../app/presentation/gridEdit";

describe("gridEdit", () => {
  it("lê TSV do Excel preservando as colunas", () => {
    expect(parseGrid("12,00\t15,00\n20,00\t")).toEqual([
      ["12,00", "15,00"],
      ["20,00", ""],
    ]);
  });

  it("cai para ponto e vírgula e vírgula quando não há tab", () => {
    expect(parseGrid("a;b\nc;d")).toEqual([
      ["a", "b"],
      ["c", "d"],
    ]);
    expect(parseGrid("a,b")).toEqual([["a", "b"]]);
  });

  it("preserva uma coluna de preços com vírgula decimal", () => {
    expect(parseGrid("7,50\n8,25\nR$ 1.234,50")).toEqual([
      ["7,50"],
      ["8,25"],
      ["R$ 1.234,50"],
    ]);
    expect(parseGrid("Produto,Preço\nPão,7.50")).toEqual([
      ["Produto", "Preço"],
      ["Pão", "7.50"],
    ]);
  });

  it("preço pt-BR e simples viram centavos", () => {
    expect(parseMoneyCell("1.234,50")).toBe(123450);
    expect(parseMoneyCell("12,5")).toBe(1250);
    expect(parseMoneyCell("12.50")).toBe(1250);
    expect(parseMoneyCell("R$ 3,00")).toBe(300);
    expect(parseMoneyCell("")).toBeNull();
    expect(parseMoneyCell("-1")).toBeNull();
    expect(parseMoneyCell("abc")).toBeNull();
  });

  it("a chave da célula vai e volta", () => {
    expect(splitEditKey(editKey("PAO", "web", "price"))).toEqual([
      "PAO",
      "web",
      "price",
    ]);
  });
});

describe("useGridEdit", () => {
  it("guarda o rascunho e desfaz uma a uma", () => {
    const edit = useGridEdit<number>();
    edit.set("a", 1);
    edit.set("b", 2);
    expect(edit.dirty.value).toBe(2);
    expect(edit.changes.value).toEqual([
      { key: "a", value: 1 },
      { key: "b", value: 2 },
    ]);
    edit.undo();
    expect(edit.draft.value.b).toBeUndefined();
    expect(edit.dirty.value).toBe(1);
    edit.undo();
    expect(edit.dirty.value).toBe(0);
    expect(edit.canUndo.value).toBe(false);
  });

  it("remove volta ao valor do servidor e limpa zera a pilha", () => {
    const edit = useGridEdit<string>();
    edit.set("a", "1");
    edit.remove("a");
    expect(edit.dirty.value).toBe(0);
    edit.set("b", "2");
    edit.clear();
    expect(edit.dirty.value).toBe(0);
    expect(edit.canUndo.value).toBe(false);
  });
});

it("confirma só as células gravadas e preserva o rascunho e o desfazer das outras", () => {
  const edit = useGridEdit<string>();
  edit.set("hidden", "inválido");
  edit.set("saved", "2,50");
  edit.set("hidden", "a corrigir");
  edit.clear(["saved"]);
  expect(edit.draft.value).toEqual({ hidden: "a corrigir" });
  edit.undo();
  expect(edit.draft.value).toEqual({ hidden: "inválido" });
  edit.undo();
  expect(edit.draft.value).toEqual({});
  expect(edit.canUndo.value).toBe(false);
});
