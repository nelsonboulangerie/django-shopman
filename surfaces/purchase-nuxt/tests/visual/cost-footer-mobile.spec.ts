import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { captureOperatorEvidence } from "../../../operator-kit/visual/playwright";
import { selectedOperatorViewports } from "../../../operator-kit/visual/matrix";

// Regressão CI #1959: a terceira ação não pode empurrar Salvar para fora do celular.
for (const viewport of selectedOperatorViewports(
  "mobile-standard,mobile-narrow",
)) {
  for (const theme of ["light", "dark"] as const) {
    test(`ações de custos ${viewport.id} ${theme}`, async ({
      page,
    }, testInfo) => {
      const failures: string[] = [];
      page.on("response", (response) => {
        if (response.status() >= 400)
          failures.push(`${response.status()} ${response.url()}`);
      });
      await page.setViewportSize({
        width: viewport.width,
        height: viewport.height,
      });
      await page.addInitScript(
        (theme) => localStorage.setItem("purchase-nuxt-color-mode", theme),
        theme,
      );
      await page.emulateMedia({ colorScheme: theme });
      await page.goto("/base/costs");
      await expect(page.locator("[data-cost-batch-table]")).toBeVisible();
      await expect(page.locator("html")).toHaveClass(new RegExp(theme));
      await page
        .getByRole("textbox", { name: /^Valor de / })
        .first()
        .evaluate((element) => {
          const data = new DataTransfer();
          data.setData("text/plain", "12,50\n20,75");
          element.dispatchEvent(
            new ClipboardEvent("paste", {
              bubbles: true,
              cancelable: true,
              clipboardData: data,
            }),
          );
        });
      await expect(
        page.getByRole("button", { name: "Desfazer", exact: true }),
      ).toBeEnabled();
      await captureOperatorEvidence(page, testInfo, {
        app: "purchase",
        surface: "purchase-cost-grid-footer",
        route: "/base/costs",
        scenario: "pasted-two-values",
        state: "draft",
        theme,
        viewport,
      });
      await page
        .getByRole("button", { name: "Salvar 2 como padrão", exact: true })
        .scrollIntoViewIfNeeded();
      const out = resolve(
        "../../docs/coordination/EVIDENCE/ONDA4-3-tabelao-insumos",
      );
      mkdirSync(out, { recursive: true });
      await page.screenshot({
        path: resolve(out, `after-fix-costs-${viewport.id}-${theme}.png`),
        fullPage: true,
      });
      expect(failures).toEqual([]);
    });
  }
}
