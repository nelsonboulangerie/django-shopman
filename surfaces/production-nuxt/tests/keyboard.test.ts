import { describe, expect, it } from "vitest";

import {
  resolveProductionGlobalShortcut,
  resolveQuantityKeyboardShortcut,
} from "../app/presentation/keyboard";

function key(
  value: string,
  overrides: Partial<KeyboardEvent> = {},
): KeyboardEvent {
  return {
    key: value,
    code: overrides.code ?? value,
    altKey: false,
    ctrlKey: false,
    metaKey: false,
    shiftKey: false,
    ...overrides,
  } as KeyboardEvent;
}

describe("atalho global da Produção", () => {
  it("R relê; etapas, busca e ajuda são do shell e não passam por aqui", () => {
    expect(resolveProductionGlobalShortcut(key("R"))).toBe("refresh");
    expect(resolveProductionGlobalShortcut(key("r"))).toBe("refresh");
    expect(
      resolveProductionGlobalShortcut(key("¡", { altKey: true, code: "Digit1" })),
    ).toBeNull();
    expect(resolveProductionGlobalShortcut(key("/"))).toBeNull();
    expect(resolveProductionGlobalShortcut(key("?"))).toBeNull();
    expect(resolveProductionGlobalShortcut(key("F5"))).toBeNull();
    expect(resolveProductionGlobalShortcut(key("r", { metaKey: true }))).toBeNull();
    expect(resolveProductionGlobalShortcut(key("r", { ctrlKey: true }))).toBeNull();
  });
});

describe("numpad físico", () => {
  it("resolve dígitos das duas fileiras, apagar, limpar e confirmar", () => {
    expect(
      resolveQuantityKeyboardShortcut(key("7", { code: "Digit7" })),
    ).toEqual({ kind: "digit", digit: "7" });
    expect(
      resolveQuantityKeyboardShortcut(key("7", { code: "Numpad7" })),
    ).toEqual({ kind: "digit", digit: "7" });
    expect(resolveQuantityKeyboardShortcut(key("Backspace"))).toEqual({
      kind: "backspace",
    });
    expect(resolveQuantityKeyboardShortcut(key("Delete"))).toEqual({
      kind: "clear",
    });
    expect(resolveQuantityKeyboardShortcut(key("c"))).toEqual({
      kind: "clear",
    });
    expect(
      resolveQuantityKeyboardShortcut(key("Enter", { code: "NumpadEnter" })),
    ).toEqual({ kind: "confirm" });
  });

  it("ignora combinações modificadas", () => {
    expect(
      resolveQuantityKeyboardShortcut(key("4", { altKey: true })),
    ).toBeNull();
    expect(
      resolveQuantityKeyboardShortcut(key("4", { ctrlKey: true })),
    ).toBeNull();
  });
});
