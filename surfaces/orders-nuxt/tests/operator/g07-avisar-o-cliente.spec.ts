import { expect, test } from "@playwright/test";
import { atCounterHour, backToRealTime, controlDir } from "./support/clock";
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
import { capture, cast, newCustomerPhone, roleContext, stack } from "./support/stack";

// WP-G07 (docs/plans/EXCELENCIA-GESTOR-PLANO.md): avisar o cliente com um toque.
// O cliente pede retirada para hoje e paga; o Caixa aceita, abre o pedido e, pelo ⋯,
// toca em "Avisar o cliente". Lê a mensagem pronta de cada aviso (o nome, o pedido e a
// hora já escritos), marca o que vai faltar e envia. A tela diz que o aviso foi para a
// fila e o recibo aparece no pedido com o nome do gesto. A pilha não manda nada de
// verdade: os adaptadores ficam inertes em DEBUG.
test.skip(!controlDir, "pede o relógio de teste da pilha (OPERATOR_CONTROL_DIR; README)");
test.afterAll(() => backToRealTime());

test("G07: avisar o cliente com um toque, lendo a mensagem antes de enviar", async ({ browser, baseURL }, testInfo) => {
  const at = await atCounterHour();
  const gestorContext = await roleContext(browser, baseURL!, false, at);
  const gestor = await gestorContext.newPage();
  await acknowledgeOtherOrdersAlarms(gestor);
  await managerSignsIn(gestor);
  await managerBindsDevice(gestor, { name: "Gestor do balcão", kind: "Escritório" }, "/workstations");
  await gestor.goto("/");
  await managerChoosesPosto(gestor, "Gestor do balcão");
  await lockDevice(gestor);
  await operatorUnlocksWithPin(gestor, cast.cashier);

  const storeContext = await roleContext(browser, stack.store, true, at);
  const store = await storeContext.newPage();
  const ref = await customerOrdersPickupToday(store, testInfo, { product: "Croissant", phone: newCustomerPhone(), name: "Teresa" });

  await acknowledgeOtherOrdersAlarms(gestor, ref);
  await expect(orderCard(gestor, ref)).toBeVisible({ timeout: 60_000 });
  await cashierAccepts(gestor, ref);
  await gestor.goto(`/${ref}`);
  await expect(gestor.getByRole("heading", { name: `Pedido ${shortCode(ref)}` }).first()).toBeVisible();

  // ⋯ do pedido → Avisar o cliente.
  await gestor.getByRole("button", { name: "Mais ações do pedido" }).filter({ visible: true }).first().click();
  const entry = gestor.locator('[data-action="customer-notice"]');
  await expect(entry).toContainText("Vai atrasar, faltou um item ou precisamos remarcar.");
  await gestor.waitForTimeout(400); // a gaveta termina de abrir
  await capture(gestor, testInfo, "menu-do-pedido-1366");
  await entry.click();
  await expect(gestor.locator("[data-detail-menu]")).toBeHidden();
  const dialog = gestor.getByRole("dialog", { name: `Avisar o cliente do pedido ${shortCode(ref)}` });
  await expect(dialog).toBeVisible();
  await gestor.waitForTimeout(400); // o diálogo termina de entrar
  // Sem escolha, nada a enviar.
  await expect(dialog.locator("[data-notice-send]")).toBeDisabled();
  // Nada vem marcado: o lugar da mensagem diz o que falta escolher.
  await expect(dialog.locator("[data-notice-message-pending]")).toHaveText("Escolha o aviso para ver a mensagem.");
  // Remarcar não cabe no pedido de hoje, e diz por quê.
  await expect(dialog.getByText("Só a encomenda tem data combinada para remarcar.")).toBeVisible();
  await capture(gestor, testInfo, "aviso-aberto-1366");

  // Vai atrasar: a nova previsão entre horas prontas, e a mensagem com ela.
  await dialog.getByRole("radio", { name: "Vai atrasar" }).click();
  await expect(dialog.locator("[data-notice-message-pending]")).toHaveText("Escolha a nova previsão para ver a mensagem.");
  await dialog.locator("[data-notice-etas]").getByRole("radio").first().click();
  await expect(dialog.locator("[data-notice-message]")).toContainText(
    `Oi, Teresa! Aqui é da Nelson Boulangerie 💛 Seu pedido ${shortCode(ref)} vai atrasar um pouco: a nova previsão é hoje, às `,
  );
  await capture(gestor, testInfo, "aviso-atraso-1366");

  // Faltou um item: marca o que vai faltar e lê a mensagem.
  await dialog.getByRole("radio", { name: "Faltou um item" }).click();
  await dialog.getByRole("checkbox", { name: /Croissant/ }).click();
  await expect(dialog.locator("[data-notice-message]")).toContainText("vai faltar o item Croissant (1 unidade), e sinto muito por isso.");
  await capture(gestor, testInfo, "aviso-falta-1366");

  // No celular, o mesmo diálogo, com o rodapé à vista.
  await gestor.setViewportSize({ width: 375, height: 812 });
  await expect(dialog.locator("[data-notice-send]")).toBeInViewport();
  await capture(gestor, testInfo, "aviso-falta-375");
  await gestor.setViewportSize({ width: 1366, height: 900 });

  // Enviar: a fila, nunca "enviado"; o recibo aparece no pedido com o nome do gesto.
  await dialog.locator("[data-notice-send]").click();
  await expect(gestor.getByText("Aviso na fila de envio. O recibo aparece em Avisos ao cliente, neste pedido.").first()).toBeVisible();
  await expect(dialog).toBeHidden();
  const receipts = gestor.locator("[data-notification-receipts]");
  await expect(receipts.getByText("Faltou um item", { exact: true })).toBeVisible({ timeout: 60_000 });
  // Nesta pilha nenhum canal aceita (os adaptadores estão inertes): todo recibo que
  // falhou traz o botão que resolve, o WhatsApp de quem está no balcão com o mesmo texto.
  await expect(receipts.locator("li", { hasText: "Faltou um item" }).locator("[data-receipt-fallback]")).toHaveAttribute("href", /^https:\/\/wa\.me\/\d+\?text=.*vai%20faltar%20o%20item%20Croissant/);
  await receipts.scrollIntoViewIfNeeded();
  await capture(gestor, testInfo, "aviso-recibo-1366");

  await gestorContext.close();
  await storeContext.close();
});
