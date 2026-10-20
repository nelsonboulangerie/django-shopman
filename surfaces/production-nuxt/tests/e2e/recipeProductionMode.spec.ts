import { expect, test } from "@playwright/test";

// ADR-040: o modo de produção da receita, "Em lote" ou "Na hora". A lista de
// fichas mostra o selo e o recorte; a ficha tem o seletor com a linha de ajuda; o
// corpo leva `productionMode`. Nada aqui usa "Arquivada" para dizer "Na hora".

const cookies = [
  { name: "e2e_session", value: "authed", domain: "127.0.0.1", path: "/" },
  { name: "e2e_scenario", value: "populated", domain: "127.0.0.1", path: "/" },
];

test.beforeEach(async ({ context }) => {
  await context.addCookies(cookies);
});

test("o dono vê o que é feito na hora e troca o modo na ficha", async ({ page }, testInfo) => {
  test.skip(
    !["chromium-desktop", "chromium-mobile-manager"].includes(testInfo.project.name),
    "Matriz focada nos dois extremos responsivos do cadastro.",
  );
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/recipes/sheets");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Na hora").first()).toBeVisible();

  const mode = page.getByRole("combobox", { name: "Modo de produção" });
  await mode.click();
  await page.getByRole("option", { name: "Na hora" }).click();
  await expect(page.getByText("Pão francês")).toHaveCount(0);
  await expect(page.getByText("Espresso", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Croque Monsieur", { exact: true }).first()).toBeVisible();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await testInfo.attach(`fichas-na-hora-${testInfo.project.name}`, {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });

  // O bechamel é em lote: a ficha dele troca para Na hora e o corpo leva o modo.
  await mode.click();
  await page.getByRole("option", { name: "Em lote" }).click();
  await expect(page.getByText("Molho bechamel", { exact: true }).first()).toBeVisible();
  await page.goto("/recipes/sheets?open=molho-bechamel");
  await page.waitForLoadState("networkidle");
  const group = page.getByRole("radiogroup").filter({ hasText: "Em lote" });
  await expect(group).toBeVisible();
  await expect(page.getByText("Em lote: planejado e estocado. Na hora: feito quando vende, baixa os insumos na venda.")).toBeVisible();
  await expect(page.getByRole("radio", { name: "Em lote" })).toBeChecked();
  await page.getByRole("radio", { name: "Na hora" }).click();
  await expect(page.getByRole("radio", { name: "Na hora" })).toBeChecked();
  const saved = page.waitForResponse((response) => response.url().includes("/recipes/sheets/molho-bechamel/") && response.request().method() === "PATCH");
  await page.getByRole("button", { name: "Salvar ficha" }).click();
  const response = await saved;
  expect(response.status()).toBe(200);
  expect(response.request().postDataJSON()).toMatchObject({ productionMode: "made_to_order", is_active: true });
  expect(pageErrors).toEqual([]);
});
