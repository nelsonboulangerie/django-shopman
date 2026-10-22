import { expect, test } from "@playwright/test";

const cookies = [
  { name: "e2e_session", value: "authed", domain: "127.0.0.1", path: "/" },
  { name: "e2e_scenario", value: "populated", domain: "127.0.0.1", path: "/" },
];

test.beforeEach(async ({ context }) => {
  await context.addCookies(cookies);
});

test("editar receita é um gesto visível desde o inventário", async ({ page }, testInfo) => {
  test.skip(
    !["chromium-desktop", "chromium-mobile-manager"].includes(testInfo.project.name),
    "Matriz focada nos dois extremos responsivos do cadastro.",
  );

  await page.goto("/recipes");
  await page.waitForLoadState("networkidle");
  const card = page.locator("[data-recipe-card]").filter({ hasText: "Pão francês" });
  const edit = card.getByRole("link", { name: "Editar receita" });
  await expect(edit).toBeVisible();
  await edit.click();

  await expect(page).toHaveURL(/\/recipes\/pao-frances\/edit$/);
  await expect(page.getByText("Esta receita está pronta para editar.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Começar edição" })).toBeVisible();

  await testInfo.attach(`receita-editar-${testInfo.project.name}`, {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
});

test("cadastros de receita cabem, explicam o efeito e preservam a revisão", async ({ page }, testInfo) => {
  test.skip(
    !["chromium-desktop", "chromium-mobile-manager"].includes(testInfo.project.name),
    "Matriz focada nos dois extremos responsivos do cadastro.",
  );

  await page.goto("/recipes/pao-frances");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Ficha de execução ativa")).toBeVisible();

  await page.getByRole("button", { name: "Operação" }).click();
  await expect(page.getByRole("heading", { name: "Operação da ficha" })).toBeVisible();
  await expect(page.getByText("Como a receita se comporta no planejamento e no chão de produção.")).toBeVisible();
  await expect(page.getByLabel("Validade (dias)")).toHaveValue("3");
  await expect(page.getByRole("checkbox", { name: "Prazo revisado pelo responsável" })).toBeChecked();

  await page.getByLabel("Validade (dias)").fill("4");
  await expect(page.getByRole("checkbox", { name: "Prazo revisado pelo responsável" })).not.toBeChecked();
  await expect(page.getByText("Alterar os dias exige uma nova confirmação.")).toBeVisible();
  await page.getByRole("button", { name: "Fechar" }).click();
  await expect(page.getByRole("heading", { name: "Descartar o que você preencheu?" })).toBeVisible();
  await page.getByRole("button", { name: "Descartar e sair" }).click();

  await page.getByRole("button", { name: "Duplicar" }).click();
  await expect(page.getByRole("heading", { name: "Duplicar receita" })).toBeVisible();
  await expect(page.getByText("A cópia nasce como rascunho")).toBeVisible();
  await expect(page.getByText("Não cria ficha ativa nem herda capacidade, validade ou histórico de produção.")).toBeVisible();
  await expect(page.getByLabel("Nome", { exact: false })).toHaveValue("Pão francês (cópia)");

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await testInfo.attach(`receita-cadastros-${testInfo.project.name}`, {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
});
