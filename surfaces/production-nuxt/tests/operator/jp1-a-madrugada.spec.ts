import { expect, test } from "@playwright/test";

import {
  lockDevice,
  managerReleasesDevice,
  operatorUnlocksWithPin,
} from "./support/operator";
import { capture, cast, device, settled, stack } from "./support/stack";

// J-P1 (docs/plans/EXCELENCIA-PRODUCAO-PLANO.md, seção 8; WP-F00): a madrugada.
// A Gerente libera o tablet da bancada; a Cozinha entra com o PIN dela, confirma o previsto
// do lote do Pain au Chocolat de hoje e o finaliza com 2 de perda e o motivo; a Gerente,
// com o PIN dela, confirma a Qualidade pelo celular; e a loja mostra o Pain au Chocolat
// pronto para a cliente.
//
// O lote é o de HOJE do Pain au Chocolat, planejado pelo seed e que nenhuma jornada do
// Gestor toca (a J6 cancela o de amanhã). Como a jornada abre e finaliza o lote do dia,
// ela roda uma vez por seed: na segunda, o lote já não está para confirmar.
const PRODUCT = "Pain au Chocolat";
const SKU = "PCHOC";
const LOSS = 2;
// Um dos motivos de perda do seed (QUALITY_DEFECTS, em config/management/commands/seed.py).
const REASON = "Assou demais";

test("J-P1: a madrugada, do previsto à loja", async ({
  browser,
  baseURL,
}, testInfo) => {
  // ── O tablet da bancada (1024 px, toque) ────────────────────────────────────
  const tabletContext = await device(browser, "tablet", baseURL!);
  const tablet = await tabletContext.newPage();
  await managerReleasesDevice(tablet);
  await capture(tablet, testInfo, "tablet-liberado");

  // A Gerente trava; quem opera o chão se identifica com o PIN.
  await lockDevice(tablet);
  await operatorUnlocksWithPin(tablet, cast.kitchen);

  // Produção: o lote planejado de hoje espera o previsto.
  await tablet.goto("/");
  await settled(tablet);
  const open = tablet
    .getByRole("button", { name: `Confirmar ${PRODUCT}`, exact: true })
    .first();
  await expect(
    open,
    `o lote de hoje do ${PRODUCT} já não está a confirmar: a J-P1 roda uma vez por seed (rode o seed de novo)`,
  ).toBeVisible();
  await open.click();
  const panel = tablet.getByRole("complementary", {
    name: "Confirmar o previsto",
  });
  await expect(panel).toBeVisible();
  await expect(panel.getByText(PRODUCT).first()).toBeVisible();
  const planned = await panel
    .getByRole("textbox", { name: "Quantidade prevista" })
    .inputValue();
  const expected = Number(planned.replace(",", "."));
  expect(expected, "o previsto nasce do planejado").toBeGreaterThan(LOSS);
  await capture(tablet, testInfo, "producao-quanto-esta-previsto");
  await panel.getByRole("button", { name: /^Confirmar \d/ }).click();
  await expect(panel).toBeHidden();

  // Finalização: 2 de perda, com o motivo.
  await tablet.goto("/close");
  await settled(tablet);
  await tablet
    .getByRole("button", { name: `Finalizar o lote de ${PRODUCT}` })
    .first()
    .click();
  await expect(tablet.getByText(`${expected} previstos`)).toBeVisible();
  await tablet.getByRole("button", { name: /^Perda: \d+ unidades$/ }).click();
  await tablet
    .getByRole("button", { name: `Dígito ${LOSS}`, exact: true })
    .click();
  await expect(
    tablet.getByRole("button", { name: `Perda: ${LOSS} unidades` }),
  ).toBeVisible();
  await capture(tablet, testInfo, "finalizacao-perda");
  await tablet
    .getByRole("button", { name: "Finalizar", exact: true })
    .locator("visible=true")
    .first()
    .click();
  // A tela pergunta o motivo principal da perda; ela nunca o escreve pelo operador.
  const reason = tablet.getByRole("dialog");
  await expect(
    reason.getByText(`Qual o motivo principal da perda de ${LOSS}?`),
  ).toBeVisible();
  // A folha sobe da base: a captura espera o motivo estar na tela.
  const reasonChoice = reason.getByRole("button", {
    name: new RegExp(`^${REASON}`),
  });
  await expect(reasonChoice).toBeInViewport();
  await capture(tablet, testInfo, "finalizacao-motivo-da-perda");
  await reasonChoice.click();
  await expect(
    tablet.getByRole("button", { name: `Finalizar o lote de ${PRODUCT}` }),
  ).toHaveCount(0);
  await capture(tablet, testInfo, "finalizacao-lote-finalizado");

  // ── O celular da Gerente (375 px) ───────────────────────────────────────────
  // Ela confere a Qualidade de longe: o lote com perda é exceção, e ela confirma assim.
  const phoneContext = await device(browser, "phone", baseURL!);
  const phone = await phoneContext.newPage();
  await managerReleasesDevice(phone);
  await lockDevice(phone);
  await operatorUnlocksWithPin(phone, cast.manager);
  await phone.goto("/quality");
  await settled(phone);
  const confirm = phone.getByRole("button", {
    name: `Confirmar a qualidade do lote de ${PRODUCT} assim`,
  });
  await expect(confirm.first()).toBeVisible();
  // O lote com perda vem depois dos sem exceção: ela rola até ele.
  await confirm.first().scrollIntoViewIfNeeded();
  await capture(phone, testInfo, "qualidade-excecao");
  await confirm.first().click();
  await expect(confirm).toHaveCount(0);
  await capture(phone, testInfo, "qualidade-confirmada");

  // ── A loja, no celular da cliente (375 px) ─────────────────────────────────
  const storeContext = await device(browser, "phone", stack.store);
  const store = await storeContext.newPage();
  await store.goto(`/produto/${SKU}`);
  await settled(store);
  await expect(
    store.getByRole("heading", { name: PRODUCT, level: 1 }),
  ).toBeVisible();
  await expect(store.getByText("Pronto agora").first()).toBeVisible();
  await expect(store.getByText("Indisponível")).toHaveCount(0);
  await capture(store, testInfo, "loja-pronto-agora");

  await storeContext.close();
  await phoneContext.close();
  await tabletContext.close();
});
