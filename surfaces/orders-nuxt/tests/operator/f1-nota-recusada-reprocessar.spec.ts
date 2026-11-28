import { expect, test } from "@playwright/test";
import { atCounterHour, backToRealTime, controlDir } from "./support/clock";
import { customerOrdersPickupToday } from "./support/customer";
import { sefazAuthorizesAll, sefazRejectsNext } from "./support/fiscal";
import { cashierAccepts, cashierDelivers, cashierStartsPreparing, orderCard } from "./support/gestor";
import { kitchenMarksReady } from "./support/kitchen";
import {
  acknowledgeOtherOrdersAlarms,
  lockDevice,
  managerBindsDevice,
  managerChoosesPosto,
  managerSignsIn,
  operatorUnlocksWithPin,
} from "./support/operator";
import { capture, cast, newCustomerPhone, roleContext, settled, stack } from "./support/stack";

// F1 (estados fiscais da #2550, com a nota simulada da #2585): a SEFAZ recusa a NFC-e.
// A cliente pede a retirada de hoje com CPF na nota e paga; o Caixa aceita e inicia, a
// Cozinha dá Pronto na estação, e o Caixa entrega. A nota sai na entrega e volta recusada:
// o detalhe do pedido diz "NFC-e não autorizada" com a resposta do emissor, e o
// "Reprocessar NFC-e" emite de novo, agora autorizada.
const REJECTION = "Rejeição 778: Informado NCM inexistente";
// CPF sintético válido (dígitos verificadores certos), de nenhuma pessoa da casa.
const TAX_ID = "52998224725";

test.skip(!controlDir, "pede a nota simulada da pilha (OPERATOR_CONTROL_DIR; README)");
test.afterAll(() => sefazAuthorizesAll());
test.afterAll(() => backToRealTime());

test("F1: a NFC-e recusada mostra o motivo e o reprocesso autoriza", async ({ browser, baseURL }, testInfo) => {
  const at = await atCounterHour();
  sefazRejectsNext(REJECTION);
  const gestorContext = await roleContext(browser, baseURL!, false, at);
  const gestor = await gestorContext.newPage();
  await acknowledgeOtherOrdersAlarms(gestor);
  await managerSignsIn(gestor);
  await managerBindsDevice(gestor, { name: "Gestor do balcão", kind: "Escritório" }, "/workstations");
  await gestor.goto("/");
  await managerChoosesPosto(gestor, "Gestor do balcão");
  await lockDevice(gestor);
  await operatorUnlocksWithPin(gestor, cast.cashier);

  // Cozinha: a Gerente abre a estação de Separação (a do pão pronto) e bloqueia; Diofer
  // entra com PIN.
  const kitchenContext = await roleContext(browser, stack.kitchen, false, at);
  const kitchen = await kitchenContext.newPage();
  await managerSignsIn(kitchen);
  await kitchen.getByRole("button", { name: "Usar sem vincular" }).click();
  await kitchen.getByRole("link", { name: /^Separação/ }).first().click();
  await expect(kitchen.getByRole("heading", { name: "Separação", level: 1 })).toBeVisible();
  await lockDevice(kitchen);
  await operatorUnlocksWithPin(kitchen, cast.kitchen);

  const storeContext = await roleContext(browser, stack.store, true, at);
  const store = await storeContext.newPage();
  const ref = await customerOrdersPickupToday(store, testInfo, {
    product: "Croissant",
    phone: newCustomerPhone(),
    name: "Lúcia",
    taxId: TAX_ID,
  });
  await storeContext.close();

  // O balcão aceita e inicia; a Cozinha dá Pronto; o balcão entrega.
  await acknowledgeOtherOrdersAlarms(gestor, ref);
  await gestor.goto("/?view=board");
  await settled(gestor);
  await expect(orderCard(gestor, ref)).toBeVisible({ timeout: 60_000 });
  await cashierAccepts(gestor, ref);
  await cashierStartsPreparing(gestor, ref);
  await kitchenMarksReady(kitchen, ref);
  await cashierDelivers(gestor, ref);

  // A nota sai na entrega e volta recusada: o detalhe diz por quê.
  await gestor.goto(`/${encodeURIComponent(ref)}`);
  await settled(gestor);
  const pending = gestor.locator('[data-pending="nfce"]');
  await expect(async () => {
    await gestor.reload();
    await settled(gestor);
    await expect(pending).toBeVisible({ timeout: 5_000 });
  }).toPass({ timeout: 120_000 });
  await expect(pending).toContainText("NFC-e não autorizada");
  await expect(pending).toContainText(`Resposta do emissor: ${REJECTION}`);
  await pending.scrollIntoViewIfNeeded();
  await capture(gestor, testInfo, "nota-recusada");

  // Reprocessar: a emissão volta à fila e a SEFAZ autoriza.
  await pending.getByRole("button", { name: "Reprocessar NFC-e", exact: true }).click();
  await expect(async () => {
    await gestor.reload();
    await settled(gestor);
    await expect(gestor.getByText("NFC-e autorizada").first()).toBeVisible({ timeout: 5_000 });
  }).toPass({ timeout: 120_000 });
  await expect(pending).toHaveCount(0);
  await capture(gestor, testInfo, "nota-autorizada");

  await kitchenContext.close();
  await gestorContext.close();
});
