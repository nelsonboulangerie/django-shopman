import { expect, type Locator, type Page } from "@playwright/test";

// Os gestos do Caixa no painel do Gestor, sempre pelo card do pedido.

/** O card do pedido no painel: o `article` que leva ao detalhe dele. */
export function orderCard(page: Page, ref: string): Locator {
  return page.getByRole("article").filter({ has: page.getByRole("link", { name: `Abrir pedido ${ref}`, exact: true }) });
}

/** O código curto que a tela mostra (NB-261116-W33 vira W33). */
export function shortCode(ref: string): string {
  return ref.split("-").pop()!;
}

/** Aceitar: pelo card, ou pelo alarme de pedido novo se ele já cobriu a tela. */
export async function cashierAccepts(page: Page, ref: string): Promise<void> {
  const alarm = page.getByRole("dialog").filter({ hasText: ref });
  if (await alarm.isVisible().catch(() => false)) {
    await alarm.getByRole("button", { name: "Aceitar", exact: true }).click();
  } else {
    await orderCard(page, ref).getByRole("button", { name: "Aceitar", exact: true }).click();
  }
  await expect(orderCard(page, ref).getByRole("button", { name: "Aceitar", exact: true })).toHaveCount(0, { timeout: 60_000 });
}

export async function cashierStartsPreparing(page: Page, ref: string): Promise<void> {
  const start = orderCard(page, ref).getByRole("button", { name: "Iniciar preparo", exact: true });
  await expect(start).toBeVisible({ timeout: 60_000 });
  await start.click();
  await expect(start).toHaveCount(0, { timeout: 60_000 });
}

/** Entregar ao cliente que veio buscar: o botão do card pronto ("Entregar W33 a Teresa"). */
export async function cashierDelivers(page: Page, ref: string): Promise<void> {
  const card = orderCard(page, ref);
  const deliver = card.getByRole("button", { name: new RegExp(`^Entregar( ${shortCode(ref)})?`) }).first();
  await expect(deliver).toBeVisible({ timeout: 120_000 });
  await deliver.click();
  await expect(card).toHaveCount(0, { timeout: 60_000 });
}
