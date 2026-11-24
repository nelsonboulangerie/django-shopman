import { mkdirSync } from "node:fs";
import { join } from "node:path";

import type { Browser, BrowserContext, Locator, Page, TestInfo } from "@playwright/test";

// Os gestos de operador pela tela, comuns aos apps de operador (#2580). Tudo aqui faz o
// que a PESSOA faz: a Gerente entra com senha e vincula o posto, alguém trava, quem vai
// operar toca no próprio nome e digita o PIN no teclado da tela. Nada cria estado por
// API, Admin ou banco, e o superusuário nunca entra. As telas são do kit (login,
// OperatorStationSetup, OperatorLock, OperatorSuiteShell), por isso os gestos moram aqui.
//
// Consumidores: a jornada ao vivo do PDV (pos-nuxt/tests/e2e-live/support/operator.ts) e
// a do Gestor (orders-nuxt/tests/operator/support/). Cada um guarda só o que é dele.
//
// ⚠️ Daqui só se importam TIPOS do Playwright. O kit tem o próprio `@playwright/test`, e
// importar o `expect` dele em tempo de execução carregaria uma segunda cópia na suíte do
// app ("Requiring @playwright/test second time"). Por isso as esperas são de locator
// (`waitFor`, clique de ensaio), que vêm da página do próprio app.

// ── O elenco ─────────────────────────────────────────────────────────────────
// shopman/shop/management/commands/setup_operators.py (o `seed` roda o comando). A
// Gerente tem senha porque é ela quem inicia o dispositivo; Caixa e Cozinha só têm PIN.
export const cast = {
  manager: { username: "joyce", name: "Joyce", password: "admin", pin: "1234" },
  cashier: { name: "Fran", pin: "1234" },
  kitchen: { name: "Diofer", pin: "1234" },
} as const;
export type Person = { name: string; pin: string };
export type Manager = Person & { username: string; password: string };

// ── Dispositivos ─────────────────────────────────────────────────────────────
// Os dois tamanhos reais: o celular de 375 px, com toque, e o balcão de 1366 px.
export const devices = {
  phone: { viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
  counter: { viewport: { width: 1366, height: 768 }, isMobile: false, hasTouch: false, deviceScaleFactor: 1 },
} as const;
export type DeviceName = keyof typeof devices;

/** Um contexto de navegador é um DISPOSITIVO novo: sem cookie, sem vínculo, sem "Usar sem
 *  vincular" lembrado. Um por dispositivo e por papel: cookies em 127.0.0.1 valem para
 *  todas as portas, e dois papéis no mesmo pote trocariam a sessão um do outro. */
export async function newDevice(browser: Browser, device: DeviceName, baseURL: string): Promise<BrowserContext> {
  return browser.newContext({ ...devices[device], baseURL, locale: "pt-BR", timezoneId: "America/Sao_Paulo" });
}

// ── Espera e registro ────────────────────────────────────────────────────────

/** Espera o Nuxt hidratar: digitar antes disso perde o texto (medido em 16/11). Os apps
 *  mantêm SSE aberto, então "networkidle" pode nunca chegar: é só um teto. */
export async function settled(page: Page): Promise<void> {
  await page.waitForLoadState("domcontentloaded");
  await page.waitForFunction(() => {
    const root = document.querySelector("#__nuxt") as (Element & { __vue_app__?: unknown }) | null;
    return Boolean(root?.__vue_app__);
  }, undefined, { timeout: 60_000 });
  await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
}

const captureCount = new Map<string, number>();

/** Captura numerada de um passo, anexada ao relatório (test-results). Com `shotsDir`, a
 *  mesma imagem vai também para lá, numa pasta por projeto e teste, para levar ao PR. */
export async function capture(page: Page, testInfo: TestInfo, name: string, shotsDir = ""): Promise<void> {
  const step = (captureCount.get(testInfo.testId) ?? 0) + 1;
  captureCount.set(testInfo.testId, step);
  const file = `${String(step).padStart(2, "0")}-${name}.png`;
  const path = testInfo.outputPath(file);
  await page.screenshot({ path });
  await testInfo.attach(name, { path, contentType: "image/png" });
  if (shotsDir) {
    // O describe entra no nome: é ele que diz o tamanho (375 px, 1366 px).
    const dir = join(shotsDir, testInfo.project.name, slug(testInfo.titlePath.slice(-2).join(" ")));
    mkdirSync(dir, { recursive: true });
    await page.screenshot({ path: join(dir, file) });
  }
}

function slug(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

/** Espera o locator sumir; `true` se sumiu dentro do prazo. */
async function goneWithin(locator: Locator, timeout: number): Promise<boolean> {
  return locator.waitFor({ state: "hidden", timeout }).then(() => true, () => false);
}

// ── Os gestos ────────────────────────────────────────────────────────────────

/** A Gerente entra com usuário e senha. Se a tela devolve erro (o BFF desiste em ~30 s
 *  quando o Django demora) ou "Sua sessão terminou" (cookie velho, medido em 16/11), ela
 *  tenta de novo, como faria no balcão. */
export async function managerSignsIn(page: Page, who: Manager = cast.manager): Promise<void> {
  await page.goto("/");
  const user = page.getByRole("textbox", { name: "Usuário" });
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await settled(page);
    // Clique de ensaio: espera o campo visível e habilitado, sem clicar.
    await user.click({ trial: true, timeout: 120_000 });
    await user.fill("");
    await user.pressSequentially(who.username);
    const password = page.getByRole("textbox", { name: "Senha" });
    await password.fill("");
    await password.pressSequentially(who.password);
    await page.getByRole("button", { name: "Entrar", exact: true }).click();
    // Entrou quando o campo de usuário some (entrar recarrega a página inteira); senão
    // a tela voltou com erro e ela tenta de novo.
    if (!(await goneWithin(user, 120_000))) continue;
    await settled(page);
    if (!(await user.isVisible().catch(() => false))) return;
  }
  throw new Error(`${who.name} não conseguiu entrar com a senha de dev em três tentativas.`);
}

/** A Gerente diz em que posto este dispositivo fica, no diálogo "Vincular este
 *  dispositivo a um posto de trabalho?" (OperatorStationSetup), que sobe sozinho logo
 *  depois do login dela. O seed cria o "PDV principal". */
export async function managerBindsStation(page: Page, station: string): Promise<void> {
  const dialog = page.getByRole("dialog", { name: /Vincular este dispositivo/ });
  await dialog.waitFor({ state: "visible", timeout: 60_000 });
  // Com um posto só, ele já vem escolhido; com mais de um, ela escolhe pelo nome.
  const choice = dialog.getByRole("combobox").first();
  if (!(await choice.textContent())?.includes(station)) {
    await choice.click();
    await page.getByRole("option", { name: station }).first().click();
    await choice.filter({ hasText: station }).waitFor({ state: "visible" });
  }
  await dialog.getByRole("button", { name: "Vincular a este posto", exact: true }).click();
  // Posto que já tem outro dispositivo (o celular e o balcão no mesmo posto): o servidor
  // pede a segunda palavra, e o botão vira "Vincular também a este posto".
  const shared = dialog.getByRole("button", { name: "Vincular também a este posto", exact: true });
  const next = await Promise.race([
    shared.waitFor({ state: "visible", timeout: 90_000 }).then(() => "shared", () => "gone"),
    dialog.waitFor({ state: "hidden", timeout: 90_000 }).then(() => "gone", () => "stuck"),
  ]);
  if (next === "shared") await shared.click();
  // Vincular recarrega o app no posto; na máquina carregada isso passa de 20 s.
  await dialog.waitFor({ state: "hidden", timeout: 90_000 });
  await settled(page);
}

const lockScreen = (page: Page) => page.getByRole("heading", { name: "Identifique-se para operar" });

/** Trava o dispositivo para o próximo operador, pelo caminho que a tela mostra: o
 *  "Bloquear" do rail ou do menu lateral, quando aparece; senão o trocador de seções do
 *  cabeçalho ("… trocar de seção ou de app"), que traz "Trocar ou bloquear" no pé
 *  (OperatorSuiteShell / OperatorSwitcher). */
export async function lockDevice(page: Page): Promise<void> {
  const direct = page.getByLabel("Bloquear ou trocar de operador").locator("visible=true").first();
  if (await direct.isVisible().catch(() => false)) {
    await direct.click();
  } else {
    await page.getByRole("button", { name: /trocar de seção ou de app/ }).locator("visible=true").first().click();
    await page.getByRole("button", { name: "Trocar ou bloquear", exact: true }).click({ timeout: 30_000 });
  }
  await lockScreen(page).waitFor({ state: "visible", timeout: 30_000 });
}

/** Na tela de bloqueio (OperatorLock): toca no próprio nome e digita o PIN no teclado da
 *  tela. A tela mostra o nome escolhido e conta os dígitos antes do Confirmar. */
export async function operatorUnlocksWithPin(page: Page, who: Person): Promise<void> {
  const lock = lockScreen(page);
  await lock.waitFor({ state: "visible", timeout: 30_000 });
  await page.getByRole("group", { name: "Quem está operando?" }).getByRole("button", { name: who.name, exact: true }).click();
  for (const digit of who.pin) {
    await page.getByRole("button", { name: digit, exact: true }).click();
  }
  // PIN de tamanho fixo (4, #3223): o último dígito envia sozinho e a trava fecha.
  // A regra antiga (de 4 a 8) conta "N de no mínimo 4" e pede o Confirmar.
  const opened = lock.waitFor({ state: "hidden", timeout: 60_000 }).then(() => "opened" as const);
  const asksConfirm = page
    .getByText(`${who.pin.length} de no mínimo`)
    .waitFor({ state: "visible", timeout: 60_000 })
    .then(() => "confirm" as const);
  if ((await Promise.race([opened, asksConfirm.catch(() => opened)])) === "confirm") {
    await page.getByRole("button", { name: "Confirmar", exact: true }).click();
  }
  await lock.waitFor({ state: "hidden", timeout: 60_000 });
  await settled(page);
}
