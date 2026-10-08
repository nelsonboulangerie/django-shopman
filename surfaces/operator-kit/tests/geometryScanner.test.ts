// @vitest-environment happy-dom

import { afterEach, describe, expect, it, vi } from "vitest";

import { scanOperatorGeometry } from "../visual/scanner";

function rect(x: number, y: number, width: number, height: number): DOMRect {
  return { x, y, width, height, top: y, left: x, right: x + width, bottom: y + height, toJSON: () => ({}) } as DOMRect;
}

const page = {
  evaluate: async <T, A>(callback: (argument: A) => T, argument: A) => callback(argument),
};

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
  Object.defineProperty(document.documentElement, "scrollWidth", { configurable: true, value: 0 });
  Object.defineProperty(document.documentElement, "clientWidth", { configurable: true, value: 0 });
});

describe("scanner geométrico", () => {
  it("encontra overflow real e alvo abaixo do envelope operacional", async () => {
    Object.defineProperty(document.documentElement, "scrollWidth", { configurable: true, value: 420 });
    Object.defineProperty(document.documentElement, "clientWidth", { configurable: true, value: 390 });
    const button = document.createElement("button");
    button.dataset.operatorAuditId = "small-action";
    button.style.opacity = "1";
    button.getBoundingClientRect = () => rect(10, 10, 30, 30);
    document.body.append(button);

    const findings = await scanOperatorGeometry(page as never, { touch: true });
    expect(findings.map(({ kind }) => kind)).toEqual(expect.arrayContaining(["horizontal-overflow", "touch-target"]));
    expect(findings.find(({ kind }) => kind === "touch-target")?.selector).toBe('[data-operator-audit-id="small-action"]');
  });

  it("mede o envelope operacional sem deformar o controle visual", async () => {
    Object.defineProperty(document.documentElement, "scrollWidth", { configurable: true, value: 390 });
    Object.defineProperty(document.documentElement, "clientWidth", { configurable: true, value: 390 });
    const envelope = document.createElement("label");
    envelope.dataset.touchEnvelope = "";
    envelope.style.opacity = "1";
    envelope.getBoundingClientRect = () => rect(10, 10, 48, 48);
    const input = document.createElement("input");
    input.type = "checkbox";
    input.style.opacity = "1";
    input.getBoundingClientRect = () => rect(24, 24, 20, 20);
    envelope.append(input);
    document.body.append(envelope);

    const findings = await scanOperatorGeometry(page as never, { touch: true });
    expect(findings.some(({ kind }) => kind === "touch-target")).toBe(false);
  });

  it("exige min-width zero e limites declarados em panes", async () => {
    Object.defineProperty(document.documentElement, "scrollWidth", { configurable: true, value: 390 });
    Object.defineProperty(document.documentElement, "clientWidth", { configurable: true, value: 390 });
    const pane = document.createElement("section");
    pane.dataset.operatorPane = "";
    pane.style.minWidth = "12px";
    pane.getBoundingClientRect = () => rect(0, 0, 300, 200);
    document.body.append(pane);

    const findings = await scanOperatorGeometry(page as never);
    expect(findings.some(({ kind }) => kind === "pane-constraints")).toBe(true);
  });

  it("detecta foco cortado por ancestral sem rolagem", async () => {
    Object.defineProperty(document.documentElement, "scrollWidth", { configurable: true, value: 390 });
    Object.defineProperty(document.documentElement, "clientWidth", { configurable: true, value: 390 });
    const frame = document.createElement("div");
    frame.style.overflow = "hidden";
    frame.getBoundingClientRect = () => rect(10, 10, 100, 60);
    const button = document.createElement("button");
    button.style.opacity = "1";
    button.getBoundingClientRect = () => rect(8, 20, 48, 48);
    frame.append(button);
    document.body.append(frame);

    const findings = await scanOperatorGeometry(page as never);
    expect(findings.some(({ kind }) => kind === "focus-clipping")).toBe(true);
  });

  it("não confunde conteúdo rolável fora do viewport com chrome sobreposto", async () => {
    Object.defineProperty(globalThis, "innerWidth", { configurable: true, value: 390 });
    Object.defineProperty(globalThis, "innerHeight", { configurable: true, value: 844 });
    Object.defineProperty(document.documentElement, "scrollWidth", { configurable: true, value: 390 });
    Object.defineProperty(document.documentElement, "clientWidth", { configurable: true, value: 390 });
    const button = document.createElement("button");
    button.style.opacity = "1";
    button.getBoundingClientRect = () => rect(12, 1200, 100, 44);
    const chrome = document.createElement("nav");
    chrome.dataset.focusObstruction = "";
    chrome.style.opacity = "1";
    chrome.getBoundingClientRect = () => rect(0, 768, 390, 76);
    document.body.append(button, chrome);
    vi.spyOn(document, "elementFromPoint").mockReturnValue(chrome);

    const findings = await scanOperatorGeometry(page as never, { touch: true });
    expect(findings.some(({ kind }) => kind === "covered-by-chrome")).toBe(false);
    expect(document.elementFromPoint).not.toHaveBeenCalled();
  });
});
