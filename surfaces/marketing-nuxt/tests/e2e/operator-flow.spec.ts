import { expect, test, type Page } from "@playwright/test";

async function enterAsSyntheticOperator(page: Page) {
  await page.context().addCookies([
    {
      name: "visual_scenario",
      value: "login-anonymous",
      domain: "127.0.0.1",
      path: "/",
    },
  ]);
  await page.goto("/");
  const username = page.getByLabel("Usuário");
  await expect(username).toBeFocused();
  await username.fill("operadora-e2e");
  await page.getByLabel("Senha").fill("senha-sintética");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Painel" }),
  ).toBeVisible();
}

test("operador entra e alcança os três postos de trabalho sem redigitação", async ({
  page,
}) => {
  await enterAsSyntheticOperator(page);

  await page.getByRole("link", { name: "Campanhas", exact: true }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Campanhas" }),
  ).toBeVisible();
  await expect(page.getByText("Fornada artesanal 01")).toBeVisible();

  await page.getByRole("button", { name: "Nova campanha" }).click();
  const editor = page.getByRole("dialog").last();
  await expect(editor).toBeVisible();
  await expect(editor.getByLabel("Nome da campanha")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(editor).toBeHidden();

  await page.getByRole("link", { name: "Plataformas", exact: true }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Plataformas" }),
  ).toBeVisible();
  await expect(page.getByText("Instagram", { exact: true }).first()).toBeVisible();

  await page.getByRole("link", { name: "Painel", exact: true }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Painel" }),
  ).toBeVisible();
});
