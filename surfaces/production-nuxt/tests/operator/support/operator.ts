import type { Page } from "@playwright/test";

import {
  managerSignsIn,
  type Person,
} from "../../../../operator-kit/tests/support/operatorGestures";
import { settled } from "./stack";

// Os gestos comuns aos apps de operador (a Gerente entra com senha, alguém trava, quem vai
// operar toca no próprio nome e digita o PIN) moram no operator-kit
// (operator-kit/tests/support/operatorGestures.ts, #2580), os mesmos do PDV ao vivo e do
// Gestor. Aqui fica só o que é da Produção.
export { lockDevice } from "../../../../operator-kit/tests/support/operatorGestures";

/** Na tela de bloqueio: toca no próprio nome e digita o PIN no teclado da tela. Na
 *  Produção o quarto dígito já entra (medido em 23/11: o "4 de no mínimo" e o Confirmar
 *  que o gesto do kit espera não chegam a aparecer); se a tela ainda pedir, ela confirma.
 *  Entrou quando a tela de bloqueio sai. */
export async function operatorUnlocksWithPin(
  page: Page,
  who: Person,
): Promise<void> {
  const lock = page.getByRole("heading", {
    name: "Identifique-se para operar",
  });
  await lock.waitFor({ state: "visible", timeout: 30_000 });
  await page
    .getByRole("group", { name: "Quem está operando?" })
    .getByRole("button", { name: who.name, exact: true })
    .click();
  for (const digit of who.pin) {
    await page.getByRole("button", { name: digit, exact: true }).click();
  }
  const confirm = page.getByRole("button", { name: "Confirmar", exact: true });
  const gone = await lock.waitFor({ state: "hidden", timeout: 5_000 }).then(
    () => true,
    () => false,
  );
  if (!gone && (await confirm.isVisible().catch(() => false)))
    await confirm.click();
  await lock.waitFor({ state: "hidden", timeout: 60_000 });
  await settled(page);
}

/** A Gerente libera um dispositivo novo: entra com usuário e senha e, quando o app oferece
 *  vincular o dispositivo a um posto, segue sem vincular (a Produção não pede posto). */
export async function managerReleasesDevice(page: Page): Promise<void> {
  await managerSignsIn(page);
  const unbound = page
    .getByRole("button", { name: "Usar sem vincular" })
    .first();
  if (await unbound.isVisible().catch(() => false)) {
    await unbound.click();
    await unbound.waitFor({ state: "hidden", timeout: 30_000 });
  }
  await settled(page);
}
