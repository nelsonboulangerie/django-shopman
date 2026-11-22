import { expect, test, type Page } from "@playwright/test";
import { atCounterHour, backToRealTime, controlDir } from "./support/clock";
import { customerOrdersPickupToday } from "./support/customer";
import { cashierAccepts, cashierStartsPreparing, orderCard, shortCode } from "./support/gestor";
import {
  acknowledgeOtherOrdersAlarms,
  lockDevice,
  managerBindsDevice,
  managerChoosesPosto,
  managerSignsIn,
  operatorUnlocksWithPin,
} from "./support/operator";
import { capture, cast, newCustomerPhone, roleContext, settled, stack } from "./support/stack";

// C1 (#2550, "cancelar depois do preparo, com Gerente"): a cliente pede retirada para
// hoje e paga; a Caixa aceita e inicia o preparo, e a Cozinha recebe o ticket. Depois do
// preparo começado, o pedido pago só se cancela com a assinatura de quem gerencia: a
// Caixa abre o cancelamento no detalhe, lê o destino do dinheiro, e a Gerente escolhe o
// próprio nome e digita o PIN. O detalhe diz o que acontece com o dinheiro; a Cozinha não
// perde o fato: o ticket vira "Cancelado", com "Não preparar.", até alguém da bancada dar
// a ciência; e a cliente lê o cancelamento e a devolução.
//
// Roda na hora do balcão (`atCounterHour`): o pedido de hoje fica no painel, e não nas
// Encomendas de hoje (#3295).
test.skip(!controlDir, "pede o relógio de teste da pilha (OPERATOR_CONTROL_DIR; README)");
test.afterAll(() => backToRealTime());

const MONEY_BACK = /R\$ \d+,\d{2} serão estornados ao Pix do cliente\./;

/** O ticket do pedido na estação, achado pelo código como faz quem está na bancada. */
async function kitchenTicket(kitchen: Page, ref: string) {
  const code = shortCode(ref);
  const ticket = kitchen.getByRole("article").filter({
    has: kitchen.getByRole("button", { name: `Ver o detalhe do pedido ${code}`, exact: true }),
  });
  if (!(await ticket.isVisible().catch(() => false))) {
    await kitchen.getByRole("button", { name: /^Buscar pedido por código/ }).click();
    await kitchen.getByRole("textbox", { name: "Código, cliente ou item" }).pressSequentially(code);
    await kitchen.getByRole("option", { name: `Filtrar os tickets por “${code}”` }).click();
  }
  await expect(ticket).toBeVisible({ timeout: 120_000 });
  return ticket;
}

test("C1: cancelar depois do preparo, com a assinatura da Gerente, e a Cozinha recebe o cancelamento", async ({ browser, baseURL }, testInfo) => {
  const at = await atCounterHour();
  // Balcão: a Gerente abre o dispositivo e o bloqueia; a Fran entra com PIN.
  const gestorContext = await roleContext(browser, baseURL!, false, at);
  const gestor = await gestorContext.newPage();
  await acknowledgeOtherOrdersAlarms(gestor);
  await managerSignsIn(gestor);
  await managerBindsDevice(gestor, { name: "Gestor do balcão", kind: "Escritório" }, "/workstations");
  await gestor.goto("/");
  await managerChoosesPosto(gestor, "Gestor do balcão");
  await lockDevice(gestor);
  await operatorUnlocksWithPin(gestor, cast.cashier);

  // Cozinha: a Gerente abre a Separação e bloqueia; o Diofer entra com PIN.
  const kitchenContext = await roleContext(browser, stack.kitchen, false, at);
  const kitchen = await kitchenContext.newPage();
  await managerSignsIn(kitchen);
  await kitchen.getByRole("button", { name: "Usar sem vincular" }).click();
  await kitchen.getByRole("link", { name: /^Separação/ }).first().click();
  await expect(kitchen.getByRole("heading", { name: "Separação", level: 1 })).toBeVisible();
  await lockDevice(kitchen);
  await operatorUnlocksWithPin(kitchen, cast.kitchen);

  // A cliente pede e paga.
  const storeContext = await roleContext(browser, stack.store, true, at);
  const store = await storeContext.newPage();
  const ref = await customerOrdersPickupToday(store, testInfo, { product: "Croissant", phone: newCustomerPhone(), name: "Clara" });

  // A Fran aceita e inicia o preparo; a Cozinha recebe o ticket.
  await acknowledgeOtherOrdersAlarms(gestor, ref);
  await expect(orderCard(gestor, ref)).toBeVisible({ timeout: 60_000 });
  await cashierAccepts(gestor, ref);
  await cashierStartsPreparing(gestor, ref);
  await capture(gestor, testInfo, "gestor-em-preparo");
  const ticket = await kitchenTicket(kitchen, ref);
  await capture(kitchen, testInfo, "cozinha-ticket");

  // Depois do preparo começado, a Fran abre o cancelamento no detalhe: o pedido pago
  // pede gerente, e a tela diz o destino do dinheiro antes de qualquer confirmação.
  await gestor.goto(`/${ref}`);
  await settled(gestor);
  await expect(gestor.getByText("Em preparo", { exact: true }).filter({ visible: true }).first()).toBeVisible({ timeout: 60_000 });
  await gestor.getByRole("button", { name: "Mais ações do pedido" }).click();
  await gestor.getByRole("button", { name: "Cancelar pedido (pede gerente)", exact: true }).click();
  const dialog = gestor.getByRole("dialog").filter({ has: gestor.getByRole("radio") });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(MONEY_BACK)).toBeVisible();
  await dialog.getByRole("radio").first().click();
  await capture(gestor, testInfo, "gestor-cancelar-motivo");
  await dialog.getByRole("button", { name: /^Cancelar pedido/ }).last().click();

  // A Gerente assina: escolhe o próprio nome na lista e digita o PIN no teclado da tela.
  const auth = gestor.getByRole("dialog").filter({ has: gestor.getByRole("heading", { name: "Autorizar cancelamento" }) });
  await expect(auth).toBeVisible({ timeout: 60_000 });
  await expect(auth.getByText(MONEY_BACK)).toBeVisible();
  await auth.getByRole("button", { name: new RegExp(cast.manager.name) }).first().click();
  for (const digit of cast.manager.pin) await auth.getByRole("button", { name: digit, exact: true }).click();
  await capture(gestor, testInfo, "gestor-cancelar-assinatura");
  await auth.getByRole("button", { name: "Confirmar", exact: true }).click();
  await expect(auth).toBeHidden({ timeout: 60_000 });

  // O detalhe diz o que aconteceu com o pedido e com o dinheiro.
  await expect(gestor.getByText("Cancelado", { exact: true }).filter({ visible: true }).first()).toBeVisible({ timeout: 60_000 });
  await expect(gestor.getByText(/Estorno pedido|Estornado/).filter({ visible: true }).first()).toBeVisible({ timeout: 60_000 });
  await capture(gestor, testInfo, "gestor-cancelado-dinheiro");

  // A Cozinha: o ticket vira "Cancelado", com "Não preparar.", sem ninguém recarregar a
  // estação; o Diofer dá a ciência e o ticket sai da bancada. O card cancelado não tem
  // mais o "Ver o detalhe": quem o acha é a ciência com o código do pedido.
  const seen = kitchen.getByRole("button", { name: `Recebi o cancelamento: pedido ${shortCode(ref)}`, exact: true });
  await expect(seen).toBeVisible({ timeout: 60_000 });
  const cancelled = kitchen.getByRole("article").filter({ has: seen });
  await expect(cancelled.getByText(/^Pedido cancelado.*Não preparar\.$/)).toBeVisible();
  await expect(ticket).toHaveCount(0);
  await capture(kitchen, testInfo, "cozinha-cancelado");
  await seen.click();
  await expect(cancelled).toHaveCount(0, { timeout: 60_000 });
  await capture(kitchen, testInfo, "cozinha-ciente");

  // A cliente lê o cancelamento e a devolução no acompanhamento.
  await store.reload();
  await expect(store.getByText(/Devolvemos os R\$ \d+,\d{2} do seu Pix/).first()).toBeVisible({ timeout: 60_000 });
  await capture(store, testInfo, "loja-cancelado");

  await storeContext.close();
  await kitchenContext.close();
  await gestorContext.close();
});
