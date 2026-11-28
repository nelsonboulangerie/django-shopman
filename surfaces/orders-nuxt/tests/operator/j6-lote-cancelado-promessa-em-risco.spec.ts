import { expect, test } from "@playwright/test";
import { customerOrdersPickupToday } from "./support/customer";
import { cashierAccepts, orderCard } from "./support/gestor";
import {
  acknowledgeOtherOrdersAlarms,
  lockDevice,
  managerBindsDevice,
  managerChoosesPosto,
  managerSignsIn,
  operatorUnlocksWithPin,
} from "./support/operator";
import { capture, cast, newCustomerPhone, roleContext, settled, stack } from "./support/stack";

// J6 (docs/plans/EXCELENCIA-GESTOR-PLANO.md, seção 8; WP-G08): o lote cancelado vira
// promessa em risco. A cliente encomenda um Pain au Chocolat para amanhã e paga; o Caixa
// aceita, e a reserva se ancora no lote planejado para amanhã (o seed o planeja).
// Quem opera a Produção (a Gerente, porque cancelar lote é com o gerente) cancela esse
// lote pela tela dela. O Gestor mostra o pedido em "Promessa em risco", dizendo qual item
// ficou sem lastro, com o "Resolver".
//
// O lote é só desta jornada (#3295). Com o Croissant, que a J3 e a J5 também encomendam
// para amanhã, a J4 levava o relógio da pilha até amanhã, a encomenda da J3 ia para a
// Cozinha e dava baixa no lote planejado, e o cancelamento era recusado com razão ("1 un.
// dele já foram entregues"): a J6 caía ou passava conforme a ordem da suíte.
const PRODUCT = "Pain au Chocolat";
test("J6: o lote cancelado na Produção vira promessa em risco no Gestor", async ({ browser, baseURL }, testInfo) => {
  test.skip(!stack.production, "a J6 pede a Produção na pilha (OPERATOR_PRODUCTION_URL)");

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
    phone: newCustomerPhone(),
    name: "Helena",
    day: "Amanhã",
  });

  // O Caixa aceita: a reserva vai para o lote de amanhã.
  await acknowledgeOtherOrdersAlarms(gestor, ref);
  await expect(orderCard(gestor, ref)).toBeVisible({ timeout: 60_000 });
  await cashierAccepts(gestor, ref);
  await gestor.goto(`/${ref}`);
  await settled(gestor);
  await expect(gestor.getByText("Promessa em risco").filter({ visible: true })).toHaveCount(0);

  // A Produção: a Gerente abre o dia de amanhã e cancela o lote do Pain au Chocolat.
  const productionContext = await roleContext(browser, stack.production);
  const production = await productionContext.newPage();
  await managerSignsIn(production);
  const unbound = production.getByRole("button", { name: "Usar sem vincular" });
  if (await unbound.isVisible().catch(() => false)) await unbound.click();
  // Quem cancela se identifica: a Gerente trava o dispositivo e entra com o PIN dela.
  await lockDevice(production);
  await operatorUnlocksWithPin(production, cast.manager);
  const tomorrow = new Date(Date.now() + 24 * 3600 * 1000).toLocaleDateString("en-CA", { timeZone: "America/Sao_Paulo" });
  await production.goto(`/?date=${tomorrow}`);
  await settled(production);
  // A linha do lote tem o nome da receita; o ⋯ dela tem o cancelar.
  await production.getByRole("button", { name: `Mais ações de ${PRODUCT}` }).first().click();
  await production.getByRole("menuitem", { name: "Cancelar lote…" }).click();
  await capture(production, testInfo, "producao-cancelar-lote");
  await production.getByRole("button", { name: "Confirmar cancelamento" }).click();
  await expect(production.getByText(`Lote cancelado: ${PRODUCT}`).first()).toBeVisible({ timeout: 60_000 });
  await capture(production, testInfo, "producao-lote-cancelado");

  // O Gestor: o pedido em promessa em risco, com o item e o Resolver.
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
