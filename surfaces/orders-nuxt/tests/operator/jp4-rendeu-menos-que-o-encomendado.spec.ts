import { expect, test } from "@playwright/test";
import { customerOrdersPickupToday } from "./support/customer";
import { cashierAccepts, orderCard } from "./support/gestor";
import {
  acknowledgeOtherOrdersAlarms,
  lockDevice,
  managerBindsDevice,
  managerChoosesPosto,
  managerSignsIn,
} from "./support/operator";
import { capture, cast, newCustomerPhone, roleContext, settled, stack } from "./support/stack";
// O PIN entra no quarto número, no Gestor e na Produção: o gesto do kit ainda espera o
// "4 de no mínimo" e o Confirmar, que não chegam a aparecer. O gesto da Produção
// (WP-F00) confirma só se a tela pedir.
import { operatorUnlocksWithPin } from "../../../production-nuxt/tests/operator/support/operator";

// J-P4 (docs/plans/EXCELENCIA-PRODUCAO-PLANO.md, seção 8; WP-F06): rendeu menos que o
// encomendado. A cliente encomenda 2 Ciabattas para amanhã pela loja e paga; o Caixa
// aceita; a Cozinha confirma o previsto do lote de amanhã e o finaliza rendendo 1, com o
// resto de perda e o motivo. A tela diz quanto rendeu, quanto falta e quais pedidos ficam
// descobertos, e "Fechar com 1" fecha o lote com a verdade (decisão 1 do
// dono, 23/11/2026): o pão entra no estoque e o Gestor mostra o pedido em "Promessa em
// risco", com o Resolver.
//
// Mora na suíte do Gestor, como a J6, porque cruza a loja, o Gestor e a Produção com os
// gestos da cliente e do Caixa que moram aqui. Pede a Produção na pilha
// (OPERATOR_PRODUCTION_URL) e pula sem ela. Abre e finaliza o lote de amanhã da
// Ciabatta, que o seed só planeja para amanhã e nenhuma outra jornada encomenda: roda uma
// vez por seed. Um produto com lote hoje e amanhã não serve aqui enquanto o vínculo
// pedido × lote prender a encomenda de amanhã ao lote de hoje (achado 4.1 do plano, que o
// WP-F08 conserta).
const PRODUCT = "Ciabatta";
const ORDERED = 2;
const REASON = "Assou demais";

test("J-P4: rendeu menos que o encomendado, o lote fecha com a verdade", async ({ browser, baseURL }, testInfo) => {
  // Medido em 23/11/2026: no seed, todo produto com lote amanhã também tem lote hoje, e a
  // régua do vínculo prende a encomenda de amanhã ao lote de hoje. A pergunta do lote
  // curto não aparece no lote de amanhã, embora o Gestor receba o aviso (#3457). Sai do
  // fixme com o WP-F08 (uma régua só).
  test.fixme(true, "espera o WP-F08: a régua do vínculo aponta o lote de hoje (#3457)");
  test.skip(!stack.production, "a J-P4 pede a Produção na pilha (OPERATOR_PRODUCTION_URL)");

  const gestorContext = await roleContext(browser, baseURL!);
  const gestor = await gestorContext.newPage();
  await acknowledgeOtherOrdersAlarms(gestor);
  await managerSignsIn(gestor);
  await managerBindsDevice(gestor, { name: "Gestor do balcão", kind: "Escritório" }, "/workstations");
  await gestor.goto("/");
  await managerChoosesPosto(gestor, "Gestor do balcão");
  await lockDevice(gestor);
  await operatorUnlocksWithPin(gestor, cast.cashier);

  // A cliente encomenda para amanhã e paga.
  const storeContext = await roleContext(browser, stack.store, true);
  const store = await storeContext.newPage();
  const ref = await customerOrdersPickupToday(store, testInfo, {
    product: PRODUCT,
    quantity: ORDERED,
    phone: newCustomerPhone(),
    name: "Marina",
    day: "Amanhã",
  });

  // O Caixa aceita: a reserva vai para o lote de amanhã.
  await acknowledgeOtherOrdersAlarms(gestor, ref);
  await expect(orderCard(gestor, ref)).toBeVisible({ timeout: 60_000 });
  await cashierAccepts(gestor, ref);

  // A Produção: a Cozinha entra com o PIN e abre o lote de amanhã com o planejado.
  const productionContext = await roleContext(browser, stack.production);
  const production = await productionContext.newPage();
  await managerSignsIn(production);
  const unbound = production.getByRole("button", { name: "Usar sem vincular" });
  if (await unbound.isVisible().catch(() => false)) await unbound.click();
  await lockDevice(production);
  await operatorUnlocksWithPin(production, cast.kitchen);
  const tomorrow = new Date(Date.now() + 24 * 3600 * 1000).toLocaleDateString("en-CA", { timeZone: "America/Sao_Paulo" });
  await production.goto(`/?date=${tomorrow}`);
  await settled(production);
  // Medido: a tela da Produção ignora o ?date= (só o Planejamento guarda o dia na URL).
  // Ao sair do fixme (#3457), escolher "Amanhã" no seletor do dia aqui e na Finalização.
  await production.getByRole("button", { name: `Confirmar ${PRODUCT}`, exact: true }).first().click();
  const startDialog = production.getByRole("dialog");
  const previsto = Number(
    (await startDialog.getByRole("textbox", { name: "Quantidade prevista" }).inputValue()).replace(",", "."),
  );
  expect(previsto, "o previsto nasce do planejado").toBeGreaterThan(ORDERED);
  await startDialog.getByRole("button", { name: "Confirmar", exact: true }).click();
  await expect(startDialog).toBeHidden();

  // Finalização: rende 1, o resto é perda com o motivo.
  const loss = previsto - 1;
  await production.goto(`/close?date=${tomorrow}`);
  await settled(production);
  await production.getByRole("button", { name: `Finalizar o lote de ${PRODUCT}` }).first().click();
  await expect(production.getByText(`${previsto} previstos`)).toBeVisible();
  await production.getByRole("button", { name: /^Perda: \d+ unidades$/ }).click();
  for (const digit of String(loss)) {
    await production.getByRole("button", { name: `Dígito ${digit}`, exact: true }).click();
  }
  await expect(production.getByRole("button", { name: `Perda: ${loss} unidades` })).toBeVisible();
  await production.getByRole("button", { name: "Finalizar", exact: true }).locator("visible=true").first().click();
  const reasonSheet = production.getByRole("dialog");
  await expect(reasonSheet.getByText(`Qual o motivo principal da perda de ${loss}?`)).toBeVisible();
  await reasonSheet.getByRole("button", { name: new RegExp(`^${REASON}`) }).click();

  // A pergunta do lote curto: quanto rendeu, quanto falta e quem fica descoberto.
  const shortLot = production.getByRole("dialog", { name: "Rendeu menos que o encomendado" });
  await expect(shortLot).toBeVisible();
  await expect(shortLot.getByText(/^Rendeu 1\. (Falta 1|Faltam \d+) para as encomendas\.$/)).toBeVisible();
  await expect(shortLot.getByText(ref)).toBeVisible();
  await expect(shortLot.getByText("pelo menos")).toHaveCount(0);
  await capture(production, testInfo, "producao-rendeu-menos");
  await shortLot.getByRole("button", { name: "Fechar com 1", exact: true }).click();
  await expect(shortLot).toBeHidden();
  await expect(production.getByRole("button", { name: `Finalizar o lote de ${PRODUCT}` })).toHaveCount(0);
  await capture(production, testInfo, "producao-lote-fechado");

  // O Gestor: o pedido em "Promessa em risco", com o item e o Resolver.
  await gestor.goto(`/${ref}`);
  await expect(async () => {
    await gestor.reload();
    await settled(gestor);
    await expect(gestor.getByText("Promessa em risco").filter({ visible: true }).first()).toBeVisible({ timeout: 5_000 });
  }).toPass({ timeout: 90_000 });
  await expect(gestor.getByText(PRODUCT).filter({ visible: true }).first()).toBeVisible();
  await expect(gestor.getByRole("button", { name: /Resolver/ }).filter({ visible: true }).first()).toBeVisible();
  await capture(gestor, testInfo, "gestor-promessa-em-risco");

  await productionContext.close();
  await storeContext.close();
  await gestorContext.close();
});
