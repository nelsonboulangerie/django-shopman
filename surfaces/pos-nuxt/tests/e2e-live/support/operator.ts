import { test as base, expect, type Browser, type BrowserContext, type Page, type TestInfo } from "@playwright/test";

import {
  capture as captureStep,
  cast,
  devices,
  lockDevice,
  managerBindsStation as bindsStation,
  managerSignsIn,
  newDevice as newDeviceAt,
  operatorUnlocksWithPin,
  settled,
  type DeviceName,
  type Person,
} from "../../../../operator-kit/tests/support/operatorGestures";

// A fixture de operador do PDV ao vivo (WP-E12). Os gestos comuns (a Gerente entra e
// vincula o posto, alguém trava, a Caixa toca no nome e digita o PIN, a espera de
// hidratação, a captura numerada, um contexto por dispositivo) moram no operator-kit
// (operator-kit/tests/support/operatorGestures.ts, #2580), os mesmos da suíte do
// Gestor. Aqui fica só o que é do PDV: a pilha, o posto do seed e o quadro de comandas.

export { cast, devices, lockDevice, managerSignsIn, operatorUnlocksWithPin, settled, type DeviceName, type Person };

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

/** O posto que o seed cria (`cashman.Terminal` `pdv-main`). */
export const MAIN_STATION = "PDV principal";

/** Um dispositivo novo, no PDV da pilha quando outra URL não vem. */
export async function newDevice(browser: Browser, device: DeviceName, baseURL = stack.pos): Promise<BrowserContext> {
  return newDeviceAt(browser, device, baseURL);
}

/** Captura de um passo; com PDV_LIVE_SHOTS, vai também para lá, para levar ao PR. */
export async function capture(page: Page, testInfo: TestInfo, name: string): Promise<void> {
  await captureStep(page, testInfo, name, stack.shots);
}

/** A Gerente vincula o dispositivo ao posto; no PDV, o principal do seed. */
export async function managerBindsStation(page: Page, station = MAIN_STATION): Promise<void> {
  await bindsStation(page, station);
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
