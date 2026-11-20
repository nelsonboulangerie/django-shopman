import { expect, test } from "@playwright/test";
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

// J5 (docs/plans/EXCELENCIA-GESTOR-PLANO.md, seção 8): cancelar encomenda paga e ver o
// dinheiro. A cliente encomenda para amanhã e paga com Pix; a Gerente, com PIN, aceita,
// abre o detalhe e cancela antes do preparo, assinando com o próprio PIN. O detalhe diz
// o que acontece com o dinheiro: "Estorno pedido" enquanto o meio de pagamento não
// confirma, "Estornado" quando ele confirma (WP-G05).
test("J5: cancelar a encomenda paga antes do preparo e ver o dinheiro voltar", async ({ browser, baseURL }, testInfo) => {
  // Balcão: a Gerente abre o dispositivo, bloqueia e entra com o próprio PIN.
  const gestorContext = await roleContext(browser, baseURL!);
  const gestor = await gestorContext.newPage();
  await acknowledgeOtherOrdersAlarms(gestor);
  await managerSignsIn(gestor);
  await managerBindsDevice(gestor, { name: "Gestor do balcão", kind: "Escritório" }, "/workstations");
  await gestor.goto("/");
  await managerChoosesPosto(gestor, "Gestor do balcão");
  await lockDevice(gestor);
  await operatorUnlocksWithPin(gestor, cast.manager);

  // A cliente encomenda para amanhã e paga com Pix.
  const storeContext = await roleContext(browser, stack.store, true);
  const store = await storeContext.newPage();
  const ref = await customerOrdersPickupToday(store, testInfo, {
    product: "Croissant", phone: newCustomerPhone(), name: "Rosa", day: "Amanhã",
  });

  // A Gerente aceita a encomenda. Aceita, a encomenda de amanhã sai do painel do dia
  // (vai para as Encomendas), e a Gerente abre o pedido pelo endereço dele, o mesmo
  // destino da busca.
  await acknowledgeOtherOrdersAlarms(gestor, ref);
  await expect(orderCard(gestor, ref)).toBeVisible({ timeout: 60_000 });
  await cashierAccepts(gestor, ref);
  await gestor.goto(`/${ref}`);
  await settled(gestor);
  await expect(gestor.getByText("Aceito", { exact: true }).filter({ visible: true }).first()).toBeVisible({ timeout: 60_000 });

  // Cancelar pelo menu do pedido: motivo, e a assinatura de quem gerencia.
  await gestor.getByRole("button", { name: "Mais ações do pedido" }).click();
  await gestor.getByRole("button", { name: "Cancelar pedido (pede gerente)", exact: true }).click();
  const dialog = gestor.getByRole("dialog").filter({ has: gestor.getByRole("radio") });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/R\$ \d+,\d{2} serão estornados ao Pix do cliente\./)).toBeVisible();
  await dialog.getByRole("radio").first().click();
  await capture(gestor, testInfo, "gestor-cancelar-motivo");
  await dialog.getByRole("button", { name: /^Cancelar pedido/ }).last().click();

  // A autorização repete o destino do dinheiro; a Gerente escolhe o nome na lista e
  // digita o PIN no teclado da tela.
  const auth = gestor.getByRole("dialog").filter({ has: gestor.getByRole("heading", { name: "Autorizar cancelamento" }) });
  await expect(auth).toBeVisible({ timeout: 60_000 });
  await expect(auth.getByText(/R\$ \d+,\d{2} serão estornados ao Pix do cliente\./)).toBeVisible();
  await auth.getByRole("button", { name: new RegExp(cast.manager.name) }).first().click();
  for (const digit of cast.manager.pin) await auth.getByRole("button", { name: digit, exact: true }).click();
  await capture(gestor, testInfo, "gestor-cancelar-assinatura");
  await auth.getByRole("button", { name: "Confirmar", exact: true }).click();
  await expect(auth).toBeHidden({ timeout: 60_000 });

  // O detalhe diz o destino do dinheiro, e ele fecha quando o Pix confirma o estorno.
  await expect(gestor.getByText("Cancelado", { exact: true }).filter({ visible: true }).first()).toBeVisible({ timeout: 60_000 });
  await expect(gestor.getByText(/Estorno pedido|Estornado/).filter({ visible: true }).first()).toBeVisible({ timeout: 60_000 });
  await capture(gestor, testInfo, "gestor-cancelado-dinheiro");
  await expect(async () => {
    await gestor.reload();
    await settled(gestor);
    await expect(gestor.getByText("Estornado").filter({ visible: true }).first()).toBeVisible({ timeout: 5_000 });
  }).toPass({ timeout: 120_000 });
  await capture(gestor, testInfo, "gestor-estornado");

  // A cliente lê o cancelamento e a devolução no acompanhamento.
  await store.reload();
  await expect(store.getByText(/Devolvemos os R\$ \d+,\d{2} do seu Pix/).first()).toBeVisible({ timeout: 60_000 });
  await capture(store, testInfo, "loja-cancelado");
});
