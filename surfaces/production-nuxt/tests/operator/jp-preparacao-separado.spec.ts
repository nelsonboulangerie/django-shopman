import { expect, test, type Locator, type Page } from "@playwright/test";

import {
  lockDevice,
  managerReleasesDevice,
  operatorUnlocksWithPin,
} from "./support/operator";
import { capture, cast, device, settled } from "./support/stack";

// WP-F09b (#3525): a Preparação lembra. O "Separado" mora no servidor e vale para a
// bancada inteira (D-042, item 5): a Cozinha marca três insumos no tablet A, e o tablet
// B, aberto na mesma tela, mostra as três marcas sem recarregar; ligar "Mostrar
// ingredientes dos pré-preparos" não as apaga; na lente "Por preparo" a Cozinha marca os
// ingredientes de uma massa; a etiqueta de pesagem traz o mesmo peso do cartão; e, no
// celular, a Gerente lê quanto falta de um insumo e encontra "Pedir no Compras".
//
// Marca e desmarca: a jornada devolve as marcas ao fim, então roda quantas vezes quiser
// no mesmo seed.

async function openPreparation(page: Page, lens: "Por insumo" | "Por preparo") {
  await page.goto("/mise-en-place");
  await settled(page);
  await page.getByRole("tab", { name: lens }).click();
  await settled(page);
}

function lineRows(page: Page): Locator {
  return page.locator("[data-mise-lines] tbody tr").filter({ has: page.getByRole("checkbox") });
}

async function markedCount(page: Page): Promise<number> {
  return page.locator('[data-mise-lines] [role="checkbox"][aria-checked="true"]').count();
}

test("Preparação: o Separado vale para a bancada inteira", async ({ browser, baseURL }, testInfo) => {
  // ── Dois tablets da bancada, a Cozinha com PIN nos dois ──────────────────────
  const contextA = await device(browser, "tablet", baseURL!);
  const tabletA = await contextA.newPage();
  await managerReleasesDevice(tabletA);
  await lockDevice(tabletA);
  await operatorUnlocksWithPin(tabletA, cast.kitchen);

  const contextB = await device(browser, "tablet", baseURL!);
  const tabletB = await contextB.newPage();
  await managerReleasesDevice(tabletB);
  await lockDevice(tabletB);
  await operatorUnlocksWithPin(tabletB, cast.kitchen);

  await openPreparation(tabletA, "Por insumo");
  await openPreparation(tabletB, "Por insumo");
  await expect(tabletA.getByText(/somente neste dispositivo|somente nesta estação/)).toHaveCount(0);
  const before = await markedCount(tabletB);

  // A Cozinha marca três insumos no tablet A.
  const rowsA = lineRows(tabletA);
  const picked: string[] = [];
  for (let index = 0; picked.length < 3; index += 1) {
    const row = rowsA.nth(index);
    const box = row.getByRole("checkbox");
    if ((await box.getAttribute("aria-checked")) === "true") continue;
    picked.push(((await row.locator("td").nth(1).locator("span").first().textContent()) ?? "").trim());
    await box.click();
    await expect(box).toHaveAttribute("aria-checked", "true");
  }
  await expect(tabletA.locator("[data-prep-mark-author]").first()).toContainText("Separado por");
  await capture(tabletA, testInfo, "tablet-a-cozinha-marca-tres-insumos");

  // O tablet B mostra as três marcas sem recarregar (SSE do canal production).
  await expect.poll(() => markedCount(tabletB), { timeout: 20_000 }).toBe(before + 3);
  for (const name of picked) {
    const row = lineRows(tabletB).filter({ hasText: name }).first();
    await expect(row.getByRole("checkbox")).toHaveAttribute("aria-checked", "true");
  }
  await capture(tabletB, testInfo, "tablet-b-ve-as-marcas-sem-recarregar");

  // Ligar os ingredientes dos pré-preparos não apaga as marcas.
  await tabletB.getByText("Mostrar ingredientes dos pré-preparos").click();
  await settled(tabletB);
  await tabletB.getByText("Mostrar ingredientes dos pré-preparos").click();
  await settled(tabletB);
  for (const name of picked) {
    const row = lineRows(tabletB).filter({ hasText: name }).first();
    await expect(row.getByRole("checkbox")).toHaveAttribute("aria-checked", "true");
  }
  await capture(tabletB, testInfo, "tablet-b-marcas-ficam-ao-mostrar-os-pre-preparos");

  // ── "Por preparo": a Cozinha marca os ingredientes de uma massa ─────────────
  await openPreparation(tabletA, "Por preparo");
  const card = tabletA.locator("article").first();
  const boxes = card.getByRole("checkbox");
  const total = await boxes.count();
  for (let index = 0; index < total; index += 1) {
    const box = boxes.nth(index);
    if ((await box.getAttribute("aria-checked")) !== "true") await box.click();
    await expect(box).toHaveAttribute("aria-checked", "true");
  }
  await expect(card.locator("[data-ticket-progress]")).toHaveText(`${total}/${total} separados`);
  await capture(tabletA, testInfo, "tablet-a-por-preparo-massa-separada");

  // A etiqueta de pesagem traz o mesmo peso do cartão.
  const cardWeights = await card.locator("ul li .tabular-nums").allTextContents();
  await card.getByRole("button", { name: /Abrir etiquetas de pesagem de/ }).click();
  const dialog = tabletA.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await settled(tabletA);
  const preview = await dialog.locator(".tabular-nums").allTextContents();
  for (const weight of preview.filter((text) => /\d\s?(g|kg|ml|L|un)/.test(text))) {
    expect(cardWeights.map((text) => text.trim())).toContain(weight.trim());
  }
  await capture(tabletA, testInfo, "tablet-a-etiqueta-com-o-peso-do-cartao");
  await tabletA.keyboard.press("Escape");

  // ── No celular, a Gerente lê a falta e encontra o Compras ───────────────────
  const phoneContext = await device(browser, "phone", baseURL!);
  const phone = await phoneContext.newPage();
  await managerReleasesDevice(phone);
  await lockDevice(phone);
  await operatorUnlocksWithPin(phone, cast.manager);
  await openPreparation(phone, "Por insumo");
  const shortage = phone.locator("[data-prep-shortage]").first();
  await expect(shortage).toHaveText(/^Faltam \d/);
  const shortRow = phone.locator("[data-mise-lines] tbody tr").filter({ has: shortage }).first();
  await expect(shortRow.getByRole("link", { name: "Pedir no Compras" })).toBeVisible();
  await shortRow.scrollIntoViewIfNeeded();
  await capture(phone, testInfo, "celular-gerente-faltam-e-pedir-no-compras");
  await phone.locator("[data-mise-lines] tbody tr").filter({ hasText: picked[0]! }).first().scrollIntoViewIfNeeded();
  await capture(phone, testInfo, "celular-gerente-ve-o-separado-da-bancada");

  // Devolve a bancada como estava: desmarca o que a jornada marcou.
  for (const name of picked) {
    const box = lineRows(tabletB).filter({ hasText: name }).first().getByRole("checkbox");
    await box.click();
    await expect(box).toHaveAttribute("aria-checked", "false");
  }
  await openPreparation(tabletA, "Por preparo");
  const again = tabletA.locator("article").first().getByRole("checkbox");
  for (let index = 0; index < total; index += 1) {
    const box = again.nth(index);
    await box.click();
    await expect(box).toHaveAttribute("aria-checked", "false");
  }

  await phoneContext.close();
  await contextB.close();
  await contextA.close();
});
