import { expect, type Locator, type Page } from "@playwright/test";
import { cast, settled } from "./stack";

// Os gestos do operador que valem para qualquer app de operador (Gestor, Cozinha):
// a Gerente entra com senha e abre o dispositivo; quem vai operar se identifica na
// tela de bloqueio e digita o PIN no teclado da tela.

/** A Gerente entra com usuário e senha. Se a tela devolve erro (o BFF desiste em ~30 s
 *  quando o Django demora) ou "Sua sessão terminou" (cookie velho, medido em 16/11), ela
 *  tenta de novo, como faria no balcão. */
export async function managerSignsIn(page: Page): Promise<void> {
  await page.goto("/");
  const signedOut = page.getByRole("textbox", { name: "Usuário" });
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await settled(page);
    await expect(signedOut).toBeVisible();
    await expect(signedOut).toBeEnabled({ timeout: 120_000 });
    await signedOut.fill("");
    await signedOut.pressSequentially(cast.manager.username);
    const password = page.getByRole("textbox", { name: "Senha" });
    await password.fill("");
    await password.pressSequentially(cast.manager.password);
    await page.getByRole("button", { name: "Entrar", exact: true }).click();
    // Entrou quando o campo de usuário some; senão a tela voltou com erro e ela tenta de novo.
    const done = await expect(signedOut).toBeHidden({ timeout: 120_000 }).then(() => true, () => false);
    if (!done) continue;
    await settled(page);
    if (!(await signedOut.isVisible().catch(() => false))) return;
  }
  throw new Error("A Gerente não conseguiu entrar com a senha de dev em três tentativas.");
}

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

/** Escolhe o posto no aviso "Vincular este dispositivo a um posto de trabalho?". */
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

/** Bloqueia o dispositivo para o próximo operador. */
export async function lockDevice(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Bloquear ou trocar de operador" }).click();
  await expect(page.getByRole("heading", { name: "Identifique-se para operar" })).toBeVisible();
}

/** Na tela de bloqueio: toca no próprio nome e digita o PIN no teclado da tela. */
export async function operatorUnlocksWithPin(page: Page, who: { name: string; pin: string }): Promise<void> {
  await expect(page.getByRole("heading", { name: "Identifique-se para operar" })).toBeVisible();
  await page.getByRole("group", { name: "Quem está operando?" }).getByRole("button", { name: who.name, exact: true }).click();
  await expect(page.getByText(who.name, { exact: true }).first()).toBeVisible();
  for (const digit of who.pin) {
    await page.getByRole("button", { name: digit, exact: true }).click();
  }
  await expect(page.getByText(`${who.pin.length} de no mínimo`)).toBeVisible();
  await page.getByRole("button", { name: "Confirmar", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Identifique-se para operar" })).toBeHidden({ timeout: 30_000 });
  // Quem está operando aparece no pé do menu lateral (Gestor e Cozinha).
  await expect(page.getByRole("complementary").getByText(who.name, { exact: true }).first()).toBeVisible();
}

/** No PDV a oferta do posto é um diálogo, que sobe sozinho depois do login da Gerente
 *  ("Vincular este dispositivo a um posto de trabalho?", operator-kit
 *  OperatorStationSetup); o seed cria o "PDV principal". Mesmo gesto do helper da suíte
 *  do PDV (pos-nuxt/tests/e2e-live/support/operator.ts). */
export async function managerBindsPosStation(page: Page, station = "PDV principal"): Promise<void> {
  const dialog = page.getByRole("dialog", { name: /Vincular este dispositivo/ });
  await expect(dialog).toBeVisible({ timeout: 60_000 });
  const choice = dialog.getByRole("combobox").first();
  if (!(await choice.textContent())?.includes(station)) {
    await choice.click();
    await page.getByRole("option", { name: station }).first().click();
    await expect(choice).toContainText(station);
  }
  await dialog.getByRole("button", { name: "Vincular a este posto", exact: true }).click();
  // Posto que já tem outro dispositivo: o servidor pede a segunda palavra.
  const shared = dialog.getByRole("button", { name: "Vincular também a este posto", exact: true });
  const next = await Promise.race([
    shared.waitFor({ state: "visible", timeout: 90_000 }).then(() => "shared", () => "gone"),
    dialog.waitFor({ state: "hidden", timeout: 90_000 }).then(() => "gone", () => "stuck"),
  ]);
  if (next === "shared") await shared.click();
  await expect(dialog).toBeHidden({ timeout: 90_000 });
  await settled(page);
}
