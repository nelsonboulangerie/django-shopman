import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { test as base, expect, type Browser, type BrowserContext, type Page, type TestInfo } from "@playwright/test";

// A fixture de operador do PDV ao vivo (WP-E12). Tudo aqui faz o que a PESSOA faz,
// pela tela: a Gerente entra com senha e vincula o posto, alguém trava, a Caixa toca
// no próprio nome e digita o PIN. Nada cria estado por API, Admin ou banco, e o
// superusuário nunca entra. Os nomes dos gestos são os da suíte irmã do Gestor
// (surfaces/orders-nuxt/tests/operator/support/operator.ts, WP-G00): a peça comum
// mora no operator-kit quando a issue de extração (README) for feita.

// ── A pilha ──────────────────────────────────────────────────────────────────
// Quem sobe é `scripts/run_pos_e2e_live.sh`; aqui só se lê o que ele exportou.
export const stack = {
  pos: (process.env.PDV_LIVE_URL || "").replace(/\/$/, ""),
  kitchen: (process.env.PDV_LIVE_KITCHEN_URL || "").replace(/\/$/, ""),
  djangoLog: process.env.PDV_LIVE_DJANGO_LOG || "",
  shots: process.env.PDV_LIVE_SHOTS || "",
};

/** Recusa rodar sem a pilha: um teste que "passa" contra o Django errado não prova nada. */
export function requireStack(): void {
  if (!stack.pos || !stack.kitchen) {
    throw new Error(
      "Suba a pilha antes (scripts/run_pos_e2e_live.sh, README de tests/e2e-live). Faltam "
        + ["PDV_LIVE_URL", "PDV_LIVE_KITCHEN_URL"].filter((name) => !process.env[name]).join(", "),
    );
  }
}

// ── O elenco ─────────────────────────────────────────────────────────────────
// shopman/shop/management/commands/setup_operators.py (o `seed` roda o comando).
// A Gerente tem senha porque é ela quem inicia o dispositivo; a Caixa só tem PIN.
export const cast = {
  manager: { username: "joyce", name: "Joyce", password: "admin", pin: "1234" },
  cashier: { name: "Fran", pin: "1234" },
  kitchen: { name: "Diofer", pin: "1234" },
} as const;
export type Person = { name: string; pin: string };

/** O posto que o seed cria (`cashman.Terminal` `pdv-main`). */
export const MAIN_STATION = "PDV principal";

// ── Dispositivos ─────────────────────────────────────────────────────────────
// Os dois tamanhos que todo WP do PDV prova (EXCELENCIA-base: "de dispositivo e
// tamanho reais"): o celular de 375 px, com toque, e o balcão de 1366 px.
export const devices = {
  phone: { viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
  counter: { viewport: { width: 1366, height: 768 }, isMobile: false, hasTouch: false, deviceScaleFactor: 1 },
} as const;
export type DeviceName = keyof typeof devices;

/** Um contexto de navegador é um DISPOSITIVO novo: sem cookie, sem vínculo, sem
 *  "Usar sem vincular" lembrado. Um por dispositivo, nunca dois papéis no mesmo. */
export async function newDevice(browser: Browser, device: DeviceName, baseURL = stack.pos): Promise<BrowserContext> {
  return browser.newContext({ ...devices[device], baseURL, locale: "pt-BR", timezoneId: "America/Sao_Paulo" });
}

// ── Espera e registro ────────────────────────────────────────────────────────

/** Espera o Nuxt hidratar: digitar antes disso perde o texto (medido em 16/11). O
 *  PDV mantém SSE aberto, então "networkidle" pode nunca chegar: é só um teto. */
export async function settled(page: Page): Promise<void> {
  await page.waitForLoadState("domcontentloaded");
  await page.waitForFunction(() => {
    const root = document.querySelector("#__nuxt") as (Element & { __vue_app__?: unknown }) | null;
    return Boolean(root?.__vue_app__);
  }, undefined, { timeout: 60_000 });
  await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
}

const captureCount = new Map<string, number>();
/** Captura de um passo: anexada ao relatório e gravada em test-results/live (e em
 *  PDV_LIVE_SHOTS, se a variável vier, para levar ao PR). */
export async function capture(page: Page, testInfo: TestInfo, name: string): Promise<void> {
  const step = (captureCount.get(testInfo.testId) ?? 0) + 1;
  captureCount.set(testInfo.testId, step);
  const file = `${String(step).padStart(2, "0")}-${name}.png`;
  const path = testInfo.outputPath(file);
  await page.screenshot({ path });
  await testInfo.attach(name, { path, contentType: "image/png" });
  if (stack.shots) {
    // O describe entra no nome: é ele que diz o tamanho (375 px, 1366 px).
    const dir = join(stack.shots, testInfo.project.name, slug(testInfo.titlePath.slice(-2).join(" ")));
    mkdirSync(dir, { recursive: true });
    await page.screenshot({ path: join(dir, file) });
  }
}
function slug(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

// ── Os gestos ────────────────────────────────────────────────────────────────

/** A Gerente entra com usuário e senha na tela "Entre para operar o caixa". */
export async function managerSignsIn(page: Page, who = cast.manager): Promise<void> {
  await page.goto("/");
  await settled(page);
  const user = page.getByRole("textbox", { name: "Usuário" });
  await expect(user).toBeVisible({ timeout: 60_000 });
  await user.click();
  await user.pressSequentially(who.username);
  const password = page.getByRole("textbox", { name: "Senha" });
  await password.click();
  await password.pressSequentially(who.password);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  // Entrar recarrega a página inteira; a tela de senha some quando a sessão volta.
  await expect(user).toBeHidden({ timeout: 90_000 });
  await settled(page);
}

/** A Gerente diz em que posto este dispositivo fica. No PDV a oferta é um diálogo
 *  ("Vincular este dispositivo a um posto de trabalho?", operator-kit
 *  OperatorStationSetup), que sobe sozinho logo depois do login dela. */
export async function managerBindsStation(page: Page, station = MAIN_STATION): Promise<void> {
  const dialog = page.getByRole("dialog", { name: /Vincular este dispositivo/ });
  await expect(dialog).toBeVisible({ timeout: 60_000 });
  // Com um posto só, ele já vem escolhido; com mais de um, ela escolhe pelo nome.
  const choice = dialog.getByRole("combobox").first();
  if (!(await choice.textContent())?.includes(station)) {
    await choice.click();
    await page.getByRole("option", { name: station }).first().click();
    await expect(choice).toContainText(station);
  }
  await dialog.getByRole("button", { name: "Vincular a este posto", exact: true }).click();
  // Posto que já tem outro dispositivo (o celular e o balcão no mesmo PDV principal):
  // o servidor pede a segunda palavra, e o botão vira "Vincular também a este posto".
  const shared = dialog.getByRole("button", { name: "Vincular também a este posto", exact: true });
  const next = await Promise.race([
    shared.waitFor({ state: "visible", timeout: 90_000 }).then(() => "shared", () => "gone"),
    dialog.waitFor({ state: "hidden", timeout: 90_000 }).then(() => "gone", () => "stuck"),
  ]);
  if (next === "shared") await shared.click();
  // Vincular recarrega o app no posto; na máquina carregada isso passa de 20 s.
  await expect(dialog).toBeHidden({ timeout: 90_000 });
  await settled(page);
}

/** Trava o dispositivo para o próximo operador, pelo caminho que a tela mostra: o
 *  "Bloquear" do rail, quando há rail; senão o trocador de seções do cabeçalho
 *  ("… trocar de seção ou de app"), que traz "Trocar ou bloquear" no pé
 *  (operator-kit OperatorSuiteShell / OperatorSwitcher). */
export async function lockDevice(page: Page): Promise<void> {
  const rail = page.getByLabel("Bloquear ou trocar de operador").locator("visible=true").first();
  if (await rail.isVisible().catch(() => false)) {
    await rail.click();
  } else {
    await page.getByRole("button", { name: /trocar de seção ou de app/ }).locator("visible=true").first().click();
    await page.getByRole("button", { name: "Trocar ou bloquear", exact: true }).click({ timeout: 30_000 });
  }
  await expect(page.getByRole("heading", { name: "Identifique-se para operar" })).toBeVisible({ timeout: 30_000 });
}

/** Na tela de bloqueio: toca no próprio nome e digita o PIN no teclado da tela. */
export async function operatorUnlocksWithPin(page: Page, who: Person): Promise<void> {
  const lock = page.getByRole("heading", { name: "Identifique-se para operar" });
  await expect(lock).toBeVisible({ timeout: 30_000 });
  await page.getByRole("group", { name: "Quem está operando?" }).getByRole("button", { name: who.name, exact: true }).click();
  for (const digit of who.pin) {
    await page.getByRole("button", { name: digit, exact: true }).click();
  }
  await page.getByRole("button", { name: "Confirmar", exact: true }).click();
  await expect(lock).toBeHidden({ timeout: 60_000 });
  await settled(page);
}

/** Quem opera agora é `who`, como a pessoa confere: no balcão o nome está no rail; no
 *  celular abre o trocador de seções, lê "Operando: <nome>" no pé e fecha. */
export async function seesOperator(page: Page, who: Person): Promise<void> {
  const onRail = page.getByText(who.name, { exact: true }).locator("visible=true").first();
  if (await onRail.isVisible().catch(() => false)) return;
  await page.getByRole("button", { name: /trocar de seção ou de app/ }).locator("visible=true").first().click();
  await expect(page.getByLabel("Quem opera")).toContainText(`Operando: ${who.name}`, { timeout: 30_000 });
  await page.keyboard.press("Escape");
  await expect(page.getByLabel("Quem opera")).toBeHidden();
}

/** O quadro de comandas do PDV está na tela. */
export async function seesTabs(page: Page): Promise<void> {
  await expect(page.getByRole("button", { name: /Próxima livre/ }).first()).toBeVisible({ timeout: 60_000 });
}

// ── Fixture ──────────────────────────────────────────────────────────────────

type LiveFixtures = {
  /** Tamanho do dispositivo do teste (`test.use({ device: "phone" })`). */
  device: DeviceName;
  /** Um dispositivo novo em folha no PDV, ninguém identificado. */
  freshDevice: Page;
  /** O ponto de partida de toda jornada J1 a J10: o dispositivo iniciado pela
   *  Gerente no PDV principal, travado, e a Caixa (Fran) operando no quadro. */
  cashierAtCounter: Page;
};

export const test = base.extend<LiveFixtures>({
  device: ["counter", { option: true }],
  freshDevice: async ({ browser, device }, use) => {
    requireStack();
    const context = await newDevice(browser, device);
    const page = await context.newPage();
    await use(page);
    await context.close();
  },
  cashierAtCounter: async ({ freshDevice: page }, use) => {
    await managerSignsIn(page);
    await managerBindsStation(page);
    await lockDevice(page);
    await operatorUnlocksWithPin(page, cast.cashier);
    await seesTabs(page);
    await use(page);
  },
});

export { expect };
