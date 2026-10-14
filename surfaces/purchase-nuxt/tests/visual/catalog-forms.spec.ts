import { expect, test } from "@playwright/test";

import { captureOperatorEvidence } from "../../../operator-kit/visual/playwright";
import { selectedOperatorViewports } from "../../../operator-kit/visual/matrix";

// Cadastro do Compras (7.2, onda 2) em CLARO e ESCURO: a lista com o gesto de
// criar, e as gavetas do casco (criar/editar/duplicar insumo e fornecedor) com
// os contatos, as conversões e os custos. Mesmo mock hermético da matriz.

const BACKEND = "http://127.0.0.1:" + (process.env.PURCHASE_VISUAL_BACKEND_PORT || "35021");
const THEMES = ["light", "dark"] as const;

const CASES = [
  { id: "materials-list", route: "/base/materials", ready: "[data-base-table]", click: "", open: "" },
  { id: "suppliers-list", route: "/base/suppliers", ready: "[data-base-suppliers-table]", click: "", open: "" },
  {
    id: "material-edit",
    route: "/base/materials/FAR-T65",
    ready: "[data-material-panel]",
    click: 'button[aria-label="Editar o insumo"]',
    open: "[data-material-form]",
  },
  {
    id: "material-duplicate",
    route: "/base/materials/FAR-T65",
    ready: "[data-material-panel]",
    click: 'button[aria-label="Duplicar o insumo"]',
    open: "[data-material-form]",
  },
  {
    id: "supplier-edit",
    route: "/base/suppliers/MOINHO-PARANA",
    ready: "[data-supplier-panel]",
    click: 'button[aria-label="Editar o fornecedor"]',
    open: "[data-supplier-form]",
  },
  {
    id: "supplier-duplicate",
    route: "/base/suppliers/MOINHO-PARANA",
    ready: "[data-supplier-panel]",
    click: 'button[aria-label="Duplicar o fornecedor"]',
    open: "[data-supplier-form]",
  },
];

const selectedRoute = process.env.OPERATOR_VISUAL_ROUTE || "";
const cases = CASES.filter((item) => !selectedRoute || item.route === selectedRoute);

for (const viewport of selectedOperatorViewports()) {
  for (const theme of THEMES) {
    for (const item of cases) {
      test(`${item.id} · ${theme} · ${viewport.id}`, async ({ page, request }, testInfo) => {
        await request.get(BACKEND + "/__visual/scenario?set=normal");
        await page.setViewportSize({
          width: Math.round(viewport.width / (viewport.zoom || 1)),
          height: Math.round(viewport.height / (viewport.zoom || 1)),
        });
        await page.addInitScript(
          ([value, key]) => {
            try {
              localStorage.setItem("nuxt-color-mode", value);
              localStorage.setItem(key, value);
            } catch {
              // armazenamento bloqueado: segue claro
            }
          },
          [theme, "purchase-color-mode"],
        );
        await page.emulateMedia({ colorScheme: theme });
        await page.goto(item.route);
        await expect(page.locator("[data-purchase-app]")).toBeVisible();
        await expect(page.locator(item.ready).first()).toBeAttached({ timeout: 20_000 });
        if (item.click) {
          await page.locator(item.click).first().click({ timeout: 10_000 });
          await expect(page.locator(item.open).first()).toBeAttached({ timeout: 20_000 });
        }
        await page.waitForTimeout(800);
        await captureOperatorEvidence(page, testInfo, {
          app: "purchase",
          surface: `purchase-${item.id}`,
          route: item.route,
          scenario: "normal",
          state: item.click ? "form" : "list",
          theme,
          viewport,
        });
      });
    }
  }
}
