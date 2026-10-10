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

  it("aceita o contorno de foco puxado para dentro mesmo na borda do recorte", async () => {
    Object.defineProperty(document.documentElement, "scrollWidth", { configurable: true, value: 390 });
    Object.defineProperty(document.documentElement, "clientWidth", { configurable: true, value: 390 });
    const frame = document.createElement("div");
    frame.style.overflow = "hidden";
    frame.getBoundingClientRect = () => rect(10, 10, 100, 60);
    const button = document.createElement("button");
    button.className = "focus-visible:-outline-offset-3";
    button.style.opacity = "1";
    button.getBoundingClientRect = () => rect(10, 20, 48, 32);
    frame.append(button);
    document.body.append(frame);

    const findings = await scanOperatorGeometry(page as never);
    expect(findings.some(({ kind }) => kind === "focus-clipping")).toBe(false);
  });

  it("um controle de 32 px com arredondamento fracionário não é alvo pequeno", async () => {
    Object.defineProperty(document.documentElement, "scrollWidth", { configurable: true, value: 390 });
    Object.defineProperty(document.documentElement, "clientWidth", { configurable: true, value: 390 });
    const input = document.createElement("input");
    input.style.opacity = "1";
    input.getBoundingClientRect = () => rect(10, 10, 128, 31.984375);
    document.body.append(input);

    const findings = await scanOperatorGeometry(page as never, { touch: true });
    expect(findings.some(({ kind }) => kind === "touch-target")).toBe(false);
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

  describe("rótulo que cabe (dono, 10/10/2026)", () => {
    function setup() {
      Object.defineProperty(globalThis, "innerWidth", { configurable: true, value: 1280 });
      Object.defineProperty(globalThis, "innerHeight", { configurable: true, value: 800 });
      Object.defineProperty(document.documentElement, "scrollWidth", { configurable: true, value: 1280 });
      Object.defineProperty(document.documentElement, "clientWidth", { configurable: true, value: 1280 });
    }
    function control(label: string, box: DOMRect, text: { scroll: number; client: number; rect?: DOMRect }) {
      const button = document.createElement("button");
      button.style.opacity = "1";
      button.getBoundingClientRect = () => box;
      const span = document.createElement("span");
      span.style.opacity = "1";
      span.textContent = label;
      span.getBoundingClientRect = () => text.rect ?? box;
      Object.defineProperty(span, "scrollWidth", { configurable: true, value: text.scroll });
      Object.defineProperty(span, "clientWidth", { configurable: true, value: text.client });
      button.append(span);
      document.body.append(button);
      return { button, span };
    }

    it("reprova rótulo cortado seco dentro do botão", async () => {
      setup();
      control("Enviar à cozinha", rect(10, 10, 60, 32), { scroll: 104, client: 40 });
      const findings = await scanOperatorGeometry(page as never);
      expect(findings.some(({ kind }) => kind === "control-text-overflow")).toBe(true);
    });

    it("reprova texto que passa da caixa do botão", async () => {
      setup();
      control("Enviar à cozinha", rect(10, 10, 60, 32), { scroll: 104, client: 104, rect: rect(10, 10, 104, 20) });
      const findings = await scanOperatorGeometry(page as never);
      expect(findings.find(({ kind }) => kind === "control-text-overflow")?.message).toContain("passa da caixa");
    });

    it("aceita reticência com o completo na dica, e reprova sem ela", async () => {
      setup();
      const { button, span } = control("Enviar à cozinha", rect(10, 10, 60, 32), { scroll: 104, client: 40 });
      span.style.textOverflow = "ellipsis";
      let findings = await scanOperatorGeometry(page as never);
      expect(findings.find(({ kind }) => kind === "control-text-overflow")?.message).toContain("reticência");
      button.title = "Enviar à cozinha";
      findings = await scanOperatorGeometry(page as never);
      expect(findings.some(({ kind }) => kind === "control-text-overflow")).toBe(false);
    });

    it("reprova controles sobrepostos", async () => {
      setup();
      control("Salvar", rect(10, 10, 80, 32), { scroll: 40, client: 40 });
      control("Cancelar", rect(60, 10, 80, 32), { scroll: 50, client: 50 });
      const findings = await scanOperatorGeometry(page as never);
      expect(findings.some(({ kind }) => kind === "control-overlap")).toBe(true);
    });

    it("aceita o completo no title do próprio trecho cortado", async () => {
      setup();
      const { span } = control("Maria Santos, retirada às 15h", rect(10, 10, 60, 32), { scroll: 160, client: 40 });
      span.style.textOverflow = "ellipsis";
      span.title = "Maria Santos, retirada às 15h";
      const findings = await scanOperatorGeometry(page as never);
      expect(findings.some(({ kind }) => kind === "control-text-overflow")).toBe(false);
    });

    it("não confunde conteúdo sob barra fixa, nem recortado pela rolagem, com sobreposição", async () => {
      setup();
      control("Salvar", rect(10, 760, 80, 32), { scroll: 40, client: 40 });
      const bar = document.createElement("nav");
      bar.style.position = "fixed";
      document.body.append(bar);
      const { button } = control("Início", rect(0, 752, 120, 48), { scroll: 40, client: 40 });
      bar.append(button);
      let findings = await scanOperatorGeometry(page as never);
      expect(findings.some(({ kind }) => kind === "control-overlap")).toBe(false);

      document.body.innerHTML = "";
      const list = document.createElement("div");
      list.style.overflowY = "auto";
      list.getBoundingClientRect = () => rect(0, 0, 400, 700);
      document.body.append(list);
      const hidden = control("Item 30", rect(10, 720, 80, 32), { scroll: 40, client: 40 });
      list.append(hidden.button);
      control("Fechar", rect(0, 712, 120, 48), { scroll: 40, client: 40 });
      findings = await scanOperatorGeometry(page as never);
      expect(findings.some(({ kind }) => kind === "control-overlap")).toBe(false);
    });

    it("não lê painel de aba como rótulo de controle", async () => {
      setup();
      const panel = document.createElement("div");
      panel.setAttribute("role", "tabpanel");
      panel.tabIndex = 0;
      panel.style.opacity = "1";
      panel.textContent = "Pedidos confirmados por hora";
      panel.getBoundingClientRect = () => rect(10, 10, 300, 200);
      Object.defineProperty(panel, "scrollWidth", { configurable: true, value: 340 });
      Object.defineProperty(panel, "clientWidth", { configurable: true, value: 300 });
      document.body.append(panel);
      const findings = await scanOperatorGeometry(page as never);
      expect(findings.some(({ kind }) => kind === "control-text-overflow")).toBe(false);
    });

    it("texto de peça fixa reserva as duas linhas e leva o completo quando corta", async () => {
      setup();
      const name = document.createElement("p");
      name.className = "op-fixed-lines";
      name.style.opacity = "1";
      name.style.lineHeight = "20px";
      name.textContent = "Croissant de manteiga francesa recheado com amêndoas";
      name.getBoundingClientRect = () => rect(10, 10, 120, 20);
      Object.defineProperty(name, "clientHeight", { configurable: true, value: 20 });
      Object.defineProperty(name, "scrollHeight", { configurable: true, value: 60 });
      document.body.append(name);
      const findings = await scanOperatorGeometry(page as never);
      const fixed = findings.filter(({ kind }) => kind === "fixed-text").map(({ message }) => message);
      expect(fixed.some((message) => message.includes("reserva 2 linhas"))).toBe(true);
      expect(fixed.some((message) => message.includes("cortado"))).toBe(true);
    });
  });
});
