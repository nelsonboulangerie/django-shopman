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
  const yieldQuantityControl = page.getByRole("spinbutton", { name: "Quantidade do rendimento", exact: true });
  await expect(yieldQuantityControl).toBeVisible();
  await expect(yieldQuantityControl).toHaveClass(/w-full/);
  await expect(page.getByLabel("Unidade do rendimento")).toHaveClass(/w-full/);
  await expect(page.getByRole("textbox", { name: "Quantidade obtida", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Produto associado (SKU)")).toHaveValue("PAO-FRANCES");

  const addIngredientButton = page.getByRole("button", { name: "Adicionar ingrediente", exact: true });
  await expect(addIngredientButton).toBeVisible();
  await expect(addIngredientButton).toHaveClass(/w-full/);
  await expect(addIngredientButton).toHaveClass(/sm:w-auto/);
  await expect(page.getByLabel("Base do cálculo (100%)")).toHaveClass(/w-full/);
  await expect(page.getByLabel("Base do cálculo (100%)")).toHaveClass(/sm:w-44/);
  await expect(page.getByTestId("formula-summary")).toContainText(/Base .* · Massa total .*/);
  await expect(page.getByRole("button", { name: "Adicionar insumo", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Adicionar receita", exact: true })).toHaveCount(0);
  await addIngredientButton.click();
  await expect(page.getByLabel("Ingrediente", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Quantidade", { exact: true })).toBeVisible();
  await expect(page.getByText("Qtd", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Un", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Categoria do ingrediente", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Função no cálculo", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Ingrediente cadastrado", { exact: true })).toHaveCount(0);
  await expect(page.getByTestId("recipe-bom-items").locator(":scope > li")).toHaveCount(1);
  await expect(page.getByTestId("add-ingredient-footer")).toBeVisible();
  await expect(page.getByTestId("recipe-bom-items").locator(":scope > li").first()).toHaveAttribute("data-focus-target", "ingredient-0-picker");
  if (testInfo.project.name === "chromium-desktop") {
    await expect(page.getByPlaceholder("Buscar ingrediente", { exact: true })).toBeFocused();
  } else {
    // Touch: a lista abre e a linha vai à régua de foco sem convocar o teclado virtual.
    await expect(page.getByPlaceholder("Buscar ingrediente", { exact: true })).not.toBeFocused();
  }
  const standardizeButton = page.getByRole("button", { name: /Padronizar para/ });
  await expect(standardizeButton).toHaveClass(/w-full/);
  await expect(standardizeButton).toHaveClass(/sm:w-auto/);
  await expect(page.getByRole("option", { name: /Farinha T65/ })).toBeVisible();
  await expect(page.getByRole("option", { name: /Levain/ })).toBeVisible();
  await page.getByRole("option", { name: /Farinha T65/ }).click();
  await expect(page.getByLabel("Quantidade", { exact: true })).toBeFocused();
  await expect(page.getByText("Na fórmula", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Papel na fórmula de Farinha T65")).toContainText("Farinha");
  await expect(page.locator("[data-ingredient-formula-group]").first()).toHaveAttribute("data-slot", "root");
  await expect(page.locator("[data-ingredient-formula-group]").first().getByRole("combobox", { name: /^Composição/ })).toHaveCount(0);
  const ingredientActions = page.locator("[data-ingredient-actions]").first();
  await expect(ingredientActions.getByRole("button", { name: "Subir ingrediente" })).toBeVisible();
  await expect(ingredientActions.getByRole("button", { name: "Descer ingrediente" })).toBeVisible();
  await expect(ingredientActions.getByRole("button", { name: "Remover ingrediente" })).toBeVisible();
  const flourExpression = page.getByLabel("Quantidade de Farinha T65 expressa em");
  await expect(flourExpression).toContainText("g");
  const ingredientQuantity = page.getByLabel("Quantidade", { exact: true });
  const fixedQuantityGrid = page.locator("[data-ingredient-quantity-grid]").first();
  const [fixedQuantityBox, fixedUnitBox] = await fixedQuantityGrid
    .locator("[data-operator-field-value], [data-operator-field-context]")
    .evaluateAll((elements) => elements.map((element) => {
      const { width, y } = element.getBoundingClientRect();
      return { width, y };
    }));
  expect(Math.abs(fixedQuantityBox.y - fixedUnitBox.y)).toBeLessThanOrEqual(2);
  await flourExpression.click();
  await page.getByRole("option", { name: "kg", exact: true }).click();
  await ingredientQuantity.fill("0,002");
  await flourExpression.click();
  await page.getByRole("option", { name: "g", exact: true }).click();
  await expect(ingredientQuantity).toHaveValue("2");
  await page.getByTestId("recipe-bom-items").getByRole("button", { name: "Incrementar", exact: true }).click();
  await expect(ingredientQuantity).toHaveValue("3");
  await expect(page.getByLabel("Papel na fórmula de Farinha T65")).toBeVisible();

  await page.getByRole("button", { name: "Adicionar ingrediente", exact: true }).click();
  const ingredientPickers = page.getByLabel("Ingrediente", { exact: true });
  await expect(ingredientPickers).toHaveCount(2);
  await expect(page.getByTestId("recipe-bom-items").locator(":scope > li").last()).toHaveAttribute("data-focus-target", "ingredient-1-picker");
  if (testInfo.project.name === "chromium-desktop") {
    await expect(page.getByPlaceholder("Buscar ingrediente", { exact: true })).toBeFocused();
  }
  await page.getByPlaceholder("Buscar ingrediente", { exact: true }).fill("lev");
  await page.getByRole("option", { name: /Levain/ }).click();
  const preparationBase = page.getByLabel("Quantidade", { exact: true }).last();
  await expect(preparationBase).toBeFocused();
  const quantityGroup = page.locator("[data-ingredient-quantity-group]").last();
  const formulaGroup = page.locator("[data-ingredient-formula-group]").last();
  await expect(quantityGroup.locator("legend")).toHaveText("Quantidade");
  await expect(quantityGroup.getByText("Quanto entra na receita.", { exact: true })).toBeVisible();
  await expect(formulaGroup.getByText("Na fórmula", { exact: true })).toBeVisible();
  await expect(formulaGroup.getByText("Como este ingrediente participa.", { exact: true })).toBeVisible();
  await expect(formulaGroup.getByText("20,0% da base", { exact: true })).toBeVisible();
  await expect(formulaGroup.getByRole("combobox", { name: /^Composição/ })).toBeVisible();
  const quantityGroupBox = await quantityGroup.boundingBox();
  const formulaGroupBox = await formulaGroup.boundingBox();
  expect(quantityGroupBox).not.toBeNull();
  expect(formulaGroupBox).not.toBeNull();
  if (testInfo.project.name === "chromium-mobile-manager") {
    expect(formulaGroupBox!.y).toBeGreaterThan(quantityGroupBox!.y);
    expect(Math.abs(formulaGroupBox!.x - quantityGroupBox!.x)).toBeLessThanOrEqual(2);
  } else {
    expect(Math.abs(formulaGroupBox!.y - quantityGroupBox!.y)).toBeLessThanOrEqual(16);
    expect(formulaGroupBox!.x).toBeGreaterThan(quantityGroupBox!.x + quantityGroupBox!.width - 2);
  }
  const ratioQuantityGrid = page.locator("[data-ingredient-quantity-grid]").last();
  await expect(ratioQuantityGrid).toBeVisible();
  const [quantityColumnBox, expressionColumnBox] = await ratioQuantityGrid
    .locator("[data-operator-field-value], [data-operator-field-context]")
    .evaluateAll((elements) => elements.map((element) => {
      const { width, y } = element.getBoundingClientRect();
      return { width, y };
    }));
  expect(Math.abs(expressionColumnBox.width - quantityColumnBox.width)).toBeLessThanOrEqual(1);
  expect(await quantityGroup.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  await expect(page.getByLabel("Quantidade de Levain expressa em")).toContainText("% da base");
  await page.getByLabel("Base percentual de Levain").click();
  await page.getByRole("option", { name: "Um ingrediente", exact: true }).click();
  const basisDetailControl = page.getByLabel("Ingrediente usado como base percentual");
  await expect(basisDetailControl).toBeVisible();
  const detailBox = await basisDetailControl.locator("xpath=..").boundingBox();
  const gridBox = await ratioQuantityGrid.boundingBox();
  expect(detailBox).not.toBeNull();
  expect(gridBox).not.toBeNull();
  expect(detailBox!.width).toBe(gridBox!.width);
  await expect(page.getByText("Prep", { exact: true }).last()).toBeVisible();
  await expect(page.getByText("Versão 4", { exact: true })).toBeVisible();
  const levainCriterion = page.getByLabel("Critério da quantidade de Levain");
  await expect(levainCriterion).toContainText("Exato");
  await levainCriterion.click();
  await page.getByRole("option", { name: "Faixa", exact: true }).click();
  const rangeFields = page.locator("[data-ingredient-quantity-range] > label");
  await expect(rangeFields).toHaveCount(3);
  if (testInfo.project.name === "chromium-mobile-manager") {
    const rangeBoxes = await Promise.all([0, 1, 2].map((position) => rangeFields.nth(position).boundingBox()));
    expect(rangeBoxes.every((box) => box !== null)).toBe(true);
    expect(rangeBoxes[1]!.y).toBeGreaterThan(rangeBoxes[0]!.y);
    expect(rangeBoxes[2]!.y).toBeGreaterThan(rangeBoxes[1]!.y);
  }
  await levainCriterion.click();
  await page.getByRole("option", { name: "Exato", exact: true }).click();
  await preparationBase.fill("0,201");
  await preparationBase.blur();
  await expect(preparationBase).toHaveValue("0,2");
  await preparationBase.locator("xpath=..").getByRole("button", { name: "Incrementar", exact: true }).click();
  await expect(preparationBase).toHaveValue("0,3");
  await expect(page.getByText("Adicional soma à fórmula. Inclusa redistribui ingredientes já previstos.", { exact: true })).toBeVisible();
  await expect(page.getByText("Inclusa", { exact: true })).toBeVisible();
  await expect(page.getByTestId("recipe-bom-items").locator(":scope > li")).toHaveCount(2);
  await expect(page.getByText("Receitas usadas como ingrediente", { exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "Adicionar ingrediente", exact: true }).click();
  await page.getByPlaceholder("Buscar ingrediente", { exact: true }).fill("creme");
  await page.getByRole("option", { name: /Creme confeiteiro/ }).click();
  await expect(page.getByLabel("Quantidade", { exact: true }).last()).toBeFocused();
  await expect(page.getByText("Versão 7", { exact: true })).toBeVisible();
  await expect(page.getByTestId("recipe-bom-items").locator(":scope > li")).toHaveCount(3);

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
