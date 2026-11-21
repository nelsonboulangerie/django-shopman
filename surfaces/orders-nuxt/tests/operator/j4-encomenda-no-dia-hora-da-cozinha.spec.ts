import { expect, test } from "@playwright/test";
import { backToRealTime, controlDir, shopDate, shopInstant, syncBrowserClock, travelTo } from "./support/clock";
import { customerOrdersPickupToday } from "./support/customer";
import { cashierAccepts, orderCard, revealCard } from "./support/gestor";
import {
  acknowledgeOtherOrdersAlarms,
  lockDevice,
  managerBindsDevice,
  managerChoosesPosto,
  managerSignsIn,
  operatorUnlocksWithPin,
} from "./support/operator";
import { capture, cast, newCustomerPhone, roleContext, settled, stack } from "./support/stack";

// J4 (docs/plans/EXCELENCIA-GESTOR-PLANO.md, seção 8; WP-G02): a encomenda do dia espera a
// hora da Cozinha. A cliente encomenda para amanhã, no turno das 15h, e paga; o Caixa aceita. O relógio
// da pilha vira o dia: de manhã, o cartão diz quando ela vai para a Cozinha e não pede
// gesto; passada essa hora, o cartão pede "Iniciar preparo".
//
// O item é de revenda (sem lote de produção) de propósito: com a fornada, a virada do dia
// sem ninguém na Produção deixa o lote "atrasado" e a encomenda vira promessa em risco,
// que é a J6. Aqui a pergunta é só a hora da Cozinha.
const PRODUCT = "Queijo Camembert Ile de France 125g";
const WINDOW = "A partir das 15h";
const KITCHEN_WAIT = /Vai para a Cozinha às (\d{1,2})h(\d{2})?/;

test.skip(!controlDir, "pede o relógio de teste da pilha (OPERATOR_CONTROL_DIR; README)");
test.afterAll(() => backToRealTime());

test("J4: a encomenda do dia espera a hora da Cozinha e depois pede o preparo", async ({ browser, baseURL }, testInfo) => {
  backToRealTime();
  const gestorContext = await roleContext(browser, baseURL!);
  await syncBrowserClock(gestorContext, new Date().toISOString());
  const gestor = await gestorContext.newPage();
  await acknowledgeOtherOrdersAlarms(gestor);
  await managerSignsIn(gestor);
  await managerBindsDevice(gestor, { name: "Gestor do balcão", kind: "Escritório" }, "/workstations");
  await gestor.goto("/");
  await managerChoosesPosto(gestor, "Gestor do balcão");
  await lockDevice(gestor);
  await operatorUnlocksWithPin(gestor, cast.cashier);

  // Hoje: a cliente encomenda para amanhã, no turno das 15h, e paga; o Caixa aceita.
  const storeContext = await roleContext(browser, stack.store, true);
  const store = await storeContext.newPage();
  const ref = await customerOrdersPickupToday(store, testInfo, {
    product: PRODUCT,
    phone: newCustomerPhone(),
    name: "Helena",
    day: "Amanhã",
    window: WINDOW,
  });
  await storeContext.close();
  await acknowledgeOtherOrdersAlarms(gestor, ref);
  await gestor.goto("/?view=board");
  await settled(gestor);
  await expect(orderCard(gestor, ref)).toBeVisible({ timeout: 60_000 });
  await cashierAccepts(gestor, ref);

  // Virada do dia: amanhã, 9h. O Caixa abre o Gestor de manhã e acha a encomenda na
  // coluna Encomendas, em "Hoje", dizendo a hora em que vai para a Cozinha.
  const tomorrow = shopDate(1);
  await travelTo(shopInstant(tomorrow, 9), [gestorContext]);
  await gestor.goto("/?view=board");
  await settled(gestor);
  const morning = gestor.getByRole("link", { name: `Abrir pedido ${ref}`, exact: true }).first();
  await expect(morning).toContainText(KITCHEN_WAIT);
  await expect(morning).toContainText("Hoje · A partir das 15h");
  // Quem espera a hora não pede gesto: não está em "Precisa de você", e o painel não tem
  // cartão dela com "Iniciar preparo".
  await expect(morning).not.toContainText("Precisa de você");
  await expect(orderCard(gestor, ref).getByRole("button", { name: "Iniciar preparo", exact: true })).toHaveCount(0);
  await morning.scrollIntoViewIfNeeded();
  await capture(gestor, testInfo, "manha-espera-a-cozinha");

  // Passada a hora da Cozinha (a do próprio cartão, mais 5 min), o cartão pede o preparo.
  const [, hour, minute] = (await morning.textContent())!.match(KITCHEN_WAIT)!;
  const release = new Date(shopInstant(tomorrow, Number(hour), Number(minute ?? 0)));
  release.setMinutes(release.getMinutes() + 5);
  await travelTo(release.toISOString(), [gestorContext]);
  await gestor.goto("/?view=board");
  await settled(gestor);
  const afternoon = await revealCard(gestor, ref);
  await expect(afternoon.locator("[data-card-kitchen-wait]")).toHaveCount(0);
  await expect(afternoon.getByRole("button", { name: "Iniciar preparo", exact: true })).toBeVisible({ timeout: 60_000 });
  // O relógio do cartão conta da chegada à Cozinha, não de ontem, quando ela pediu (WP-G02).
  // A chegada é o worker que grava; o painel acompanha sozinho.
  await expect(afternoon).not.toContainText(/Há \d+h/, { timeout: 120_000 });
  await afternoon.scrollIntoViewIfNeeded();
  await capture(gestor, testInfo, "hora-da-cozinha");

  await gestorContext.close();
});
