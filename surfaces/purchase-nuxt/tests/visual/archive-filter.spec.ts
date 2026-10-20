import { expect, test } from "@playwright/test";

import { captureOperatorEvidence } from "../../../operator-kit/visual/playwright";
import { selectedOperatorViewports } from "../../../operator-kit/visual/matrix";

const BACKEND = "http://127.0.0.1:" + (process.env.PURCHASE_VISUAL_BACKEND_PORT || "35021");

const screens = [
  { surface: "purchase-base-materials", route: "/base/materials", ready: "[data-base-table]" },
  { surface: "purchase-base-suppliers", route: "/base/suppliers", ready: "[data-base-suppliers-table]" },
] as const;

for (const viewport of selectedOperatorViewports()) {
  for (const theme of ["light", "dark"] as const) {
    for (const screen of screens) {
      test(`Arquivados em ${screen.surface} · ${theme} · ${viewport.id}`, async ({ page, request }, testInfo) => {
        const failures: string[] = [];
        page.on("response", (response) => {
          if (response.status() >= 400) failures.push(`${response.status()} ${response.url()}`);
        });
        await request.get(`${BACKEND}/__visual/scenario?set=normal`);
        await page.addInitScript(
          ([value, key]) => {
            localStorage.setItem("nuxt-color-mode", value);
            localStorage.setItem(key, value);
          },
          [theme, "purchase-nuxt-color-mode"],
        );
        await page.emulateMedia({ colorScheme: theme });
        await page.goto(screen.route);
        await expect(page.locator(screen.ready).first()).toBeVisible();

        await captureOperatorEvidence(page, testInfo, {
          app: "purchase",
          surface: `${screen.surface}-arquivar-compras`,
          route: screen.route,
          scenario: "before",
          state: "normal",
          theme,
          viewport,
        });

        await page.locator("[data-operator-filter-panel-open]").click();
        await page.locator('[data-operator-filter-dimension="archive"]').click();
        await page.getByText("Arquivados", { exact: true }).last().click();
        await expect(page.getByText("Arquivado", { exact: true }).first()).toBeVisible();
        await expect(page.locator("[data-operator-filter-chip]")).toContainText("Arquivados");
        const done = page.locator("[data-operator-filter-panel-done]");
        if (await done.isVisible()) await done.click();
        else await page.keyboard.press("Escape");
        await expect(page.locator("[data-operator-filter-panel]")).toBeHidden();

        await captureOperatorEvidence(page, testInfo, {
          app: "purchase",
          surface: `${screen.surface}-arquivar-compras`,
          route: screen.route,
          scenario: "after",
          state: "archived",
          theme,
          viewport,
        });
        expect(failures).toEqual([]);
      });
    }
  }
}
