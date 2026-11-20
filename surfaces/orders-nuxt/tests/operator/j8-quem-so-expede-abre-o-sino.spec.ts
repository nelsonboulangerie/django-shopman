import { expect, test } from "@playwright/test";
import { customerCancelsOwnOrder, customerOrdersPickupToday } from "./support/customer";
import { shortCode } from "./support/gestor";
import {
  acknowledgeOtherOrdersAlarms,
  lockDevice,
  managerBindsDevice,
  managerChoosesPosto,
  managerSignsIn,
  operatorUnlocksWithPin,
} from "./support/operator";
import { capture, cast, newCustomerPhone, roleContext, settled, stack } from "./support/stack";

// J8 (docs/plans/EXCELENCIA-GESTOR-PLANO.md, seção 8): quem só expede abre o sino.
// A cliente pede e paga, e cancela sozinha na loja antes do preparo: o Gestor recebe o
// aviso "O cliente cancelou o pedido…" no sino. Quem está no Gestor é a Cozinha (Diofer,
// só expede, com PIN): ela toca no aviso, e o detalhe do pedido diz por que não abre e
// para onde ela volta, sem "tentar de novo" (WP-G05, P1-20).
test("J8: quem só expede abre um aviso de pedido no sino e lê por que o detalhe não abre", async ({ browser, baseURL }, testInfo) => {
  // Balcão: a Gerente abre o dispositivo e o bloqueia; Diofer, da Cozinha, entra com PIN.
  const gestorContext = await roleContext(browser, baseURL!);
  const gestor = await gestorContext.newPage();
  await acknowledgeOtherOrdersAlarms(gestor);
  await managerSignsIn(gestor);
  await managerBindsDevice(gestor, { name: "Gestor do balcão", kind: "Escritório" }, "/workstations");
  await gestor.goto("/");
  await managerChoosesPosto(gestor, "Gestor do balcão");
  await lockDevice(gestor);
  await operatorUnlocksWithPin(gestor, cast.kitchen);

  // A cliente pede, paga e cancela sozinha antes do preparo.
  const storeContext = await roleContext(browser, stack.store, true);
  const store = await storeContext.newPage();
  const ref = await customerOrdersPickupToday(store, testInfo, { product: "Croissant", phone: newCustomerPhone(), name: "Lúcia" });
  await customerCancelsOwnOrder(store, testInfo);

  // Diofer abre o sino e acha o aviso do pedido.
  await acknowledgeOtherOrdersAlarms(gestor, ref);
  await gestor.getByRole("button", { name: /^Avisos/ }).first().click();
  const notice = gestor.getByRole("dialog").getByText(`O cliente cancelou o pedido ${ref} antes do preparo.`, { exact: false });
  await expect(notice).toBeVisible({ timeout: 60_000 });
  await capture(gestor, testInfo, "gestor-sino");

  // Toca no aviso: o detalhe recusa com o porquê e devolve a pessoa à Saída.
  const open = gestor.getByRole("dialog").getByRole("link", { name: "Abrir o pedido" }).and(gestor.locator(`a[href$="/${ref}"]`));
  await open.click();
  await settled(gestor);
  await expect(gestor.getByText("Sua conta não abre o detalhe do pedido")).toBeVisible({ timeout: 60_000 });
  // A frase que segue ("continua no painel da Saída") é falsa para o pedido cancelado:
  // #2879. A jornada confere só o que é verdade em todo estado.
  const description = gestor.getByText(`O detalhe é de quem gerencia pedidos. O pedido ${shortCode(ref)}`, { exact: false });
  await expect(description).toBeVisible();
  await expect(gestor.getByRole("link", { name: "Abrir a Saída" })).toBeVisible();
  // Nada de "tentar de novo": quem não abre é a conta, não a rede.
  await expect(gestor.getByRole("button", { name: /Tentar de novo/ })).toHaveCount(0);
  await capture(gestor, testInfo, "gestor-detalhe-recusado");
});
