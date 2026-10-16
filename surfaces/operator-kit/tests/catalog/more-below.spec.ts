import { expect, test, type Page } from "@playwright/test";

import type { OperatorVisualViewport } from "../../visual/matrix";

// Trava da dica "tem mais abaixo" (`MoreBelow`) na janela (10/10/2026: a 1366, no B.I.,
// no Compras e no Kitchen Sink, o degradê dela atravessava a barra lateral e lavava o
// pé dela, com Avisos e o menu do operador). Na bancada do shell da suíte com conteúdo
// mais alto que a janela (`catalog/OperatorKitPhoneHeaderPage.vue`, `?more=1`):
//   - a dica aparece e fica DENTRO do painel de conteúdo (as bordas dele);
//   - não cruza a barra lateral nem o pé dela, aberta e compacta;
//   - no celular (barra lateral em gaveta), ocupa a largura do painel, que é a janela.
// Sem captura de baseline: só geometria.

const ROUTE = "/__operator_kit_catalog/phone-header?more=1";
const SIZES: Record<string, { width: number; height: number }> = {
  "mobile-standard": { width: 390, height: 844 },
  "tablet-portrait": { width: 768, height: 1024 },
  "desktop-low": { width: 1366, height: 768 },
};

async function geometry(page: Page) {
  return page.evaluate(() => {
    const box = (selector: string) => {
      const element = document.querySelector(selector);
      if (!element) return null;
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      if (style.display === "none" || rect.width < 1 || rect.height < 1) return null;
      return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
    };
    return {
      hint: box("[data-more-below]"),
      panel: box("[data-operator-content-panel]"),
      rail: box("[data-suite-rail]"),
      railFooter: box("[data-suite-rail-footer]"),
    };
  });
}

type Box = { left: number; right: number; top: number; bottom: number };
const overlaps = (a: Box, b: Box) => a.left < b.right - 0.5 && b.left < a.right - 0.5 && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5;

test("tem mais abaixo: a dica fica no painel de conteúdo, nunca sobre a barra lateral", async ({ page }, testInfo) => {
  const viewport = testInfo.project.metadata.operatorViewport as OperatorVisualViewport | undefined;
  const size = viewport ? SIZES[viewport.id] : undefined;
  test.skip(!size, "Roda a 390, 768 e 1366 px.");
  await page.setViewportSize(size!);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(ROUTE);
  await expect(page.locator("[data-bench-long]")).toBeVisible();
  await page.waitForFunction(() => Boolean((document.querySelector("#__nuxt") as { __vue_app__?: unknown } | null)?.__vue_app__));
  await page.waitForLoadState("networkidle");

  const hint = page.locator("[data-more-below]");
  await expect(hint).toBeVisible();

  async function check(label: string) {
    await expect.poll(async () => {
      const g = await geometry(page);
      const problems: string[] = [];
      if (!g.hint) return ["dica ausente"];
      if (!g.panel) return ["painel de conteúdo ausente"];
      if (g.hint.left < g.panel.left - 0.5) problems.push(`começa em ${Math.round(g.hint.left)}, antes do painel (${Math.round(g.panel.left)})`);
      if (g.hint.right > g.panel.right + 0.5) problems.push(`termina em ${Math.round(g.hint.right)}, depois do painel (${Math.round(g.panel.right)})`);
      if (g.rail && overlaps(g.hint, g.rail)) problems.push("cobre a barra lateral");
      if (g.railFooter && overlaps(g.hint, g.railFooter)) problems.push("cobre o pé da barra lateral");
      return problems;
    }, { message: label }).toEqual([]);
  }

  await check("barra lateral aberta");
  await page.screenshot({ path: testInfo.outputPath("more-below.png") });

  if (size!.width >= 1024) {
    // Compactar a barra lateral muda a largura do painel sem mexer na janela.
    await page.getByRole("button", { name: "Compactar a barra lateral" }).click();
    await check("barra lateral compacta");
    await page.screenshot({ path: testInfo.outputPath("more-below-compact.png") });
  }
});
