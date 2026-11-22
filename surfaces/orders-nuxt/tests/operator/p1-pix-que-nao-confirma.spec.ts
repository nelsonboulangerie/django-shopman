import { expect, test } from "@playwright/test";
import { backToRealTime, controlDir, syncBrowserClock, travelTo } from "./support/clock";
import { customerOrdersPickupToday } from "./support/customer";
import { orderCard } from "./support/gestor";
import {
  acknowledgeOtherOrdersAlarms,
  lockDevice,
  managerBindsDevice,
  managerChoosesPosto,
  managerSignsIn,
  operatorUnlocksWithPin,
} from "./support/operator";
import { capture, cast, newCustomerPhone, roleContext, settled, stack } from "./support/stack";

// P1 (#2550: "pagamento que não confirma"): a cliente envia o pedido com Pix e não paga.
// O Caixa vê o pedido esperando o pagamento. O relógio da pilha passa do prazo do Pix: o
// worker pergunta ao gateway, não acha pagamento e cancela sem cobrar nada. O pedido sai
// do painel do Caixa sem ninguém tocar nele, e a cliente lê no acompanhamento que o Pix
// venceu e nada foi cobrado.
//
// O prazo do Pix é configuração do canal (padrão 5 min); a jornada anda 20 min.
const AFTER_THE_DEADLINE_MS = 20 * 60_000;

test.skip(!controlDir, "pede o relógio de teste da pilha (OPERATOR_CONTROL_DIR; README)");
test.afterAll(() => backToRealTime());

test("P1: o Pix que não confirma cancela sozinho, sem cobrar, e sai do painel", async ({ browser, baseURL }, testInfo) => {
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

  // A cliente envia o pedido e fica no acompanhamento, com o Pix por pagar.
  const storeContext = await roleContext(browser, stack.store, true);
  await syncBrowserClock(storeContext, new Date().toISOString());
  const store = await storeContext.newPage();
  const ref = await customerOrdersPickupToday(store, testInfo, {
    product: "Croissant",
    phone: newCustomerPhone(),
    name: "Sônia",
    pays: false,
  });

  // O Caixa vê o pedido esperando o pagamento.
  await acknowledgeOtherOrdersAlarms(gestor, ref);
  await gestor.goto("/?view=board");
  await settled(gestor);
  const card = orderCard(gestor, ref);
  await expect(card).toBeVisible({ timeout: 60_000 });
  await expect(card).toContainText(/Pix/);
  await card.scrollIntoViewIfNeeded();
  await capture(gestor, testInfo, "esperando-o-pix");

  // Passa o prazo do Pix. Ninguém toca no pedido: o worker cancela, e o painel acompanha.
  const later = new Date(Date.now() + AFTER_THE_DEADLINE_MS).toISOString();
  await travelTo(later, [gestorContext, storeContext]);
  await expect(async () => {
    await gestor.reload();
    await settled(gestor);
    await expect(orderCard(gestor, ref)).toHaveCount(0, { timeout: 5_000 });
  }).toPass({ timeout: 180_000 });
  await capture(gestor, testInfo, "saiu-do-painel");

  // O detalhe do pedido diz o que houve.
  await gestor.goto(`/${encodeURIComponent(ref)}`);
  await settled(gestor);
  await expect(gestor.getByText("Dinheiro do pedido cancelado: Nada foi cobrado")).toBeVisible({ timeout: 60_000 });
  await expect(gestor.getByText(/Prazo do pagamento · O Pix venceu/).first()).toBeVisible();
  await capture(gestor, testInfo, "detalhe-cancelado");

  // A cliente, no acompanhamento: o Pix venceu, nada foi cobrado.
  await store.reload();
  await settled(store);
  await expect(store.getByRole("heading", { name: "Pagamento expirado" })).toBeVisible({ timeout: 60_000 });
  await expect(store.getByText("O prazo para pagar acabou e cancelamos o pedido.")).toBeVisible();
  await expect(store.getByText("Nada foi cobrado.")).toBeVisible();
  await expect(store.getByRole("button", { name: "Repetir pedido" })).toBeVisible();
  await capture(store, testInfo, "loja-pix-venceu");

  await storeContext.close();
  await gestorContext.close();
});
