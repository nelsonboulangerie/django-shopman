import { expect, test, type Page } from "@playwright/test";
import { atCounterHour, backToRealTime, controlDir } from "./support/clock";
import { customerOrdersPickupToday } from "./support/customer";
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
import { printerBearer, printerTakesTheNextJob } from "./support/printer";
import { capture, cast, newCustomerPhone, roleContext, settled, stack } from "./support/stack";

// F3 (#3124, o estado fiscal "DANFE" da #2550): a cliente pede retirada para hoje com CPF
// na nota e paga; o balcão aceita e inicia, a Cozinha dá Pronto, o balcão entrega, e a
// NFC-e sai autorizada (nota simulada, com XML). No detalhe, o Caixa toca "Imprimir
// DANFE": a bobina vai pelo relay à impressora do balcão, que a pega e confirma, e o
// detalhe diz "DANFE impressa". "Reimprimir DANFE" manda o mesmo papel marcado
// REIMPRESSÃO. A impressora é a simulada (`support/printer.ts`), com a credencial que
// o comando real de pareamento emite.
test.skip(!controlDir, "pede a nota simulada e o relógio de teste da pilha (OPERATOR_CONTROL_DIR; README)");
test.skip(!printerBearer, "pede a impressora simulada do balcão (OPERATOR_PRINT_AGENT_BEARER; README)");
test.afterAll(() => backToRealTime());

const TAX_ID = "52998224725";

/** O item de DANFE do ⋯ do pedido, com o rótulo e o estado que a tela diz. */
async function danfeMenuItem(gestor: Page) {
  await gestor.getByRole("button", { name: "Mais ações do pedido" }).click();
  return gestor.locator('[data-action="print-danfe"]');
}

test("F3: a DANFE sai pela impressora do balcão e a reimpressão sai marcada", async ({ browser, baseURL }, testInfo) => {
  const at = await atCounterHour();
  const gestorContext = await roleContext(browser, baseURL!, false, at);
  const gestor = await gestorContext.newPage();
  await acknowledgeOtherOrdersAlarms(gestor);
  await managerSignsIn(gestor);
  await managerBindsDevice(gestor, { name: "Gestor do balcão", kind: "Escritório" }, "/workstations");
  await gestor.goto("/");
  await managerChoosesPosto(gestor, "Gestor do balcão");
  await lockDevice(gestor);
  await operatorUnlocksWithPin(gestor, cast.cashier);

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
    name: "Helena",
    taxId: TAX_ID,
  });
  await storeContext.close();

  await acknowledgeOtherOrdersAlarms(gestor, ref);
  await expect(orderCard(gestor, ref)).toBeVisible({ timeout: 60_000 });
  await cashierAccepts(gestor, ref);
  await cashierStartsPreparing(gestor, ref);
  await kitchenMarksReady(kitchen, ref);
  await cashierDelivers(gestor, ref);

  // A nota sai na entrega e autoriza; a DANFE fica disponível no ⋯ do pedido.
  await gestor.goto(`/${encodeURIComponent(ref)}`);
  await settled(gestor);
  await expect(async () => {
    await gestor.reload();
    await settled(gestor);
    await expect(gestor.getByText("NFC-e autorizada").first()).toBeVisible({ timeout: 5_000 });
  }).toPass({ timeout: 120_000 });
  let item = await danfeMenuItem(gestor);
  await expect(item).toContainText("Imprimir DANFE");
  await capture(gestor, testInfo, "gestor-danfe-disponivel");

  // Imprimir: a bobina vai pelo relay; a impressora do balcão a pega e confirma.
  await item.click();
  const first = await printerTakesTheNextJob();
  expect(first.kind).toBe("order_danfe");
  expect(first.text).toContain("DANFE NFC-e");
  expect(first.text).toContain("Croissant");
  expect(first.text).not.toContain("REIMPRESS");

  // O detalhe diz que a DANFE saiu, e o gesto vira reimprimir.
  await expect(async () => {
    await gestor.reload();
    await settled(gestor);
    item = await danfeMenuItem(gestor);
    await expect(item).toContainText("DANFE impressa", { timeout: 5_000 });
  }).toPass({ timeout: 60_000 });
  await expect(item).toContainText("Reimprimir DANFE");
  await capture(gestor, testInfo, "gestor-danfe-impressa");

  // Reimprimir: o mesmo papel, marcado.
  await item.click();
  const second = await printerTakesTheNextJob();
  expect(second.kind).toBe("order_danfe");
  expect(second.text).toContain("DANFE NFC-e");
  expect(second.text).toContain("REIMPRESS");
  await capture(gestor, testInfo, "gestor-danfe-reimpressa");

  await kitchenContext.close();
  await gestorContext.close();
});
