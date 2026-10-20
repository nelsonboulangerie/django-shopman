import { expect, test } from "@playwright/test";

// /recipes/sheets caía em 500 ao abrir: a opção "Todas" do filtro de situação tinha
// valor vazio, e o Select do Nuxt UI (Reka) recusa item de valor vazio. A tela tem de
// abrir e o filtro tem de trocar sem erro.

const cookies = [{ name: "e2e_session", value: "authed", domain: "127.0.0.1", path: "/" }];

test.beforeEach(async ({ context }) => {
  await context.addCookies(cookies);
});

test("as fichas de execução abrem e o filtro de situação troca sem erro", async ({ page }, testInfo) => {
  test.skip(
    !["chromium-desktop", "chromium-mobile-manager"].includes(testInfo.project.name),
    "Matriz focada nos dois extremos responsivos do cadastro.",
  );
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/recipes/sheets");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Internal Server Error")).toHaveCount(0);
  const situation = page.getByRole("combobox", { name: "Situação da ficha" });
  await expect(situation).toContainText("Todas");

  await situation.click();
  await page.getByRole("option", { name: "Inativas" }).click();
  await expect(situation).toContainText("Inativas");
  await situation.click();
  await page.getByRole("option", { name: "Todas" }).click();
  await expect(situation).toContainText("Todas");
  expect(pageErrors).toEqual([]);
});
