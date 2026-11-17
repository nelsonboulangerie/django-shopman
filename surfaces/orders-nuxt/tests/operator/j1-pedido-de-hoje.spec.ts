import { expect, test } from "@playwright/test";
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
import { capture, cast, newCustomerPhone, roleContext, stack } from "./support/stack";

// J1 (docs/plans/EXCELENCIA-GESTOR-PLANO.md, seção 8): pedido de hoje, de ponta a ponta.
// Cliente novo pede retirada para hoje e paga na loja (375 px); o Caixa, com PIN, aceita
// e inicia no Gestor (1366 px); a Cozinha dá Pronto na estação; o Caixa entrega.
//
// A ordem importa: o dispositivo do balcão fica pronto ANTES de o cliente pedir. Pedido
// pago tem poucos minutos para ser aceito antes de cancelar sozinho, e ninguém monta o
// balcão com o relógio correndo.
test("J1: pedido de retirada para hoje, da loja à entrega", async ({ browser, baseURL }, testInfo) => {
  // Balcão: a Gerente entra, vincula o dispositivo ao posto e o bloqueia; Fran entra com PIN.
  const gestorContext = await roleContext(browser, baseURL!);
  const gestor = await gestorContext.newPage();
  await acknowledgeOtherOrdersAlarms(gestor);
  await managerSignsIn(gestor);
  await managerBindsDevice(gestor, { name: "Gestor do balcão", kind: "Escritório" }, "/workstations");
  await gestor.goto("/");
  await managerChoosesPosto(gestor, "Gestor do balcão");
  await lockDevice(gestor);
  await capture(gestor, testInfo, "gestor-bloqueado");
  await operatorUnlocksWithPin(gestor, cast.cashier);
  await capture(gestor, testInfo, "gestor-caixa");

  // Cozinha: a Gerente abre a estação de Encomendas e bloqueia; Diofer entra com PIN.
  const kitchenContext = await roleContext(browser, stack.kitchen);
  const kitchen = await kitchenContext.newPage();
  await managerSignsIn(kitchen);
  await kitchen.getByRole("button", { name: "Usar sem vincular" }).click();
  await kitchen.getByRole("link", { name: /^Encomendas/ }).first().click();
  await expect(kitchen.getByRole("heading", { name: "Encomendas", level: 1 })).toBeVisible();
  await lockDevice(kitchen);
  await operatorUnlocksWithPin(kitchen, cast.kitchen);
  await capture(kitchen, testInfo, "cozinha-diofer");

  // Cliente novo, no celular: pede e paga.
  const storeContext = await roleContext(browser, stack.store, true);
  const store = await storeContext.newPage();
  const ref = await customerOrdersPickupToday(store, testInfo, { product: "Croissant", phone: newCustomerPhone(), name: "Teresa" });

  // Caixa: o pedido chega sozinho ao painel (SSE), sem recarregar a tela.
  await acknowledgeOtherOrdersAlarms(gestor, ref);
  await expect(orderCard(gestor, ref)).toBeVisible({ timeout: 60_000 });
  await capture(gestor, testInfo, "gestor-novo");
  await cashierAccepts(gestor, ref);
  await capture(gestor, testInfo, "gestor-aceito");
  await cashierStartsPreparing(gestor, ref);
  await capture(gestor, testInfo, "gestor-em-preparo");

  // Cozinha: o ticket aparece na estação e Diofer dá Pronto.
  await kitchenMarksReady(kitchen, ref);
  await capture(kitchen, testInfo, "cozinha-pronto");

  // Caixa: o pedido está pronto; o cliente chega e Fran entrega.
  await cashierDelivers(gestor, ref);
  await capture(gestor, testInfo, "gestor-entregue");

  // O cliente vê, no próprio acompanhamento, que retirou.
  await store.reload();
  await expect(store.getByText(/Retirado|Entregue/).first()).toBeVisible({ timeout: 60_000 });
  await capture(store, testInfo, "loja-retirado");
});
