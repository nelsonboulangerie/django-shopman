import { expect, test, type Page } from "@playwright/test";

import type { OperatorVisualViewport } from "../../visual/matrix";

// Trava da faixa "Sem conexão" (`OfflineBanner`; 10/10/2026: no PDV ela cobria o
// cabeçalho da coluna da comanda e a barra do topo). Na bancada do shell da suíte
// (`catalog/OperatorKitPhoneHeaderPage.vue`), a 390, 768 e 1366 px:
//   - com a faixa, NENHUM controle interativo fica sob ela: todo controle visível
//     começa abaixo da faixa, e o ponto do meio dele é dele (não da faixa);
//   - o shell desce exatamente a altura da faixa e cabe na janela (a barra inferior do
//     celular não sai pela base);
//   - a faixa leva o ponto vermelho;
//   - ao voltar a rede, o shell volta ao topo e nada fica deslocado.
// Sem captura de baseline: só geometria.

const ROUTE = "/__operator_kit_catalog/phone-header";
const SIZES: Record<string, { width: number; height: number }> = {
  "mobile-standard": { width: 390, height: 844 },
  "tablet-portrait": { width: 768, height: 1024 },
  "desktop-low": { width: 1366, height: 768 },
};

const INTERACTIVE = [
  "a[href]",
  "button",
  "input",
  "select",
  "textarea",
  "summary",
  "[role=button]",
  "[role=link]",
  "[role=tab]",
  "[role=menuitem]",
  "[role=combobox]",
  "[role=switch]",
  "[role=checkbox]",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

async function underBand(page: Page) {
  return page.evaluate((selector) => {
    const band = document.querySelector("[data-operator-offline-band]")!;
    const bandBox = band.getBoundingClientRect();
    const name = (element: Element) =>
      (element.getAttribute("aria-label") || element.textContent || element.tagName).trim().replace(/\s+/g, " ").slice(0, 60);
    const visible = (element: Element) => {
      const box = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return box.width > 1 && box.height > 1 && style.visibility !== "hidden" && style.display !== "none";
    };
    const controls = [...document.querySelectorAll(selector)].filter(
      (element) => !band.contains(element) && visible(element),
    );
    const covered: string[] = [];
    for (const element of controls) {
      const box = element.getBoundingClientRect();
      // Controle fora da janela (rolado) não conta: a faixa só cobre o topo da janela.
      if (box.bottom <= 0 || box.top >= window.innerHeight) continue;
      if (box.top < bandBox.bottom - 0.5) {
        covered.push(`${name(element)} (topo ${Math.round(box.top)} < faixa ${Math.round(bandBox.bottom)})`);
        continue;
      }
      const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
      if (hit && band.contains(hit)) covered.push(`${name(element)} (o meio é da faixa)`);
    }
    const shell = document.querySelector("[data-operator-suite-shell]")!.getBoundingClientRect();
    return {
      count: controls.length,
      covered,
      bandBottom: bandBox.bottom,
      shellTop: shell.top,
      shellBottom: shell.bottom,
      windowHeight: window.innerHeight,
      sideways: document.documentElement.scrollWidth > window.innerWidth,
      pageScrolls: document.documentElement.scrollHeight > window.innerHeight + 1,
    };
  }, INTERACTIVE);
}

test("faixa \"Sem conexão\": nenhum controle fica sob ela, e nada pula quando a rede vai e volta", async ({ page, context }, testInfo) => {
  const viewport = testInfo.project.metadata.operatorViewport as OperatorVisualViewport | undefined;
  const size = viewport ? SIZES[viewport.id] : undefined;
  test.skip(!size, "Roda a 390, 768 e 1366 px.");
  await page.setViewportSize(size!);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(ROUTE);
  await expect(page.locator("[data-phone-header-bench]")).toBeVisible();
  await page.waitForFunction(() => Boolean((document.querySelector("#__nuxt") as { __vue_app__?: unknown } | null)?.__vue_app__));
  await page.waitForLoadState("networkidle");

  const shell = page.locator("[data-operator-suite-shell]");
  expect((await shell.boundingBox())!.y).toBe(0);

  await context.setOffline(true);
  const band = page.locator("[data-operator-offline-band]");
  await expect(band).toBeVisible();
  await expect(band).toContainText("Sem conexão. Tentando reconectar…");
  // O ponto vermelho (dono, 08/10/2026).
  await expect(band.locator("[data-count-chip]")).toHaveCount(1);

  const offline = await underBand(page);
  expect(offline.count).toBeGreaterThan(5);
  expect(offline.covered).toEqual([]);
  // O shell começa onde a faixa termina e acaba na base da janela.
  expect(Math.abs(offline.shellTop - offline.bandBottom)).toBeLessThanOrEqual(0.5);
  expect(Math.abs(offline.shellBottom - offline.windowHeight)).toBeLessThanOrEqual(0.5);
  expect(offline.sideways).toBe(false);
  expect(offline.pageScrolls).toBe(false);

  await context.setOffline(false);
  await expect(band).toHaveCount(0);
  await expect.poll(async () => (await shell.boundingBox())!.y).toBe(0);
  expect(await page.evaluate(() => document.documentElement.hasAttribute("data-operator-offline"))).toBe(false);
});
