import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

const phase = process.env.GRID_SCOPE_PHASE || "after";
for (const theme of ["light", "dark"] as const) {
  test(`rascunho oculto do custo ${theme}`, async ({ page }) => {
    const failures: string[] = [];
    page.on("response", (response) => {
      if (response.status() >= 400)
        failures.push(`${response.status()} ${response.url()}`);
    });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.addInitScript(
      (theme) => localStorage.setItem("purchase-nuxt-color-mode", theme),
      theme,
    );
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/base/costs");
    await expect(page.locator("[data-cost-batch-table]")).toBeVisible();
    await expect(page.locator("html")).toHaveClass(new RegExp(theme));
    await page.locator("[data-cost-batch-supplier]").click();
    await page
      .getByRole("option", { name: "Moinho Paraná", exact: true })
      .click();
    await page
      .getByRole("textbox", {
        name: "Valor de Creme de leite fresco 35%",
        exact: true,
      })
      .fill("inválido");
    await page
      .getByRole("textbox", {
        name: "Valor de Chocolate amargo 70% em gotas para forno",
        exact: true,
      })
      .fill("12,50");
    await page.locator("[data-suite-search-input]").click();
    await page
      .getByPlaceholder("Buscar insumo na tabela", { exact: true })
      .fill("Chocolate");
    await page
      .getByRole("option", {
        name: "Filtrar a tabela do fornecedor por “Chocolate”",
        exact: true,
      })
      .click();
    await page.waitForTimeout(500);
    const save = page.getByRole("button", {
      name: "Salvar 1 como padrão",
      exact: true,
    });
    const out = resolve(
      "../../docs/coordination/EVIDENCE/ONDA4-3F-rascunhos-filtrados",
    );
    mkdirSync(out, { recursive: true });
    await page.screenshot({
      path: resolve(out, `${phase}-filtered-cost-${theme}.png`),
      fullPage: true,
    });
    // Antes da correção, o valor válido visível fica bloqueado pelo erro escondido.
    await expect(save).toBeEnabled({ timeout: 1000 });
    const request = page.waitForRequest(
      (request) =>
        request.method() === "POST" && request.url().includes("/costs/batch/"),
    );
    await save.click();
    const sent = (await request).postDataJSON();
    expect(sent.costs).toEqual([
      { materialSku: "CHOC-70", costInput: "12,50", conversionId: null },
    ]);
    await expect(
      page.getByRole("textbox", {
        name: "Valor de Chocolate amargo 70% em gotas para forno",
        exact: true,
      }),
    ).toHaveValue("");
    await page.locator("[data-suite-search-input]").click();
    await page
      .getByRole("option", {
        name: "Tirar o filtro “Chocolate” da tabela do fornecedor",
        exact: true,
      })
      .click();
    const hidden = page.getByRole("textbox", {
      name: "Valor de Creme de leite fresco 35%",
      exact: true,
    });
    await expect(hidden).toHaveValue("inválido");
    await expect(
      page.getByText("Informe um valor de compra maior que zero."),
    ).toBeVisible();
    await page.screenshot({
      path: resolve(out, `${phase}-preserved-draft-${theme}.png`),
      fullPage: true,
    });
    await page.getByRole("button", { name: "Desfazer", exact: true }).click();
    await expect(hidden).toHaveValue("");
    expect(failures).toEqual([]);
  });
}
