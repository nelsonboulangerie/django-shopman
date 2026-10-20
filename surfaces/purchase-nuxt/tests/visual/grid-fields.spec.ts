import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

const phase = process.env.GRID_EVIDENCE_PHASE || "after";
const out = resolve("../../docs/coordination/EVIDENCE/ONDA4-3-tabelao-insumos");
for (const theme of ["light", "dark"] as const) {
  for (const route of ["costs", "materials"]) {
    test(`${route} ${theme} ${phase}`, async ({ page }) => {
      const failures: string[] = [];
      page.on("response", (response) => {
        if (response.status() >= 400)
          failures.push(`${response.status()} ${response.url()}`);
      });
      await page.setViewportSize({ width: 1440, height: 1000 });
      await page.addInitScript((theme) => {
        localStorage.setItem("nuxt-color-mode", theme);
        localStorage.setItem("purchase-nuxt-color-mode", theme);
      }, theme);
      await page.emulateMedia({ colorScheme: theme });
      await page.goto(`/base/${route}`);
      await expect(
        page.locator(
          route === "costs" ? "[data-cost-batch-table]" : "[data-base-table]",
        ),
      ).toBeVisible();
      await expect(page.locator("html")).toHaveClass(new RegExp(theme));
      if (phase === "after") {
        const field = page
          .getByRole("textbox", {
            name: route === "costs" ? /^Valor de / : /^Mínimo de /,
          })
          .first();
        // ClipboardEvent criado no browser, com dados reais de duas linhas.
        await field.evaluate(
          (element, text) => {
            const data = new DataTransfer();
            data.setData("text/plain", text);
            element.dispatchEvent(
              new ClipboardEvent("paste", {
                bubbles: true,
                cancelable: true,
                clipboardData: data,
              }),
            );
          },
          route === "costs" ? "12,50\ninválido" : "2,5\ninválido",
        );
        await expect(
          page.getByRole("button", { name: "Desfazer", exact: true }).first(),
        ).toBeEnabled();
        await expect(
          page
            .getByText(
              route === "costs"
                ? "Informe um valor de compra maior que zero."
                : "Informe uma quantidade válida.",
            )
            .first(),
        ).toBeVisible();
      }
      await page.waitForTimeout(500);
      mkdirSync(out, { recursive: true });
      await page.screenshot({
        path: resolve(out, `${phase}-${route}-${theme}.png`),
        fullPage: true,
      });
      if (phase === "after") {
        const fields = page.getByRole("textbox", {
          name: route === "costs" ? /^Valor de / : /^Mínimo de /,
        });
        await fields.nth(1).fill(route === "costs" ? "20,75" : "3,5");
        if (route === "costs") {
          await page.locator("[data-cost-batch-supplier]").click();
          await page
            .getByRole("option", { name: "Moinho Paraná", exact: true })
            .click();
        }
        const suffix =
          route === "costs" ? "/costs/batch/" : "/materials/min-stock/";
        const sent: unknown[] = [];
        page.on("request", (request) => {
          if (request.method() === "POST" && request.url().includes(suffix))
            sent.push(request.postDataJSON());
        });
        const saved = page.waitForResponse(
          (response) =>
            response.request().method() === "POST" &&
            response.url().includes(suffix),
        );
        await page
          .getByRole("button", { name: /^Salvar 2/ })
          .first()
          .click();
        expect((await saved).status()).toBe(200);
        expect(sent).toHaveLength(1);
        expect(
          (sent[0] as Record<string, unknown[]>)[
            route === "costs" ? "costs" : "minimums"
          ],
        ).toHaveLength(2);
      }
      expect(failures).toEqual([]);
    });
  }
}
