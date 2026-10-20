import { expect, test } from "@playwright/test";

for (const entity of ["materials", "suppliers"] as const)
  for (const theme of ["light", "dark"] as const)
    for (const mobile of [false, true]) {
      test(`onda4-5 CSV ${entity} ${theme} ${mobile ? "mobile" : "desktop"}`, async ({
        page,
      }, testInfo) => {
        await page.setViewportSize(
          mobile ? { width: 390, height: 844 } : { width: 1280, height: 720 },
        );
        const errors: string[] = [];
        page.on("response", (response) => {
          if (response.status() >= 400)
            errors.push(`${response.status()} ${response.url()}`);
        });
        await page.addInitScript((value) => {
          localStorage.setItem("nuxt-color-mode", value);
          localStorage.setItem("purchase-nuxt-color-mode", value);
        }, theme);
        await page.emulateMedia({ colorScheme: theme });
        const csv =
          entity === "materials"
            ? "SKU;Nome;Unidade;Mínimo\nNOVO;Farinha nova;kg;1,5"
            : "Referência;Razão social\nnovo;Moinho novo";
        let writes = 0;
        await page.route(
          `**/api/v1/backstage/purchase/${entity}/csv/`,
          async (route) => {
            if (route.request().method() === "GET") {
              await route.fulfill({
                json: {
                  table: {
                    header: [
                      entity === "materials" ? "SKU" : "Referência",
                      "Nome",
                    ],
                    rows: [["NOVO", "Cadastro de exemplo"]],
                  },
                },
              });
              return;
            }
            const body = route.request().postDataJSON();
            if (body.preview) {
              await route.fulfill({
                json: {
                  preview: {
                    rows: 1,
                    totals: { new: 1, update: 0 },
                    errors: [],
                    changes: [
                      {
                        ref: "NOVO",
                        name: "Cadastro de exemplo",
                        action: "Criar",
                      },
                    ],
                    base_revision: "signed-preview",
                  },
                },
              });
              return;
            }
            writes += 1;
            expect(body.csv).toBe(csv);
            expect(body.base_revision).toBe("signed-preview");
            expect(route.request().headers()["idempotency-key"]).toBeTruthy();
            await route.fulfill({ json: { ok: true, outcome: "applied" } });
          },
        );
        await page.goto(`/base/${entity}`);
        await expect(
          page.locator(
            entity === "materials"
              ? "[data-base-table]"
              : "[data-base-suppliers-table]",
          ),
        ).toBeVisible();
        await page.screenshot({
          path: testInfo.outputPath(
            `onda4-5-${entity}-antes-${theme}-${mobile ? "mobile" : "desktop"}.png`,
          ),
          fullPage: true,
          animations: "disabled",
        });
        await page
          .getByRole("button", { name: "Mais ações da Base", exact: true })
          .click();
        await page
          .getByRole("menuitem", { name: "Importar CSV", exact: true })
          .click();
        await page
          .locator('input[type="file"]')
          .setInputFiles({
            name: "base.csv",
            mimeType: "text/csv",
            buffer: Buffer.from(csv),
          });
        await expect(page.locator("[data-import-preview]")).toContainText(
          "Cadastro de exemplo",
        );
        await expect(page.locator("[data-import-apply]")).toBeEnabled();
        expect(writes).toBe(0);
        await page.waitForTimeout(500);
        await page.screenshot({
          path: testInfo.outputPath(
            `onda4-5-${entity}-depois-${theme}-${mobile ? "mobile" : "desktop"}.png`,
          ),
          fullPage: true,
          animations: "disabled",
        });
        await page.locator("[data-import-apply]").click();
        await expect(page.locator("[data-import-apply]")).toBeHidden();
        expect(writes).toBe(1);
        await page
          .getByRole("button", { name: "Mais ações da Base", exact: true })
          .click();
        await page
          .getByRole("menuitem", { name: "Exportar CSV", exact: true })
          .click();
        await expect(
          page.getByRole("button", { name: "Baixar CSV", exact: true }),
        ).toBeVisible();
        await expect(
          page.getByText("O arquivo inclui todos os cadastros da Base", {
            exact: false,
          }),
        ).toBeVisible();
        await page.waitForTimeout(500);
        await page.screenshot({
          path: testInfo.outputPath(
            `onda4-5-${entity}-export-${theme}-${mobile ? "mobile" : "desktop"}.png`,
          ),
          fullPage: true,
          animations: "disabled",
        });
        const download = page.waitForEvent("download");
        await page
          .getByRole("button", { name: "Baixar CSV", exact: true })
          .click();
        expect((await download).suggestedFilename()).toMatch(
          new RegExp(`^${entity}-.*\\.csv$`),
        );
        expect(errors).toEqual([]);
      });
    }
