import { expect, test, type Page } from "@playwright/test";
import { shopDate } from "./support/clock";
import { customerOrdersPickupToday } from "./support/customer";
import { cashierAccepts, orderCard } from "./support/gestor";
import {
  acknowledgeOtherOrdersAlarms,
  lockDevice,
  managerBindsDevice,
  managerBindsPosStation,
  managerChoosesPosto,
  managerSignsIn,
  operatorUnlocksWithPin,
} from "./support/operator";
import { capture, cast, newCustomerPhone, roleContext, settled, stack } from "./support/stack";

// E1 (#2550: "a aba Encomendas do PDV para o mesmo pedido"): a cliente encomenda para
// amanhã pela loja e paga. Antes do aceite, o balcão já a vê nas Encomendas do PDV, e
// lê o mesmo que o Gestor: "Novo", ao lado do dinheiro "Pago" (#3166). O Caixa aceita
// no Gestor; no PDV o "Novo" sai, o dinheiro segue pago, e o detalhe da encomenda traz
// a cliente, o dia e o turno combinados.
const PRODUCT = "Croissant";
const SHIFT = "A partir das 9h";

test.skip(!stack.pos, "pede o PDV na pilha (OPERATOR_POS_URL)");

/** A linha da encomenda nas Encomendas do PDV, relida até `check` passar. */
async function preorderRow(pos: Page, ref: string, check: (row: ReturnType<Page["locator"]>) => Promise<void>) {
  const row = pos.locator(`[data-preorder-card="${ref}"]`).filter({ visible: true }).first();
  await expect(async () => {
    await pos.goto("/preorders");
    await settled(pos);
    // A semana abre no dia de hoje: a Caixa abre o de amanhã.
    const [, month, day] = shopDate(1).split("-");
    const tomorrow = pos.locator("[data-week-day-toggle]").filter({ visible: true }).and(pos.locator(`[aria-label*="${day}/${month}"]`)).first();
    if ((await tomorrow.getAttribute("aria-expanded")) === "false") await tomorrow.click();
    await expect(row).toBeVisible({ timeout: 5_000 });
    await check(row);
  }).toPass({ timeout: 90_000 });
  await row.scrollIntoViewIfNeeded();
  return row;
}

test("E1: a encomenda da loja aparece nas Encomendas do PDV, Novo antes do aceite", async ({ browser, baseURL }, testInfo) => {
  test.setTimeout(600_000);

  const gestorContext = await roleContext(browser, baseURL!);
  const gestor = await gestorContext.newPage();
  await acknowledgeOtherOrdersAlarms(gestor);
  await managerSignsIn(gestor);
  await managerBindsDevice(gestor, { name: "Gestor do balcão", kind: "Escritório" }, "/workstations");
  await gestor.goto("/");
  await managerChoosesPosto(gestor, "Gestor do balcão");
  await lockDevice(gestor);
  await operatorUnlocksWithPin(gestor, cast.cashier);

  // O balcão: a Gerente abre o PDV no posto, e a Caixa entra com o PIN.
  const posContext = await roleContext(browser, stack.pos);
  const pos = await posContext.newPage();
  await managerSignsIn(pos);
  await managerBindsPosStation(pos);
  await lockDevice(pos);
  await operatorUnlocksWithPin(pos, cast.cashier);

  // A cliente encomenda para amanhã e paga.
  const storeContext = await roleContext(browser, stack.store, true);
  const store = await storeContext.newPage();
  const ref = await customerOrdersPickupToday(store, testInfo, {
    product: PRODUCT,
    phone: newCustomerPhone(),
    name: "Lúcia",
    day: "Amanhã",
    window: SHIFT,
  });

  // Antes do aceite: o PDV diz "Novo", como o Gestor, e o dinheiro "Pago".
  await acknowledgeOtherOrdersAlarms(gestor, ref);
  await expect(orderCard(gestor, ref)).toBeVisible({ timeout: 60_000 });
  await preorderRow(pos, ref, async (row) => {
    await expect(row.locator("[data-preorder-situation]").filter({ visible: true }).first()).toHaveText("Novo", { timeout: 5_000 });
    await expect(row.locator("[data-preorder-money-badge]").filter({ visible: true }).first()).toHaveText("Pago");
  });
  await capture(pos, testInfo, "pdv-encomenda-nova");

  // O Caixa aceita no Gestor.
  await cashierAccepts(gestor, ref);
  await capture(gestor, testInfo, "gestor-aceita");

  // No PDV o "Novo" sai, e o dinheiro segue pago.
  await preorderRow(pos, ref, async (row) => {
    await expect(row.getByText("Novo", { exact: true })).toHaveCount(0, { timeout: 5_000 });
    await expect(row.locator("[data-preorder-money-badge]").filter({ visible: true }).first()).toHaveText("Pago");
  });
  await capture(pos, testInfo, "pdv-encomenda-aceita");

  // O detalhe da encomenda: a cliente, o dia e o turno combinados.
  await pos.goto(`/preorders/${encodeURIComponent(ref)}`);
  await settled(pos);
  await expect(pos.getByRole("heading", { name: `Encomenda ${ref}` }).filter({ visible: true }).first()).toBeVisible({ timeout: 60_000 });
  await expect(pos.getByText(/Lúcia/).filter({ visible: true }).first()).toBeVisible();
  await expect(pos.getByText(`Amanhã · ${SHIFT}`).filter({ visible: true }).first()).toBeVisible();
  await expect(pos.getByText(new RegExp(PRODUCT)).filter({ visible: true }).first()).toBeVisible();
  await capture(pos, testInfo, "pdv-detalhe-da-encomenda");

  await storeContext.close();
  await posContext.close();
  await gestorContext.close();
});
