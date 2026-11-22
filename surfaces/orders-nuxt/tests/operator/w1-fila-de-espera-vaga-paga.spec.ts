import { expect, test, type Locator, type Page } from "@playwright/test";
import { backToRealTime, controlDir, shopDate, shopInstant, syncBrowserClock, travelTo } from "./support/clock";
import { customerConfirmsTheSlotAndPays, customerOrdersPickupToday } from "./support/customer";
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

// W1 (#2550: "fila de espera e vaga paga"): a fila é da fornada de HOJE que ainda não
// ficou pronta (shop/services/waitlist.py). A cliente pede, envia e entra na fila sem
// pagar nada. O Gestor mostra o pedido na fila. A Gerente finaliza o lote na Produção:
// a fornada saiu, e a vez é da cliente. Ela confirma a vaga no acompanhamento e só aí o
// Pix nasce; paga, e o Caixa aceita.
//
// O lote é o do seed (o Kuro Pan de hoje, já iniciado, 9 por sair; 8 na vitrine). Cada
// unidade é uma reserva: a cliente pede mais do que a vitrine cobre, e o que falta
// espera a fornada. Basta uma unidade esperando para o pedido estar na fila. A W1 pede a
// pilha semeada HOJE e o relógio de teste, que a leva às 10h, com a fornada por sair.
const PRODUCT = "Kuro Pan";
const MORE_THAN_THE_SHELF = 10;
const MORNING_HOUR = 10;

test.skip(!controlDir, "pede o relógio de teste da pilha (OPERATOR_CONTROL_DIR; README)");
test.skip(!stack.production, "pede a Produção na pilha (OPERATOR_PRODUCTION_URL)");
test.afterAll(() => backToRealTime());

const BATCH_IN_PROGRESS = `${PRODUCT}: o lote de hoje está em andamento`;
// O selo da fila e o porquê do aceite desligado (#3177), sem falar em pagamento: na
// fila, nada foi cobrado (shop/services/operator_orders._waitlist_wait_reason).
const IN_THE_QUEUE = "Na fila de espera";
const WAITING_THE_CUSTOMER = "Aguardando o cliente confirmar";
const ACCEPT_WAITS_THE_BATCH = "Na fila de espera: o pedido espera o lote ficar pronto. Nada foi cobrado do cliente.";

const waitlistBadge = (card: Locator) => card.locator("[data-waitlist-badge]");

/** O card do pedido no painel, relido até `check` passar (o worker abre a vaga). */
async function boardCard(gestor: Page, ref: string, check: (card: Locator) => Promise<void>): Promise<Locator> {
  const card = orderCard(gestor, ref).first();
  await expect(async () => {
    await gestor.goto("/?view=board");
    await settled(gestor);
    await check(card);
  }).toPass({ timeout: 90_000 });
  await card.scrollIntoViewIfNeeded();
  return card;
}

const accept = (card: Locator) => card.getByRole("button", { name: "Aceitar", exact: true });

test("W1: a cliente entra na fila, o lote fica pronto, ela confirma a vaga e paga", async ({ browser, baseURL }, testInfo) => {
  test.setTimeout(600_000);
  const morning = shopInstant(shopDate(), MORNING_HOUR);
  await travelTo(morning);

  const gestorContext = await roleContext(browser, baseURL!);
  await syncBrowserClock(gestorContext, morning);
  const gestor = await gestorContext.newPage();
  await acknowledgeOtherOrdersAlarms(gestor);
  await managerSignsIn(gestor);
  await managerBindsDevice(gestor, { name: "Gestor do balcão", kind: "Escritório" }, "/workstations");
  await gestor.goto("/");
  await managerChoosesPosto(gestor, "Gestor do balcão");
  await lockDevice(gestor);
  await operatorUnlocksWithPin(gestor, cast.cashier);

  // A cliente: o cardápio diz quando a fornada fica pronta; ela pede e entra na fila.
  const storeContext = await roleContext(browser, stack.store, true);
  await syncBrowserClock(storeContext, morning);
  const store = await storeContext.newPage();
  const ref = await customerOrdersPickupToday(store, testInfo, {
    product: PRODUCT,
    quantity: MORE_THAN_THE_SHELF,
    phone: newCustomerPhone(),
    name: "Marta",
    queued: true,
  });

  // O Caixa vê o pedido na fila de espera.
  await acknowledgeOtherOrdersAlarms(gestor, ref);
  // No painel da mesa o card diz que o lote está saindo, leva o selo da fila, e o
  // aceite espera dizendo o porquê sem falar em pagamento.
  await boardCard(gestor, ref, async (card) => {
    await expect(card).toContainText(BATCH_IN_PROGRESS, { timeout: 5_000 });
    await expect(waitlistBadge(card)).toHaveText(IN_THE_QUEUE, { timeout: 5_000 });
    await expect(accept(card)).toBeDisabled();
    await expect(accept(card)).toHaveAttribute("title", ACCEPT_WAITS_THE_BATCH);
  });
  await capture(gestor, testInfo, "gestor-na-fila");

  // A Gerente finaliza o lote do Kuro Pan na Produção: a fornada saiu.
  const productionContext = await roleContext(browser, stack.production);
  await syncBrowserClock(productionContext, morning);
  const production = await productionContext.newPage();
  await managerSignsIn(production);
  const unbound = production.getByRole("button", { name: "Usar sem vincular" });
  if (await unbound.isVisible().catch(() => false)) await unbound.click();
  await lockDevice(production);
  await operatorUnlocksWithPin(production, cast.manager);
  await production.goto("/close");
  await settled(production);
  await production.getByRole("button", { name: `Finalizar o lote de ${PRODUCT}` }).first().click();
  await capture(production, testInfo, "producao-finalizar");
  await production.getByRole("button", { name: "Finalizar", exact: true }).first().click();
  const confirm = production.getByRole("button", { name: /^Confirmar \d+ unidades$/ });
  if (await confirm.first().isVisible({ timeout: 3_000 }).catch(() => false)) await confirm.first().click();
  await expect(production.getByRole("button", { name: `Finalizar o lote de ${PRODUCT}` })).toHaveCount(0, { timeout: 60_000 });
  await capture(production, testInfo, "producao-lote-finalizado");

  // O Gestor: o lote saiu, e a vez é da cliente. O selo diz que o pedido espera ela.
  await boardCard(gestor, ref, async (card) => {
    await expect(card).not.toContainText(BATCH_IN_PROGRESS, { timeout: 5_000 });
    await expect(waitlistBadge(card)).toHaveText(WAITING_THE_CUSTOMER, { timeout: 5_000 });
  });
  await capture(gestor, testInfo, "gestor-aguardando-cliente");

  // A cliente confirma a vaga, e só agora o Pix nasce; ela paga.
  await customerConfirmsTheSlotAndPays(store, testInfo);

  // A cliente pagou: o aceite corre, e o Caixa aceita.
  await boardCard(gestor, ref, async (card) => {
    await expect(card).toContainText(/Cancela sozinho em \d+:\d{2}/, { timeout: 5_000 });
    await expect(accept(card)).toBeEnabled();
  });
  await capture(gestor, testInfo, "gestor-cliente-pagou");
  await cashierAccepts(gestor, ref);
  await capture(gestor, testInfo, "gestor-aceita");

  await store.reload();
  await settled(store);
  await expect(store.getByText(/^Pedido aceito\./).first()).toBeVisible({ timeout: 60_000 });
  await capture(store, testInfo, "loja-aceita");

  await productionContext.close();
  await storeContext.close();
  await gestorContext.close();
});
