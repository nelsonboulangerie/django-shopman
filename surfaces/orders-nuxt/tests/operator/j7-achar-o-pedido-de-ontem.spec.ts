import { expect, test } from "@playwright/test";
import {
  acknowledgeOtherOrdersAlarms,
  lockDevice,
  managerBindsDevice,
  managerChoosesPosto,
  managerSignsIn,
  operatorUnlocksWithPin,
} from "./support/operator";
import { capture, cast, roleContext, settled } from "./support/stack";

// J7 (docs/plans/EXCELENCIA-GESTOR-PLANO.md, seção 8): achar o pedido de ontem.
// A cliente liga: "o pedido de ontem". A Gerente, com PIN, abre o Histórico, busca pelo
// nome, lê que hoje não há nada dela, amplia o período com um toque e abre o pedido de
// ontem (WP-G04).
//
// A cliente é a Ana Ferreira do seed (`config/management/commands/seed.py`, CLI-005), que
// tem pedido concluído no dia anterior ao seed. Por isso a jornada pede a pilha semeada
// na véspera, ou num dia em que a Ana não tenha pedido concluído ainda: com pedido dela
// hoje, a lista já mostra o de hoje e não oferece ampliar.
const CUSTOMER = "Ana Ferreira";

test("J7: achar o pedido de ontem pelo nome, ampliando o período", async ({ browser, baseURL }, testInfo) => {
  const gestorContext = await roleContext(browser, baseURL!);
  const gestor = await gestorContext.newPage();
  await acknowledgeOtherOrdersAlarms(gestor);
  await managerSignsIn(gestor);
  await managerBindsDevice(gestor, { name: "Gestor do balcão", kind: "Escritório" }, "/workstations");
  await gestor.goto("/");
  await managerChoosesPosto(gestor, "Gestor do balcão");
  await lockDevice(gestor);
  await operatorUnlocksWithPin(gestor, cast.manager);

  // Histórico pelo menu, busca pelo nome.
  await gestor.getByRole("link", { name: "Histórico" }).first().click();
  await settled(gestor);
  await gestor.getByRole("button", { name: "Buscar pedido no histórico" }).click();
  await gestor.getByRole("textbox", { name: "Pedido, nome ou telefone" }).pressSequentially(CUSTOMER);
  await gestor.getByRole("option", { name: `Filtrar o histórico por “${CUSTOMER}”` }).click();
  await expect(gestor.getByText(`Nenhum pedido com “${CUSTOMER}” hoje`).first()).toBeVisible({ timeout: 60_000 });
  await capture(gestor, testInfo, "historico-hoje-vazio");

  // Um toque amplia o período, e o pedido de ontem aparece com o nome dela.
  await gestor.getByRole("button", { name: "Buscar nos últimos 28 dias" }).click();
  const yesterday = gestor.getByRole("row").filter({ hasText: /ontem às/ }).filter({ hasText: CUSTOMER }).first();
  await expect(yesterday).toBeVisible({ timeout: 60_000 });
  await capture(gestor, testInfo, "historico-28-dias");

  // Abre o pedido.
  const link = yesterday.getByRole("link").first();
  const ref = (await link.innerText()).trim();
  await link.click();
  await settled(gestor);
  await expect(gestor.getByText(ref).filter({ visible: true }).first()).toBeVisible({ timeout: 60_000 });
  await expect(gestor.getByText(CUSTOMER).filter({ visible: true }).first()).toBeVisible();
  await capture(gestor, testInfo, "pedido-de-ontem");
});
