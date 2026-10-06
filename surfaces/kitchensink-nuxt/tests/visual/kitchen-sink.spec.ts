import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { captureOperatorEvidence } from "../../../operator-kit/visual/playwright";
import type { OperatorVisualViewport } from "../../../operator-kit/visual/matrix";

test("consumer real preserva SSR, hidratação, acessibilidade e geometria", async ({ page }, testInfo) => {
  const viewport = testInfo.project.metadata.operatorViewport as OperatorVisualViewport;
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error" || /hydration/i.test(message.text())) errors.push(message.text());
  });

  await page.goto("/?state=extreme-content");
  await expect(page.locator('[data-operator-catalog][data-hydrated="true"]')).toBeAttached();
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
  await captureOperatorEvidence(page, testInfo, {
    app: "kitchensink",
    surface: "canonical-catalog",
    route: "/?state=extreme-content",
    scenario: "normal",
    state: "extreme-content",
    theme: "light",
    viewport,
  }, { allowedFindings: [] });
  expect(errors).toEqual([]);
});

test("HTML SSR contém conteúdo útil sem JavaScript", async ({ request }, testInfo) => {
  const viewport = testInfo.project.metadata.operatorViewport as OperatorVisualViewport;
  test.skip(viewport.id !== "desktop-common", "SSR independe de viewport.");
  const response = await request.get("/?state=readonly");
  expect(response.ok()).toBe(true);
  const html = await response.text();
  expect(html).toContain("Operator Kitchen Sink");
  expect(html).toContain("Somente leitura");
  expect(html).toContain('data-hydrated="false"');
});

test("teclado percorre controles e modal devolve o foco", async ({ page }, testInfo) => {
  const viewport = testInfo.project.metadata.operatorViewport as OperatorVisualViewport;
  test.skip(viewport.id !== "desktop-common", "Interação completa roda uma vez.");
  await page.goto("/");
  await expect(page.locator('[data-operator-catalog][data-hydrated="true"]')).toBeAttached();
  const trigger = page.getByRole("button", { name: "Abrir confirmação" });
  await trigger.focus();
  await expect(trigger).toBeFocused();
  await trigger.press("Enter");
  await expect(page.getByRole("dialog", { name: "Confirmar ação" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
});
