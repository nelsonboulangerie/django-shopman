import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import type { OperatorVisualViewport } from "../../../operator-kit/visual/matrix";

// A página "Shell da suíte" (`/suite`): o shell de referência dos apps de operador com as
// peças da fase 2. Sem baseline de imagem: o contrato é de estrutura (o que aparece em
// cada largura), de SSR e de acessibilidade.

function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (/hydration/i.test(message.text())) errors.push(message.text());
  });
  return errors;
}

async function open(page: Page, path: string) {
  await page.goto(path);
  await expect(page.locator('[data-suite-reference][data-hydrated="true"]')).toBeAttached();
}

test("o aviso da tela mostra um inteiro e guarda o resto em e mais N, sem rolagem lateral", async ({ page }, testInfo) => {
  const viewport = testInfo.project.metadata.operatorViewport as OperatorVisualViewport;
  test.skip(!["mobile-standard", "desktop-common"].includes(viewport.id), "Celular e mesa.");
  const errors = watchErrors(page);
  await open(page, "/suite?alerts=three");

  const alerts = page.locator("[data-page-header-alert]");
  await expect(alerts).toHaveCount(1);
  await expect(alerts.first().getByRole("button", { name: "Ver os atrasados" })).toBeVisible();
  await page.getByRole("button", { name: "e mais 2 avisos" }).click();
  await expect(alerts).toHaveCount(3);

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});

test("celular: barra inferior de 3 a 5 vagas, ação na base em fluxo, ⋯ único na barra do topo", async ({ page }, testInfo) => {
  const viewport = testInfo.project.metadata.operatorViewport as OperatorVisualViewport;
  test.skip(viewport.id !== "mobile-standard", "Contrato do celular.");
  await open(page, "/suite?alerts=none");

  const quick = page.locator("[data-operator-quick-bar]");
  await expect(quick.getByRole("link")).toHaveCount(2);
  await expect(quick.locator("[data-section], [data-quick-bar-more]")).toHaveCount(5);
  await expect(page.locator("[data-suite-base-action]")).toBeVisible();
  await expect(page.locator("[data-page-header-more]")).toHaveCount(1);
  await expect(page.locator("[data-page-header-alerts]")).toHaveCount(0);
});

test("mesa: barra lateral na tela, sem barra inferior e sem ação na base", async ({ page }, testInfo) => {
  const viewport = testInfo.project.metadata.operatorViewport as OperatorVisualViewport;
  test.skip(viewport.id !== "desktop-common", "Contrato da mesa.");
  await open(page, "/suite");

  await expect(page.locator("[data-suite-rail]")).toBeVisible();
  await expect(page.locator("[data-operator-suite-tabs]")).toBeHidden();
  await expect(page.locator("[data-suite-base-action]")).toBeHidden();
  await expect(page.locator("[data-suite-swipe] [data-swipe-row]")).toHaveCount(3);
  await expect(page.locator("[data-suite-stacked-chart] [data-operator-reading-plot] svg").first()).toBeVisible();
  // Sem exclusão: o aviso do cabeçalho (descrição na cor plena, AA) e as toolbars (no
  // landmark do cabeçalho) entram na varredura inteira.
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
});

test("HTML SSR da página do shell já traz as peças", async ({ request }, testInfo) => {
  const viewport = testInfo.project.metadata.operatorViewport as OperatorVisualViewport;
  test.skip(viewport.id !== "desktop-common", "SSR independe de viewport.");
  const response = await request.get("/suite?alerts=one");
  expect(response.ok()).toBe(true);
  const html = await response.text();
  expect(html).toContain("O shell de referência");
  expect(html).toContain("2 pedidos passaram do horário");
  expect(html).toContain('data-hydrated="false"');
});
