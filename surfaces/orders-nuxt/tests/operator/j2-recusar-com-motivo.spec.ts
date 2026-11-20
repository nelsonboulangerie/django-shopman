import { expect, test } from "@playwright/test";
import { customerOrdersPickupToday } from "./support/customer";
import { cashierOpensReject, orderCard, shortCode } from "./support/gestor";
import {
  acknowledgeOtherOrdersAlarms,
  lockDevice,
  managerBindsDevice,
  managerChoosesPosto,
  managerSignsIn,
  operatorUnlocksWithPin,
} from "./support/operator";
import { capture, cast, newCustomerPhone, roleContext, stack } from "./support/stack";

// J2 (docs/plans/EXCELENCIA-GESTOR-PLANO.md, seção 8): recusar com motivo.
// O cliente pede retirada para hoje e paga com Pix; o Caixa, com PIN, toca em Recusar
// no cartão e lê no diálogo qual pedido é e o que acontece com o dinheiro ANTES de
// confirmar (WP-G06); escolhe o motivo, confirma, e o cliente lê o cancelamento com a
// frase do motivo na loja.
test("J2: recusar um pedido pago, lendo o destino do dinheiro antes de confirmar", async ({ browser, baseURL }, testInfo) => {
  // Balcão pronto antes de o cliente pedir: pedido pago tem poucos minutos de aceite.
  const gestorContext = await roleContext(browser, baseURL!);
  const gestor = await gestorContext.newPage();
  await acknowledgeOtherOrdersAlarms(gestor);
  await managerSignsIn(gestor);
  await managerBindsDevice(gestor, { name: "Gestor do balcão", kind: "Escritório" }, "/workstations");
  await gestor.goto("/");
  await managerChoosesPosto(gestor, "Gestor do balcão");
  await lockDevice(gestor);
  await operatorUnlocksWithPin(gestor, cast.cashier);

  // Cliente novo, no celular: pede e paga com Pix.
  const storeContext = await roleContext(browser, stack.store, true);
  const store = await storeContext.newPage();
  const ref = await customerOrdersPickupToday(store, testInfo, { product: "Croissant", phone: newCustomerPhone(), name: "Teresa" });

  // Caixa: o pedido chega ao painel e ele toca em Recusar no cartão.
  await acknowledgeOtherOrdersAlarms(gestor, ref);
  await expect(orderCard(gestor, ref)).toBeVisible({ timeout: 60_000 });
  const dialog = await cashierOpensReject(gestor, ref);

  // O diálogo diz QUAL pedido (código no título, quem pediu) e o destino do dinheiro.
  await expect(dialog.getByRole("heading", { name: `Recusar o pedido ${shortCode(ref)}?` })).toBeVisible();
  await expect(dialog.locator("[data-reason-order-customer]")).toHaveText("Teresa");
  await expect(dialog.locator("[data-reason-order-total]")).toHaveText(/^R\$ \d+,\d{2}$/);
  await expect(dialog.locator("[data-reason-money]")).toHaveText(/^R\$ \d+,\d{2} serão estornados ao Pix do cliente\.$/);
  // Retirada paga: os motivos que o pedido desmente não são oferecidos.
  await expect(dialog.getByRole("radio", { name: "Não dá para entregar" })).toHaveCount(0);
  await expect(dialog.getByRole("radio", { name: "Pagamento não confirmado" })).toHaveCount(0);
  // Sem motivo, o confirmar espera, e está à vista.
  const confirm = dialog.getByRole("button", { name: "Recusar pedido", exact: true });
  await expect(confirm).toBeInViewport();
  await expect(confirm).toBeDisabled();
  await capture(gestor, testInfo, "gestor-recusar-aberto");

  await dialog.getByRole("radio", { name: "Acabou um item" }).click();
  await expect(dialog.getByText("Um dos itens acabou e não conseguimos preparar o pedido completo.")).toBeVisible();
  await expect(confirm).toBeEnabled();
  await capture(gestor, testInfo, "gestor-recusar-motivo");
  await confirm.click();
  await expect(dialog).toBeHidden({ timeout: 60_000 });
  await expect(orderCard(gestor, ref)).toHaveCount(0, { timeout: 60_000 });
  await capture(gestor, testInfo, "gestor-recusado");

  // O cliente lê, no próprio acompanhamento, o cancelamento com a frase do motivo.
  await store.reload();
  await expect(store.getByText("Um dos itens acabou e não conseguimos preparar o pedido completo.").first()).toBeVisible({ timeout: 60_000 });
  await capture(store, testInfo, "loja-recusado");
});
