// A Produção na pilha do PDV ao vivo (J-P5, WP-F13): a Cozinha lê o pedido à Produção
// no Planejamento e planeja. Os gestos são os da suíte de operador da Produção
// (production-nuxt/tests/operator/support/operator.ts); não se importa de lá porque o
// módulo de pilha daquela suíte lê as variáveis dela ao carregar.
import { expect, type Page } from "@playwright/test";

import { managerSignsIn, settled, type Person } from "./operator";

export const productionUrl = (process.env.PDV_LIVE_PRODUCTION_URL || "").replace(/\/$/, "");

/** A Gerente libera um dispositivo novo da Produção, sem posto (a Produção não pede). */
export async function managerReleasesProductionDevice(page: Page): Promise<void> {
  await managerSignsIn(page);
  for (const name of ["Usar sem vincular", "Agora não"]) {
    const skip = page.getByRole("button", { name, exact: true }).first();
    if (await skip.isVisible().catch(() => false)) {
      await skip.click();
      await skip.waitFor({ state: "hidden", timeout: 30_000 });
    }
  }
  await settled(page);
}

/** Na tela de bloqueio da Produção: o próprio nome e o PIN no teclado da tela; o quarto
 *  dígito já entra, e o Confirmar só se a tela pedir. */
export async function unlocksProductionWithPin(page: Page, who: Person): Promise<void> {
  const lock = page.getByRole("heading", { name: "Identifique-se para operar" });
  await lock.waitFor({ state: "visible", timeout: 30_000 });
  await page.getByRole("group", { name: "Quem está operando?" }).getByRole("button", { name: who.name, exact: true }).click();
  for (const digit of who.pin) await page.getByRole("button", { name: digit, exact: true }).click();
  const confirm = page.getByRole("button", { name: "Confirmar", exact: true });
  if (await confirm.isVisible().catch(() => false)) await confirm.click();
  await lock.waitFor({ state: "hidden", timeout: 60_000 });
  await settled(page);
}

/** O Planejamento da data, aberto pela URL que o atalho da Produção carrega. */
export async function opensPlanning(page: Page, iso: string): Promise<void> {
  await page.goto(`/plan?date=${iso}`);
  await settled(page);
  await expect(page.locator("[data-plan-table], [data-plan-empty], [data-plan-promised-band]").first()).toBeVisible({ timeout: 60_000 });
}
