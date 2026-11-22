import { expect, test, type Page } from "@playwright/test";
import { backToRealTime, controlDir, shopDate, shopInstant, syncBrowserClock, travelTo } from "./support/clock";
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

// L1 (#2550: "loja fechada"): a casa fechou e a cliente encomenda para amanhã, e paga.
// O prazo de aceite só corre com a casa ABERTA (business_calendar.next_operational_deadline):
// o pedido que chega com a loja fechada não pode vencer de madrugada. A cliente lê que a
// loja confere quando abrir; o Caixa abre o pedido e o prazo conta da abertura, não de
// agora. O relógio da pilha passa da abertura: o pedido continua esperando, com o prazo
// que sobrou, e o Caixa aceita.
//
// A casa que fecha hoje é AMBIENTE da pilha: o seed com `--closing-in-minutes N` (README).
// Na pilha de sempre (aberta 24 h, "Aberto até 23h59"), a L1 pula e diz por quê. O
// produto é de revenda: sem fornada, o pedido de amanhã não vira "Promessa em risco"
// quando o relógio passa da meia-noite.
const PRODUCT = "Queijo Camembert Ile de France 125g";
const CLOSING_LABEL = /^(Aberto|Últimos pedidos) até (\d{1,2})h(\d{2})?$/;
const DEADLINE = /^(Cancela|Confirma) sozinho em (?:(\d+)h(\d{2})|(\d+):(\d{2})) se ninguém (aceitar|recusar)\.$/;
const MINUTE = 60_000;

test.skip(!controlDir, "pede o relógio de teste da pilha (OPERATOR_CONTROL_DIR; README)");
test.afterAll(() => backToRealTime());

/** Os minutos que o detalhe do pedido diz faltar para o aceite ("1h50" ou "55:00"). */
async function minutesToDecide(gestor: Page): Promise<number> {
  const alert = gestor.locator("[data-detail-deadline]");
  await expect(alert).toBeVisible({ timeout: 60_000 });
  const text = (await alert.innerText()).replace(/\s+/g, " ").trim();
  const match = text.match(DEADLINE);
  expect(match, `o prazo de aceite no detalhe: "${text}"`).not.toBeNull();
  const [, , hours, hourMinutes, minutes] = match!;
  return hours ? Number(hours) * 60 + Number(hourMinutes) : Number(minutes);
}

test("L1: com a loja fechada, a encomenda espera a abertura para o prazo de aceite correr", async ({ browser, baseURL }, testInfo) => {
  test.setTimeout(600_000);
  backToRealTime();

  // A hora em que a casa fecha hoje, como a loja escreve no alto da página.
  const storeContext = await roleContext(browser, stack.store, true);
  await syncBrowserClock(storeContext, new Date().toISOString());
  const store = await storeContext.newPage();
  await store.goto("/menu");
  await settled(store);
  const label = store.getByText(CLOSING_LABEL).first();
  await expect(label, "a loja da pilha precisa estar aberta agora (README: expediente)").toBeVisible();
  const [, , hour, minute] = (await label.innerText()).trim().match(CLOSING_LABEL)!;
  test.skip(
    hour === "23" && minute === "59",
    "a pilha está aberta 24 h: a L1 pede a casa que fecha hoje (seed --closing-in-minutes; README)",
  );
  const closesAt = Date.parse(shopInstant(shopDate(), Number(hour), Number(minute ?? 0)));
  const opensAt = Date.parse(shopInstant(shopDate(1), 0, 0)); // a pilha abre à 0h todo dia
  const afterClosing = Math.min(closesAt + 10 * MINUTE, opensAt - 5 * MINUTE);
  expect(afterClosing, "a casa precisa fechar antes das 23h55 para a L1 caber no dia").toBeGreaterThan(closesAt);

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

  // A casa fecha. A cliente encomenda para amanhã e paga o Pix.
  await travelTo(new Date(afterClosing).toISOString(), [storeContext, gestorContext]);
  await store.goto("/menu");
  await settled(store);
  await expect(store.getByRole("banner").first()).toContainText(/Fechado agora\.\s*Abrimos amanhã/);
  await capture(store, testInfo, "loja-fechada");
  const ref = await customerOrdersPickupToday(store, testInfo, {
    product: PRODUCT,
    phone: newCustomerPhone(),
    name: "Helena",
    day: "Amanhã",
    window: "A partir das 9h",
    storeClosed: true,
  });
  await expect(store.getByRole("heading", { name: "Pedido recebido" })).toBeVisible();
  await expect(
    store.getByText(/^Pagamento recebido\. Estamos fechados agora e conferimos seu pedido quando abrirmos, amanhã/),
  ).toBeVisible();
  await capture(store, testInfo, "loja-confere-quando-abrir");

  // O Caixa abre o pedido: o prazo de aceite conta da abertura de amanhã, não de agora.
  await acknowledgeOtherOrdersAlarms(gestor, ref);
  await gestor.goto(`/${encodeURIComponent(ref)}`);
  await settled(gestor);
  const closedLeft = await minutesToDecide(gestor);
  const untilOpening = Math.round((opensAt - afterClosing) / MINUTE);
  expect(closedLeft, "o prazo inteiro começa na abertura").toBeGreaterThan(untilOpening);
  await capture(gestor, testInfo, "prazo-conta-da-abertura");

  // A casa abre. Ninguém tocou no pedido: ele espera, com o prazo que sobrou.
  const opened = opensAt + 5 * MINUTE;
  await travelTo(new Date(opened).toISOString(), [storeContext, gestorContext]);
  await gestor.reload();
  await settled(gestor);
  const openLeft = await minutesToDecide(gestor);
  const expected = closedLeft - Math.round((opened - afterClosing) / MINUTE);
  expect(Math.abs(openLeft - expected), `o prazo andou só com a casa aberta (${openLeft} min, esperado ${expected})`).toBeLessThanOrEqual(2);
  await capture(gestor, testInfo, "casa-abriu-prazo-andando");

  // O Caixa aceita pelo painel.
  await acknowledgeOtherOrdersAlarms(gestor, ref);
  await gestor.goto("/?view=board");
  await settled(gestor);
  await expect(orderCard(gestor, ref)).toBeVisible({ timeout: 60_000 });
  await cashierAccepts(gestor, ref);
  await capture(gestor, testInfo, "aceita");

  // A cliente: o acompanhamento diz que a loja aceitou, e a frase da loja fechada saiu.
  await store.reload();
  await settled(store);
  await expect(store.getByText(/^Pedido aceito\./).first()).toBeVisible({ timeout: 60_000 });
  await expect(store.getByText(/Estamos fechados agora/)).toHaveCount(0);
  await capture(store, testInfo, "loja-aceita");

  await storeContext.close();
  await gestorContext.close();
});
