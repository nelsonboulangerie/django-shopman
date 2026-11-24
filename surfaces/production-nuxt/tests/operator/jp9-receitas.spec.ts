import { expect, test, type Page } from "@playwright/test";

import {
  lockDevice,
  managerReleasesDevice,
  operatorUnlocksWithPin,
} from "./support/operator";
import { capture, cast, device, settled } from "./support/stack";

// J-P9 (docs/plans/EXCELENCIA-PRODUCAO-PLANO.md, seção 8; WP-F05, #3403): as receitas
// que se leem. A Gerente cria uma receita à mão, anota um ingrediente ("a conferir"),
// procura um insumo que não existe e encontra o atalho do Compras, publica com um SKU
// novo, edita e publica a segunda versão, e compara as duas lendo qual é a publicada e
// de quando. A Cozinha só lê: vê a receita e a nota, e não tem como editar nem criar.
//
// A receita nasce com nome e SKU únicos por rodada (sufixo de tempo): a jornada não
// depende de seed novo e não colide com a ficha de ninguém.
const RUN = Date.now().toString(36).toUpperCase();
const NAME = `Pão de teste J-P9 ${RUN}`;
const SKU = `JP9-${RUN}`;
const NOTE = "A conferir: no inverno a massa pede 20 g a mais.";
const MISSING = "cardamomo verde";

/** No editor, adiciona um ingrediente buscando pelo nome e escolhendo a primeira opção. */
async function addIngredient(page: Page, search: string, grams: number) {
  await page
    .getByRole("button", { name: "Adicionar ingrediente", exact: true })
    .last()
    .click();
  const box = page.getByPlaceholder("Buscar ingrediente", { exact: true });
  await box.fill(search);
  const option = page.getByRole("option", { name: new RegExp(search, "i") }).first();
  await option.click();
  const quantity = page.getByLabel("Quantidade", { exact: true }).last();
  await quantity.fill(String(grams));
  await quantity.press("Tab");
}

/** "Salvar e publicar" no editor; com SKU novo, a tela pergunta antes. Volta à receita. */
async function saveAndPublish(page: Page, testInfo: Parameters<typeof capture>[1], shot: string) {
  await page
    .getByRole("button", { name: "Salvar e publicar" })
    .first()
    .click();
  const newSku = page.getByRole("button", { name: "Publicar com SKU novo" });
  const asked = await newSku
    .waitFor({ state: "visible", timeout: 15_000 })
    .then(() => true, () => false);
  if (asked) {
    await capture(page, testInfo, shot);
    await newSku.click();
  }
  await page.waitForURL(/\/recipes\/[^/]+\?v=\d+$/);
  await settled(page);
}

test("J-P9: a receita se lê; a Cozinha só lê", async ({ browser, baseURL }, testInfo) => {
  // ── A Gerente, no balcão do escritório (tablet de 1024 px) ─────────────────
  const tabletContext = await device(browser, "tablet", baseURL!);
  const tablet = await tabletContext.newPage();
  await managerReleasesDevice(tablet);
  await lockDevice(tablet);
  await operatorUnlocksWithPin(tablet, cast.manager);

  // Cria a receita à mão.
  await tablet.goto("/recipes");
  await settled(tablet);
  await tablet.getByRole("link", { name: "Nova receita" }).first().click();
  await settled(tablet);
  await tablet.getByRole("tab", { name: "Manual" }).click();
  await tablet.getByPlaceholder("Ex.: Pão de campanha").fill(NAME);
  await tablet.getByRole("button", { name: "Abrir o editor" }).click();
  await tablet.waitForURL(/\/recipes\/[^/]+\/edit/);
  await settled(tablet);
  const ref = new URL(tablet.url()).pathname.split("/")[2]!;

  // A ficha: SKU de saída, farinha e água, e a nota da água.
  await tablet.getByLabel("Produto associado (SKU)").fill(SKU);
  await addIngredient(tablet, "Farinha", 1000);
  await addIngredient(tablet, "Água", 650);
  await tablet.getByLabel(/^Nota de .*[ÁA]gua/i).fill(NOTE);

  // Procura um insumo que não existe: o vazio leva ao Compras.
  await tablet
    .getByRole("button", { name: "Adicionar ingrediente", exact: true })
    .last()
    .click();
  await tablet.getByPlaceholder("Buscar ingrediente", { exact: true }).fill(MISSING);
  const empty = tablet.locator("[data-ingredient-empty]");
  await expect(empty).toContainText("Nenhum insumo com esse nome.");
  const purchase = empty.getByRole("link", { name: "Abrir o Compras" });
  await expect(purchase).toBeVisible();
  await expect(purchase).toHaveAttribute("href", /\/base\/materials$/);
  await capture(tablet, testInfo, "gerente-insumo-que-nao-existe-abre-o-compras");
  await tablet.keyboard.press("Escape");
  await tablet
    .locator("[data-ingredient-actions]")
    .last()
    .getByRole("button", { name: "Remover ingrediente" })
    .click();

  // Publica a versão 1 (SKU novo: a tela pergunta).
  await saveAndPublish(tablet, testInfo, "gerente-publicar-com-sku-novo");
  await expect(tablet).toHaveURL(new RegExp(`/recipes/${ref}\\?v=1$`));

  // Na receita, a nota do item se lê sob o nome do ingrediente.
  const note = tablet.locator("[data-item-note]").filter({ hasText: NOTE });
  await expect(note).toBeVisible();
  await capture(tablet, testInfo, "gerente-receita-com-a-nota-do-item");

  // Edita: a água vai a 700 g, e publica a versão 2.
  await tablet.getByRole("link", { name: "Editar", exact: true }).click();
  await tablet.waitForURL(/\/edit/);
  await settled(tablet);
  const water = tablet
    .locator("[data-testid='recipe-bom-items'] > li")
    .filter({ has: tablet.getByLabel(/^Nota de .*[ÁA]gua/i) })
    .getByLabel("Quantidade", { exact: true });
  await water.fill("700");
  await water.press("Tab");
  await saveAndPublish(tablet, testInfo, "gerente-publicar-versao-2");
  await expect(tablet).toHaveURL(new RegExp(`/recipes/${ref}\\?v=2$`));

  // Compara a 1 com a 2: cada lado diz o estado e de quando.
  await tablet.getByRole("button", { name: /Versão 1/ }).click();
  await tablet.getByRole("button", { name: "Comparar com…" }).click();
  await tablet.waitForURL(/\/recipes\/compare\?a=/);
  await settled(tablet);
  await tablet.getByText("Escolha a receita", { exact: true }).click();
  await tablet.getByPlaceholder("Buscar receita").fill(NAME);
  await tablet.getByRole("option", { name: new RegExp(NAME) }).click();
  const sideA = tablet.locator('[data-compare-side="a"]');
  const sideB = tablet.locator('[data-compare-side="b"]');
  await expect(sideA).toContainText("(versão 1)");
  await expect(sideA).toContainText("Substituída");
  await expect(sideA).toContainText(/publicada \d{2}\/\d{2}\/\d{4}/);
  await expect(sideB).toContainText("(versão 2)");
  await expect(sideB).toContainText("Publicada");
  await expect(sideB).toContainText("Atual");
  await expect(sideB).toContainText(/publicada \d{2}\/\d{2}\/\d{4}/);
  await expect(tablet.getByText("+50 g")).toBeVisible();
  await capture(tablet, testInfo, "gerente-comparar-qual-e-qual");

  // ── A Cozinha, no mesmo tablet: só lê ──────────────────────────────────────
  await lockDevice(tablet);
  await operatorUnlocksWithPin(tablet, cast.kitchen);
  await tablet.goto(`/recipes/${ref}`);
  await settled(tablet);
  await expect(tablet.locator("[data-item-note]").filter({ hasText: NOTE })).toBeVisible();
  await expect(tablet.getByRole("link", { name: "Editar", exact: true })).toHaveCount(0);
  await expect(tablet.getByRole("button", { name: "Publicar" })).toHaveCount(0);
  await capture(tablet, testInfo, "cozinha-le-a-receita");
  await tablet.goto("/recipes/new");
  await settled(tablet);
  await expect(tablet.getByText("Só leitura", { exact: true })).toBeVisible();

  await tabletContext.close();

  // ── A Gerente no celular (375 px): a mesma leitura cabe ────────────────────
  const phoneContext = await device(browser, "phone", baseURL!);
  const phone = await phoneContext.newPage();
  await managerReleasesDevice(phone);
  await lockDevice(phone);
  await operatorUnlocksWithPin(phone, cast.manager);
  await phone.goto(`/recipes/compare?a=${ref}@1&b=${ref}@2`);
  await settled(phone);
  await expect(phone.locator('[data-compare-side="b"]')).toContainText("Atual");
  await capture(phone, testInfo, "gerente-celular-comparar");
  await phone.goto(`/recipes/${ref}?v=2`);
  await settled(phone);
  await expect(phone.locator("[data-item-note]").filter({ hasText: NOTE })).toBeVisible();
  await capture(phone, testInfo, "gerente-celular-receita-com-a-nota");
  await phoneContext.close();
});
