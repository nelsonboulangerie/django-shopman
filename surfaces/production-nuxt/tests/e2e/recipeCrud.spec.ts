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
  const edit = card.getByRole("link", { name: "Editar Pão francês" });
  await expect(edit).toBeVisible();
  await edit.click();

  await expect(page).toHaveURL(/\/recipes\/pao-frances\/edit\?v=3$/);
  await expect(page.locator("[data-page-header-eyebrow]:visible, [data-page-header-eyebrow-phone]:visible")).toContainText("Rascunho · Versão 3");
  await expect(page.getByRole("button", { name: "Salvar rascunho" })).toBeVisible();

  await testInfo.attach(`receita-editar-${testInfo.project.name}`, {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
});

test("cadastros de receita cabem, explicam o efeito e preservam a revisão", async ({ page }, testInfo) => {
  test.setTimeout(60_000);
  test.skip(
    !["chromium-desktop", "chromium-mobile-manager"].includes(testInfo.project.name),
    "Matriz focada nos dois extremos responsivos do cadastro.",
  );

  await page.goto("/recipes/pao-frances");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Ficha técnica", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Configuração da produção" })).toBeVisible();

  await page.getByRole("link", { name: "Editar", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Informações da receita" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Rendimento", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Resultado da receita" })).toHaveCount(0);
  await expect(page.getByRole("textbox", { name: "Quantidade", exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Quantidade obtida", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Produto associado (SKU)")).toHaveValue("PAO-FRANCES");

  await expect(page.getByRole("button", { name: "Adicionar ingrediente", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Adicionar insumo", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Adicionar receita", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Adicionar ingrediente", exact: true }).click();
  await expect(page.getByLabel("Ingrediente", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Quantidade", { exact: true })).toBeVisible();
  await expect(page.getByText("Qtd", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Un", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel(/Categoria de ingrediente/)).toHaveCount(1);
  await expect(page.getByText("Função no cálculo", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Ingrediente cadastrado", { exact: true })).toHaveCount(0);
  await expect(page.getByTestId("recipe-bom-items").locator(":scope > li")).toHaveCount(1);
  const standardizeButton = page.getByRole("button", { name: /Padronizar para/ });
  await expect(standardizeButton).toHaveClass(/w-full/);
  await expect(standardizeButton).toHaveClass(/sm:w-auto/);
  await page.getByLabel("Ingrediente", { exact: true }).click();
  await expect(page.getByRole("option", { name: /Farinha T65/ })).toBeVisible();
  await expect(page.getByRole("option", { name: /Levain/ })).toBeVisible();
  await page.getByPlaceholder("Buscar ingrediente", { exact: true }).fill("lev");
  await page.getByRole("option", { name: /Levain/ }).click();
  await expect(page.getByLabel("Função da receita usada como ingrediente")).toBeVisible();
  await expect(page.getByTestId("recipe-bom-items").locator(":scope > li")).toHaveCount(1);
  await expect(page.getByText("Receitas usadas como ingrediente", { exact: true })).toHaveCount(0);

  await page.getByRole("tab", { name: "Modo de preparo" }).click();
  await expect(page.getByRole("heading", { name: "Modo de preparo" })).toBeVisible();
  await expect(page.getByText("Registre cada etapa com instrução, tempo, temperatura e ponto de referência.")).toBeVisible();

  await page.getByRole("tab", { name: "Produção" }).click();
  await expect(page.getByRole("heading", { name: "Configuração da produção" })).toBeVisible();
  await expect(page.getByText("Como a receita ocupa a produção e quando um lote exige atenção.")).toBeVisible();
  await expect(page.getByLabel("Validade (dias)")).toHaveValue("3");
  await expect(page.getByRole("checkbox", { name: "Prazo revisado pelo responsável" })).toBeChecked();

  await page.getByLabel("Validade (dias)").fill("4");
  await expect(page.getByRole("checkbox", { name: "Prazo revisado pelo responsável" })).not.toBeChecked();
  await expect(page.getByText("Alterar os dias exige uma nova confirmação.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Salvar configuração" })).toBeVisible();

  await page.getByRole("link", { name: "Voltar", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sair sem salvar a receita?" })).toBeVisible();
  await page.getByRole("button", { name: "Sair sem salvar" }).click();
  await page.getByRole("button", { name: "Mais ações", exact: true }).click();
  await page.getByRole("menuitem", { name: "Duplicar receita", exact: true }).click();
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
