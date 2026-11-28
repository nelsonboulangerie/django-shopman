import { expect, test } from "@playwright/test";

// A escrita real é provada na API. Aqui o transporte hermético permite observar
// seleção, confirmação, uma única ida e o recibo de Desfazer nos dois temas.
for (const mobile of [false, true])
  for (const theme of ["light", "dark"] as const) {
    test(`lote fornecedores onda4-4 ${theme} ${mobile ? "mobile" : "desktop"}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize(
        mobile ? { width: 390, height: 844 } : { width: 1280, height: 720 },
      );
      const toolbar = mobile
        ? '[data-operator-bulk-bar][data-placement="base"]'
        : "[data-page-header-selection]";
      const failures: string[] = [];
      page.on("response", (response) => {
        if (response.status() >= 400)
          failures.push(`${response.status()} ${response.url()}`);
      });
      await page.addInitScript((value) => {
        localStorage.setItem("nuxt-color-mode", value);
        localStorage.setItem("purchase-nuxt-color-mode", value);
      }, theme);
      await page.emulateMedia({ colorScheme: theme });
      let calls = 0;
      let body: {
        rows: { ref: string; revision: string }[];
        isActive: boolean;
      } | null = null;
      await page.route("**/api/v1/backstage/purchase/?*", async (route) => {
        const response = await route.fetch();
        const data = await response.json();
        if (data.purchase?.suppliers?.items)
          for (const supplier of data.purchase.suppliers.items)
            supplier.revision = "2026-10-20T20:00:00+00:00";
        await route.fulfill({ response, json: data });
      });
      await page.route(
        "**/api/v1/backstage/purchase/suppliers/batch/",
        async (route) => {
          calls += 1;
          body = route.request().postDataJSON();
          await route.fulfill({
            json: {
              ok: true,
              resource: {
                count: 2,
                undo: calls === 1 ? "receipt-preview" : undefined,
                serverNow: new Date().toISOString(),
                until: new Date(Date.now() + 15000).toISOString(),
              },
            },
          });
        },
      );
      await page.goto("/base/suppliers");
      await expect(page.locator("[data-base-suppliers-table]")).toBeVisible();
      await page.screenshot({
        path: testInfo.outputPath(
          `onda4-4-fornecedores-antes-${theme}-${mobile ? "mobile" : "desktop"}.png`,
        ),
        fullPage: true,
      });
      const checks = page.locator(
        '[data-base-suppliers-table] tbody button[role="checkbox"]',
      );
      await checks.nth(0).click();
      await checks.nth(1).click();
      await expect(page.locator(toolbar)).toContainText("2 selecionados");
      await page
        .locator(`${toolbar} [data-operator-bulk-action="Arquivar"]`)
        .click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await page
        .getByRole("dialog")
        .getByRole("button", { name: "Arquivar", exact: true })
        .click();
      await expect.poll(() => calls).toBe(1);
      await expect(page.locator(toolbar)).toContainText("Desfazer");
      await expect(
        page
          .locator(toolbar)
          .getByRole("button", { name: "Desfazer", exact: true }),
      ).toBeEnabled();
      expect(body!.rows).toHaveLength(2);
      expect(body!.isActive).toBe(false);
      expect(body!.rows.every((row) => Boolean(row.revision))).toBe(true);
      await page.screenshot({
        path: testInfo.outputPath(
          `onda4-4-fornecedores-depois-${theme}-${mobile ? "mobile" : "desktop"}.png`,
        ),
        fullPage: true,
      });
      await page
        .locator(toolbar)
        .getByRole("button", { name: "Desfazer", exact: true })
        .click();
      await expect.poll(() => calls).toBe(2);
      await expect(page.locator(toolbar)).toBeHidden();
      expect(failures).toEqual([]);
    });
  }
