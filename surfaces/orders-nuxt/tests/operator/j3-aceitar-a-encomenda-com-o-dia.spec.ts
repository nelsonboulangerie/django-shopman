import { expect, test } from "@playwright/test";
import { customerOrdersPickupToday } from "./support/customer";
import { cashierAccepts, orderCard, shortCode } from "./support/gestor";
import {
  acknowledgeOtherOrdersAlarms,
  lockDevice,
  managerBindsDevice,
  managerChoosesPosto,
  managerSignsIn,
  operatorUnlocksWithPin,
} from "./support/operator";
import { capture, cast, newCustomerPhone, roleContext, settled, stack } from "./support/stack";

// J3 (docs/plans/EXCELENCIA-GESTOR-PLANO.md, seção 8; WP-G01): a encomenda se anuncia.
// A cliente encomenda pela loja para amanhã, com a janela da retirada, e paga. O Caixa,
// com PIN, lê "Encomenda" com o dia e a janela no Painel, na Fila, na Tabela e no sino,
// antes de aceitar; e aceita.
const PROMISE = /^Encomenda · Amanhã/;

test("J3: aceitar a encomenda lendo o dia e a janela nas quatro formas", async ({ browser, baseURL }, testInfo) => {
  const gestorContext = await roleContext(browser, baseURL!);
  const gestor = await gestorContext.newPage();
  await acknowledgeOtherOrdersAlarms(gestor);
  await managerSignsIn(gestor);
  await managerBindsDevice(gestor, { name: "Gestor do balcão", kind: "Escritório" }, "/workstations");
  await gestor.goto("/");
  await managerChoosesPosto(gestor, "Gestor do balcão");
  await lockDevice(gestor);
  await operatorUnlocksWithPin(gestor, cast.cashier);

  const storeContext = await roleContext(browser, stack.store, true);
  const store = await storeContext.newPage();
  const ref = await customerOrdersPickupToday(store, testInfo, {
    product: "Croissant",
    phone: newCustomerPhone(),
    name: "Beatriz",
    day: "Amanhã",
  });
  const code = shortCode(ref);

  // Painel: o cartão do pedido novo diz para quando.
  await acknowledgeOtherOrdersAlarms(gestor, ref);
  await gestor.goto("/?view=board");
  await settled(gestor);
  const card = orderCard(gestor, ref);
  await expect(card).toBeVisible({ timeout: 60_000 });
  await expect(card.locator("[data-card-promise]").filter({ visible: true }).first()).toHaveText(PROMISE);
  await capture(gestor, testInfo, "painel-encomenda");

  // Fila: a mesma frase na linha do pedido.
  await gestor.goto("/?view=queue");
  await settled(gestor);
  const queueRow = gestor.locator(`[data-queue-ref="${ref}"]`);
  const more = gestor.getByText(/Ver todos/).first();
  if (!(await queueRow.isVisible().catch(() => false)) && (await more.isVisible().catch(() => false))) await more.click();
  await expect(queueRow.locator("[data-queue-promise]").first()).toHaveText(PROMISE, { timeout: 60_000 });
  await queueRow.scrollIntoViewIfNeeded();
  await capture(gestor, testInfo, "fila-encomenda");

  // Tabela: a mesma frase na linha.
  await gestor.goto("/?view=table");
  await settled(gestor);
  const tableRow = gestor.getByRole("row").filter({ has: gestor.getByRole("link", { name: `Abrir pedido ${ref}`, exact: true }) });
  await expect(tableRow.locator("[data-table-promise]").first()).toHaveText(PROMISE, { timeout: 60_000 });
  await tableRow.scrollIntoViewIfNeeded();
  await capture(gestor, testInfo, "tabela-encomenda");

  // Sino: o aviso do pedido novo começa pelo combinado.
  await gestor.getByRole("button", { name: /^Avisos/ }).first().click();
  const notice = gestor.getByText(new RegExp(`^Encomenda · Amanhã.*${code}`)).first();
  await expect(notice).toBeVisible({ timeout: 60_000 });
  await gestor.waitForTimeout(400); // o painel do sino termina de abrir
  await capture(gestor, testInfo, "sino-encomenda");
  await gestor.keyboard.press("Escape");

  // Aceita pelo cartão, como no balcão.
  await gestor.goto("/?view=board");
  await settled(gestor);
  await cashierAccepts(gestor, ref);
  await capture(gestor, testInfo, "aceita");

  await storeContext.close();
  await gestorContext.close();
});
