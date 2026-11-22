import { expect, test } from "@playwright/test";
import { controlDir } from "./support/clock";
import { customerOrdersDeliveryToday } from "./support/customer";
import { sefazAuthorizesAll, simulatedNote } from "./support/fiscal";
import { cashierAccepts, cashierStartsPreparing, orderCard } from "./support/gestor";
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

// F2 (estados fiscais da #2550, com a nota simulada da #2585): entrega sem CPF. A cliente
// pede entrega para hoje, não informa CPF na nota e paga com Pix. O Caixa aceita e inicia,
// a Cozinha dá Pronto: na entrega da casa a NFC-e nasce com a sacola pronta, antes de o
// entregador sair. Sem CPF ela sai do mesmo jeito (decisão do dono, 13/10/2026), como venda
// presencial, sem destinatário nem frete, e o pedido diz "NFC-e autorizada".
const ADDRESS = {
  route: "Rua Jorge Velho",
  number: "140",
  neighborhood: "Bela Suíça",
  cep: "86050-480",
  city: "Londrina",
  state: "PR",
};

test.skip(!controlDir, "pede a nota simulada da pilha (OPERATOR_CONTROL_DIR; README)");

test("F2: a entrega sem CPF sai com NFC-e autorizada, antes da saída", async ({ browser, baseURL }, testInfo) => {
  sefazAuthorizesAll();
  const gestorContext = await roleContext(browser, baseURL!);
  const gestor = await gestorContext.newPage();
  await acknowledgeOtherOrdersAlarms(gestor);
  await managerSignsIn(gestor);
  await managerBindsDevice(gestor, { name: "Gestor do balcão", kind: "Escritório" }, "/workstations");
  await gestor.goto("/");
  await managerChoosesPosto(gestor, "Gestor do balcão");
  await lockDevice(gestor);
  await operatorUnlocksWithPin(gestor, cast.cashier);

  // Cozinha: a Gerente abre a estação de Separação e bloqueia; Diofer entra com PIN.
  const kitchenContext = await roleContext(browser, stack.kitchen);
  const kitchen = await kitchenContext.newPage();
  await managerSignsIn(kitchen);
  await kitchen.getByRole("button", { name: "Usar sem vincular" }).click();
  await kitchen.getByRole("link", { name: /^Separação/ }).first().click();
  await expect(kitchen.getByRole("heading", { name: "Separação", level: 1 })).toBeVisible();
  await lockDevice(kitchen);
  await operatorUnlocksWithPin(kitchen, cast.kitchen);

  const storeContext = await roleContext(browser, stack.store, true);
  const store = await storeContext.newPage();
  const ref = await customerOrdersDeliveryToday(store, testInfo, {
    product: "Croissant",
    quantity: 3,
    phone: newCustomerPhone(),
    name: "Marta",
    address: ADDRESS,
  });
  await storeContext.close();

  await acknowledgeOtherOrdersAlarms(gestor, ref);
  await gestor.goto("/?view=board");
  await settled(gestor);
  await expect(orderCard(gestor, ref)).toBeVisible({ timeout: 60_000 });
  await cashierAccepts(gestor, ref);
  await cashierStartsPreparing(gestor, ref);
  // Sacola pronta: é aqui que a nota da entrega nasce.
  await kitchenMarksReady(kitchen, ref);

  await gestor.goto(`/${encodeURIComponent(ref)}`);
  await settled(gestor);
  await expect(async () => {
    await gestor.reload();
    await settled(gestor);
    await expect(gestor.getByText("NFC-e autorizada").first()).toBeVisible({ timeout: 5_000 });
  }).toPass({ timeout: 120_000 });
  await expect(gestor.locator('[data-pending="nfce"]')).toHaveCount(0);
  await capture(gestor, testInfo, "entrega-sem-cpf-nota-autorizada");

  // O que a nota declarou: sem documento, a entrega sai como venda PRESENCIAL, sem
  // destinatário nem frete (services/fiscal.delivery_issues_as_presential).
  const note = simulatedNote(ref);
  expect(note, "a SEFAZ simulada deveria ter a nota do pedido").not.toBeNull();
  expect(note!.status).toBe("authorized");
  expect(note!.customer_tax_id).toBe("");
  expect(note!.delivery, "entrega sem CPF sai presencial, sem o grupo de entrega").toBe(false);

  await kitchenContext.close();
  await gestorContext.close();
});
