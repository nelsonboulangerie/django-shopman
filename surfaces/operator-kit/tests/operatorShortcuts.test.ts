// @vitest-environment happy-dom

import { describe, expect, it } from "vitest";

import type { OperatorShortcutCommand } from "../app/types/operatorShortcut";
import {
  defineOperatorShortcutMap,
  findOperatorShortcutCollisions,
  shortcutEventAllowed,
  shortcutMatches,
} from "../app/utils/operatorShortcuts";

const base: OperatorShortcutCommand = {
  id: "suite.search",
  label: "Buscar na suíte",
  combinations: [{ code: "KeyK", control: true, platform: "windows" }],
  scope: "suite",
  owner: "operator-kit",
  enabledContexts: ["ready"],
  forbiddenContexts: ["locked"],
  alternative: "Botão Buscar no cabeçalho",
};

describe("mapa canônico de atalhos", () => {
  it("casa por code e modificadores na plataforma declarada", () => {
    const event = new KeyboardEvent("keydown", { code: "KeyK", key: "k", ctrlKey: true });
    expect(shortcutMatches(event, base.combinations[0]!, "windows")).toBe(true);
    expect(shortcutMatches(event, base.combinations[0]!, "macos")).toBe(false);
  });

  it("bloqueia campos, overlays, repetição, IME e contexto proibido", () => {
    const input = document.createElement("input");
    document.body.append(input);
    const event = new KeyboardEvent("keydown", { code: "KeyK", key: "k", ctrlKey: true, repeat: true });
    Object.defineProperty(event, "target", { value: input });
    expect(shortcutEventAllowed(event, base, new Set(["ready"]))).toBe(false);
    const normal = new KeyboardEvent("keydown", { code: "KeyK", key: "k", ctrlKey: true });
    Object.defineProperty(normal, "target", { value: document.body });
    expect(shortcutEventAllowed(normal, base, new Set(["locked"]))).toBe(false);
  });

  it("cala sob a trava do terminal, que cobre a tela sem ser diálogo", () => {
    const lock = document.createElement("div");
    lock.setAttribute("data-operator-lock", "");
    const event = new KeyboardEvent("keydown", { code: "KeyK", key: "k", ctrlKey: true });
    Object.defineProperty(event, "target", { value: document.body });
    expect(shortcutEventAllowed(event, base, new Set(["ready"]))).toBe(true);
    document.body.append(lock);
    try {
      expect(shortcutEventAllowed(event, base, new Set(["ready"]))).toBe(false);
    } finally {
      lock.remove();
    }
  });

  it("detecta colisão em contexto e plataforma sobrepostos", () => {
    const other: OperatorShortcutCommand = { ...base, id: "screen.search", scope: "screen", owner: "orders" };
    expect(findOperatorShortcutCollisions([base, other])).toMatchObject([
      { first: "suite.search", second: "screen.search", platform: "windows" },
    ]);
    expect(() => defineOperatorShortcutMap([base, other])).toThrow(/Colisão/);
  });

  it("exige alternativa sem teclado", () => {
    expect(() => defineOperatorShortcutMap([{ ...base, alternative: "" }])).toThrow(/alternativa/);
  });
});
