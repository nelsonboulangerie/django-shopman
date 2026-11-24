import { expect, test } from "@playwright/test";

import {
  lockDevice,
  managerReleasesDevice,
  operatorUnlocksWithPin,
} from "./support/operator";
import { capture, cast, device, settled } from "./support/stack";

// J-P4 (docs/plans/EXCELENCIA-PRODUCAO-PLANO.md, seção 8; WP-F06): rendeu menos que o
// encomendado. A cliente encomenda Croissants para amanhã pela loja e paga; o Caixa aceita
// no Gestor; a Cozinha confirma o previsto do lote de amanhã e o finaliza com quase tudo
// de perda, de modo que rende menos que o encomendado. A tela diz quanto rendeu, quanto
// falta e quais pedidos ficam descobertos, e "Fechar com N e avisar o Gestor" fecha o lote
// com a verdade (decisão 1 do dono, 23/11/2026). O Gestor mostra o pedido em "Promessa em
// risco", com o Resolver.
//
// A loja e o Gestor são os da suíte do Gestor (os gestos da cliente e do Caixa moram em
// surfaces/orders-nuxt/tests/operator/support). Por isso a J-P4 pede, além da pilha da
// Produção, o Gestor compilado (OPERATOR_GESTOR_URL) e o log do runserver
// (OPERATOR_DJANGO_LOG), de onde sai o código de entrada da cliente. Sem eles, ela pula.
// Abre e finaliza o lote de amanhã do Croissant: roda uma vez por seed.
const PRODUCT = "Croissant";
const ORDERED = 2;

test("J-P4: rendeu menos que o encomendado, o lote fecha com a verdade", async ({
  browser,
  baseURL,
}, testInfo) => {
  test.skip(
    !process.env.OPERATOR_GESTOR_URL || !process.env.OPERATOR_DJANGO_LOG,
    "a J-P4 pede o Gestor (OPERATOR_GESTOR_URL) e o log do Django (OPERATOR_DJANGO_LOG)",
  );
  // O apoio do Gestor lê a pilha dele ao carregar; a Cozinha não entra nesta jornada.
  process.env.OPERATOR_KITCHEN_URL ??= "";
  const customer = await import(
    "../../../orders-nuxt/tests/operator/support/customer"
  );
  const gestorSupport = await import(
    "../../../orders-nuxt/tests/operator/support/gestor"
  );
  const gestorOperator = await import(
    "../../../orders-nuxt/tests/operator/support/operator"
  );
  const gestorStack = await import(
    "../../../orders-nuxt/tests/operator/support/stack"
  );
  const gestorURL = process.env.OPERATOR_GESTOR_URL!.replace(/\/$/, "");

  // ── O Gestor do balcão: o Caixa entra com PIN ──────────────────────────────
  const gestorContext = await gestorStack.roleContext(browser, gestorURL);
  const gestor = await gestorContext.newPage();
  await gestorOperator.acknowledgeOtherOrdersAlarms(gestor);
  await gestorOperator.managerSignsIn(gestor);
  await gestorOperator.managerBindsDevice(
    gestor,
    { name: "Gestor do balcão", kind: "Escritório" },
    "/workstations",
  );
  await gestor.goto("/");
  await gestorOperator.managerChoosesPosto(gestor, "Gestor do balcão");
  await gestorOperator.lockDevice(gestor);
  await gestorOperator.operatorUnlocksWithPin(gestor, cast.cashier);

  // ── A cliente encomenda para amanhã e paga ──────────────────────────────────
  const storeContext = await gestorStack.roleContext(
    browser,
    gestorStack.stack.store,
    true,
  );
  const store = await storeContext.newPage();
  const ref = await customer.customerOrdersPickupToday(store, testInfo, {
    product: PRODUCT,
    quantity: ORDERED,
    phone: gestorStack.newCustomerPhone(),
    name: "Marina",
    day: "Amanhã",
  });

  // O Caixa aceita: a reserva vai para o lote de amanhã.
  await gestorOperator.acknowledgeOtherOrdersAlarms(gestor, ref);
  await expect(gestorSupport.orderCard(gestor, ref)).toBeVisible({
    timeout: 60_000,
  });
  await gestorSupport.cashierAccepts(gestor, ref);

  // ── O tablet da bancada: a Cozinha abre o lote de amanhã ───────────────────
  const tomorrow = new Date(Date.now() + 24 * 3600 * 1000).toLocaleDateString(
    "en-CA",
    { timeZone: "America/Sao_Paulo" },
  );
  const tabletContext = await device(browser, "tablet", baseURL!);
  const tablet = await tabletContext.newPage();
  await managerReleasesDevice(tablet);
  await lockDevice(tablet);
  await operatorUnlocksWithPin(tablet, cast.kitchen);
  await tablet.goto(`/?date=${tomorrow}`);
  await settled(tablet);
  const open = tablet
    .getByRole("button", { name: `Confirmar ${PRODUCT}`, exact: true })
    .first();
  await expect(
    open,
    `o lote de amanhã do ${PRODUCT} já não está a confirmar: a J-P4 roda uma vez por seed`,
  ).toBeVisible();
  await open.click();
  const panel = tablet.getByRole("complementary", {
    name: "Confirmar o previsto",
  });
  const expected = Number(
    (
      await panel
        .getByRole("textbox", { name: "Quantidade prevista" })
        .inputValue()
    ).replace(",", "."),
  );
  expect(expected, "o previsto nasce do planejado").toBeGreaterThan(ORDERED);
  await panel.getByRole("button", { name: /^Confirmar \d/ }).click();
  await expect(panel).toBeHidden();

  // ── Finalização: rende 1, menos que o encomendado ──────────────────────────
  const loss = expected - 1;
  await tablet.goto(`/close?date=${tomorrow}`);
  await settled(tablet);
  await tablet
    .getByRole("button", { name: `Finalizar o lote de ${PRODUCT}` })
    .first()
    .click();
  await expect(tablet.getByText(`${expected} previstos`)).toBeVisible();
  await tablet.getByRole("button", { name: /^Perda: \d+ unidades$/ }).click();
  for (const digit of String(loss)) {
    await tablet
      .getByRole("button", { name: `Dígito ${digit}`, exact: true })
      .click();
  }
  await expect(
    tablet.getByRole("button", { name: `Perda: ${loss} unidades` }),
  ).toBeVisible();
  await tablet
    .getByRole("button", { name: "Finalizar", exact: true })
    .locator("visible=true")
    .first()
    .click();
  // O motivo principal da perda, em um toque.
  const reasonSheet = tablet.getByRole("dialog");
  await expect(
    reasonSheet.getByText(`Qual o motivo principal da perda de ${loss}?`),
  ).toBeVisible();
  await reasonSheet.getByRole("button", { name: /^Assou demais/ }).click();

  // A pergunta do lote curto: quanto rendeu, quanto falta e quem fica descoberto.
  const shortLot = tablet.getByRole("dialog", {
    name: "Rendeu menos que o encomendado",
  });
  await expect(shortLot).toBeVisible();
  await expect(shortLot.getByText(/^Rendeu 1\. Faltam \d+ para as encomendas\.$/)).toBeVisible();
  await expect(shortLot.getByText(ref)).toBeVisible();
  await expect(shortLot.getByText("pelo menos")).toHaveCount(0);
  await capture(tablet, testInfo, "producao-rendeu-menos");
  await shortLot
    .getByRole("button", { name: "Fechar com 1 e avisar o Gestor" })
    .click();
  await expect(shortLot).toBeHidden();
  await expect(
    tablet.getByRole("button", { name: `Finalizar o lote de ${PRODUCT}` }),
  ).toHaveCount(0);
  await capture(tablet, testInfo, "producao-lote-fechado");

  // ── O Gestor: o pedido em "Promessa em risco", com o Resolver ──────────────
  await gestor.goto(`/${ref}`);
  await expect(async () => {
    await gestor.reload();
    await settled(gestor);
    await expect(
      gestor.getByText("Promessa em risco").filter({ visible: true }).first(),
    ).toBeVisible({ timeout: 5_000 });
  }).toPass({ timeout: 90_000 });
  await expect(
    gestor.getByText(PRODUCT).filter({ visible: true }).first(),
  ).toBeVisible();
  await expect(
    gestor.getByRole("button", { name: /Resolver/ }).filter({ visible: true }).first(),
  ).toBeVisible();
  await capture(gestor, testInfo, "gestor-promessa-em-risco");

  await tabletContext.close();
  await storeContext.close();
  await gestorContext.close();
});
