import { expect, type Locator, type Page } from "@playwright/test";

import {
  operatorUnlocksWithPin as unlocksWithPin,
  type Person,
} from "../../../../operator-kit/tests/support/operatorGestures";
import { settled } from "./stack";

// Os gestos comuns aos apps de operador (a Gerente entra com senha e vincula o posto,
// alguém trava, quem vai operar se identifica e digita o PIN) moram no operator-kit
// (operator-kit/tests/support/operatorGestures.ts, #2580), os mesmos do PDV ao vivo.
// Aqui fica só o que é do Gestor: a tela de Postos, o alarme de outro pedido e o nome de
// quem opera no menu lateral.

export { lockDevice, managerBindsStation, managerSignsIn } from "../../../../operator-kit/tests/support/operatorGestures";

const alarms = new WeakMap<Page, Locator>();

/** O alarme "Pedido novo sem aceite" de OUTRO pedido (o seed, uma execução anterior
 *  que parou no meio) cobre a tela inteira e pode subir a qualquer momento. Quem está
 *  no Gestor dá "Visto" nele, como faria; o do pedido da jornada fica intocado. Chame de
 *  novo com o ref quando o pedido da jornada nascer. */
export async function acknowledgeOtherOrdersAlarms(page: Page, ownRef?: string): Promise<void> {
  const previous = alarms.get(page);
  if (previous) await page.removeLocatorHandler(previous);
  const alarm = page.getByRole("dialog").filter({ has: page.getByRole("heading", { name: "Pedido novo sem aceite" }) });
  const foreign = ownRef ? alarm.filter({ hasNotText: ownRef }) : alarm;
  alarms.set(page, foreign);
  await page.addLocatorHandler(foreign, async (dialog) => {
    await dialog.getByRole("button", { name: "Visto", exact: true }).click();
  });
}

/** A Gerente vincula o dispositivo a um posto do tipo dado; cria o posto antes, pela
 *  tela de Postos do Gestor, se ele ainda não existir. */
export async function managerBindsDevice(page: Page, posto: { name: string; kind: string }, workstationsUrl: string): Promise<void> {
  await page.goto(workstationsUrl);
  await settled(page);
  await expect(page.getByRole("heading", { name: "Postos", level: 1 })).toBeVisible();
  const existing = page.getByRole("main").getByText(posto.name, { exact: true }).first();
  if (!(await existing.isVisible().catch(() => false))) {
    await page.getByRole("textbox", { name: "Nome do posto" }).pressSequentially(posto.name);
    await page.getByRole("combobox", { name: "Tipo" }).first().click();
    await page.getByRole("option", { name: posto.kind, exact: true }).click();
    await page.getByRole("button", { name: "Criar posto" }).click();
    await expect(existing).toBeVisible();
  }
}

/** Escolhe o posto pelo aviso "Vincular a este posto" do Gestor, que abre o diálogo
 *  "Vincular este dispositivo a um posto de trabalho?" com o campo "Posto:". */
export async function managerChoosesPosto(page: Page, postoName: string): Promise<void> {
  await settled(page);
  await page.getByRole("button", { name: "Vincular a este posto" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Vincular este dispositivo a um posto de trabalho?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("combobox", { name: "Posto:" }).click();
  await page.getByRole("option", { name: postoName, exact: true }).first().click();
  await dialog.getByRole("button", { name: /^Vincular/ }).click();
  // Vincular recarrega o app no posto; na máquina carregada isso passa de 20 s.
  await expect(dialog).toBeHidden({ timeout: 120_000 });
  await settled(page);
}

/** O gesto do kit, e a confirmação do Gestor e da Cozinha: quem está operando aparece no
 *  pé do menu lateral. */
export async function operatorUnlocksWithPin(page: Page, who: Person): Promise<void> {
  await unlocksWithPin(page, who);
  await expect(page.getByRole("complementary").getByText(who.name, { exact: true }).first()).toBeVisible();
}
