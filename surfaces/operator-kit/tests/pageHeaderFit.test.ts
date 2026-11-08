// @vitest-environment happy-dom

import { afterEach, describe, expect, it, vi } from "vitest";

import { fitPageHeader } from "../app/composables/usePageHeaderFit";

// O happy-dom não faz layout: cada degrau declara quanto a barra precisa, e o teste
// confere que ela para no primeiro em que cabe (dono, 07/11/2026: o cabeçalho do pedido
// no Gestor sobrepunha seta, hora e busca a 1360 px).
function bar(need: Record<"full" | "compact" | "wrap", number>, width = 1000, titleLines: Partial<Record<"full" | "compact" | "wrap", number>> = {}) {
  const root = document.createElement("div");
  const left = document.createElement("div");
  const title = document.createElement("h1");
  title.dataset.slot = "title";
  title.textContent = "Pedido 3761";
  Object.defineProperty(title, "clientWidth", { configurable: true, value: 80 });
  left.append(title);
  root.append(left);
  document.body.append(root);
  const step = () => (root.dataset.pageHeaderFit ?? "full") as "full" | "compact" | "wrap";
  Object.defineProperty(root, "clientWidth", { configurable: true, get: () => width });
  Object.defineProperty(root, "scrollWidth", { configurable: true, get: () => Math.max(width, need[step()]) });
  vi.spyOn(Range.prototype, "getClientRects").mockImplementation(() => {
    const lines = titleLines[step()] ?? 1;
    return Array.from({ length: lines }, (_, index) => ({ top: index * 24, width: 60, height: 20 })) as unknown as DOMRectList;
  });
  return root;
}

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("a barra do topo que cabe", () => {
  it("cabendo, fica inteira", () => {
    const root = bar({ full: 900, compact: 700, wrap: 600 });
    expect(fitPageHeader(root)).toBe("full");
    expect(root.dataset.pageHeaderFit).toBe("full");
  });

  it("sem lugar para a busca inteira, a busca vira lupa", () => {
    const root = bar({ full: 1143, compact: 850, wrap: 600 });
    expect(fitPageHeader(root)).toBe("compact");
  });

  it("nem com a lupa, as ações descem de linha", () => {
    const root = bar({ full: 1400, compact: 1100, wrap: 700 });
    expect(fitPageHeader(root)).toBe("wrap");
  });

  it("o título espremido em duas linhas também conta como não caber", () => {
    const root = bar({ full: 900, compact: 800, wrap: 700 }, 1000, { full: 2 });
    expect(fitPageHeader(root)).toBe("compact");
  });

  it("a caixa do elemento e a do texto, 2 px abaixo, são a mesma linha", () => {
    const root = bar({ full: 900, compact: 800, wrap: 700 });
    vi.spyOn(Range.prototype, "getClientRects").mockImplementation(
      () => [{ top: 20, width: 61, height: 24 }, { top: 22, width: 61, height: 20 }] as unknown as DOMRectList,
    );
    expect(fitPageHeader(root)).toBe("full");
  });

  it("volta a ficar inteira quando a largura volta", () => {
    const root = bar({ full: 1143, compact: 850, wrap: 600 });
    expect(fitPageHeader(root)).toBe("compact");
    Object.defineProperty(root, "clientWidth", { configurable: true, get: () => 1400 });
    Object.defineProperty(root, "scrollWidth", { configurable: true, get: () => 1400 });
    expect(fitPageHeader(root)).toBe("full");
  });
});
