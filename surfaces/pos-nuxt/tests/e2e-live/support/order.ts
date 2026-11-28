// Os gestos da encomenda no PDV, pela tela: abrir, identificar o cliente, escolher o
// dia e montar a comanda. Moravam na J5 (WP-E2, WP-E3); a J-P5 da Produção (WP-F13)
// usa os mesmos, então moram aqui.
import { expect, type Page } from "@playwright/test";

import { settled } from "./operator";
import { picksNextOpenDay, type ChosenDay } from "./schedule";

export interface Customer {
  name: string;
  phone: string;
}

export function exact(text: string) {
  return new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
}

export async function opensOrder(page: Page) {
  // A porta da encomenda é a seção Encomendas (rail no balcão, barra de baixo no
  // celular), e de lá "Nova encomenda".
  await page.getByRole("link", { name: /^Encomendas/ }).locator("visible=true").first().click();
  await settled(page);
  await page.getByRole("button", { name: /^Nova( encomenda)?$/ }).locator("visible=true").first().click({ timeout: 30_000 });
  // "Iniciar nova encomenda?": a próxima comanda livre fica em uso para montá-la.
  const start = page.getByRole("dialog", { name: "Iniciar nova encomenda?" });
  const heading = page.getByRole("heading", { name: /Nova encomenda|Preparar encomenda/ });
  await expect(async () => {
    if (await start.isVisible().catch(() => false)) {
      await start.getByRole("button", { name: "Iniciar encomenda", exact: true }).click({ timeout: 2000 });
    }
    await expect(heading).toBeVisible({ timeout: 2000 });
  }).toPass({ timeout: 60_000 });
}

export async function identifiesCustomer(page: Page, customer: Customer) {
  await page.getByRole("button", { name: "Identificar cliente" }).locator("visible=true").first().click();
  const search = page.getByRole("combobox", { name: "Buscar cliente" }).locator("visible=true").first();
  await search.click();
  await search.pressSequentially(customer.phone);
  const dialog = page.getByRole("dialog").filter({ has: page.getByRole("combobox", { name: "Buscar cliente" }) });
  await dialog.getByRole("option", { name: exact(customer.name) }).first().click({ timeout: 30_000 });
  // Escolher o cadastro pode fechar o diálogo sozinho; se não fechar, "Concluir".
  const done = dialog.getByRole("button", { name: "Concluir", exact: true });
  await expect(async () => {
    if (await done.isVisible().catch(() => false)) await done.click({ timeout: 2000 });
    await expect(dialog).toBeHidden({ timeout: 2000 });
  }).toPass({ timeout: 30_000 });
}

// A ordem do funil (WP-E13, #2754): depois do cliente vem "para quando", e só
// então o recebimento.
export async function schedulesNextOpenDayPickup(page: Page): Promise<ChosenDay> {
  const day = await picksNextOpenDay(page);
  const slot = page
    .locator('[data-order-step="schedule"]')
    .getByRole("button")
    .filter({ hasText: /\d{1,2}h|\d{2}:\d{2}/ })
    .and(page.locator(":enabled"))
    .first();
  await slot.click({ timeout: 30_000 });
  await page.getByRole("button", { name: "Continuar", exact: true }).click();
  await page.locator("[data-order-fulfillment-options]").getByRole("radio", { name: /^Retirada/ }).click();
  await page.getByRole("button", { name: /Montar encomenda/ }).click();
  await expect(page.getByPlaceholder(/Buscar produto/).locator("visible=true").first()).toBeVisible({ timeout: 30_000 });
  return day;
}

const MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

/**
 * Daqui a dez dias no relógio da loja, pulando o domingo (a casa não abre): a data do
 * laudo (P1-1). O seed planeja só a próxima semana, então a data não tem lote planejado.
 */
export function tenDaysAhead(): { iso: string; day: string; cell: RegExp; month: string } {
  return daysAhead(10);
}

/** `days` dias à frente no relógio da loja, pulando o domingo; cada jornada usa a sua. */
export function daysAhead(days: number): { iso: string; day: string; cell: RegExp; month: string } {
  const now = new Date(new Date().toLocaleString("en-US", { timeZone: "America/Sao_Paulo" }));
  now.setDate(now.getDate() + days);
  if (now.getDay() === 0) now.setDate(now.getDate() + 1);
  const dd = String(now.getDate()).padStart(2, "0");
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const month = `${MONTHS[now.getMonth()]} de ${now.getFullYear()}`;
  return { iso: `${now.getFullYear()}-${mm}-${dd}`, day: `${dd}/${mm}`, cell: new RegExp(`, ${now.getDate()} de ${month}$`), month };
}

/** "Outra data": a Fran escolhe o dia no calendário do kit, o turno, e monta a encomenda. */
export async function schedulesPickupOn(page: Page, target: { cell: RegExp; month: string }) {
  await page.locator('[data-day-option="other"]').locator("visible=true").first().click();
  const calendar = page.getByRole("dialog", { name: /^Abrir calendário/ });
  if (!(await calendar.isVisible().catch(() => false))) {
    await page.getByRole("button", { name: /^Abrir calendário/ }).locator("visible=true").first().click();
  }
  await expect(calendar).toBeVisible({ timeout: 10_000 });
  const cell = calendar.getByRole("button", { name: target.cell }).and(calendar.locator(":not([data-outside-view]):not([data-disabled])")).first();
  // O mês da data pode ser o próximo: avança só se a célula não está na grade aberta.
  if (!(await cell.waitFor({ timeout: 3000 }).then(() => true, () => false))) {
    await calendar.getByRole("button", { name: "Próximo mês" }).click();
  }
  await cell.click();
  await expect(calendar).toBeHidden({ timeout: 10_000 });
  const slot = page
    .locator('[data-order-step="schedule"]')
    .getByRole("button")
    .filter({ hasText: /\d{1,2}h|\d{2}:\d{2}/ })
    .and(page.locator(":enabled"))
    .first();
  await slot.click({ timeout: 30_000 });
  await page.getByRole("button", { name: "Continuar", exact: true }).click();
  await page.locator("[data-order-fulfillment-options]").getByRole("radio", { name: /^Retirada/ }).click();
  await page.getByRole("button", { name: /Montar encomenda/ }).click();
  await expect(page.getByPlaceholder(/Buscar produto/).locator("visible=true").first()).toBeVisible({ timeout: 30_000 });
}

/** O tile do produto pelo nome exato (há "Croissant Mini" ao lado do "Croissant"). */
export function tileOf(page: Page, product: string) {
  return page
    .locator("button[data-pos-product]")
    .filter({ has: page.locator("[data-pos-product-name]", { hasText: new RegExp(`^${product}$`) }) })
    .locator("visible=true")
    .first();
}

/** Lança o produto e digita a quantidade no editor da linha. */
export async function ordersQuantity(page: Page, product: string, qty: string) {
  const search = page.getByPlaceholder(/Buscar produto/).locator("visible=true").first();
  await search.click();
  await search.pressSequentially(product);
  await tileOf(page, product).click({ timeout: 30_000 });
  // A baguete fica pronta mais tarde que o turno escolhido: a tela oferece o turno
  // dela, e a Fran aceita (é o que o cliente ouviria).
  const later = page.getByRole("button", { name: /^Mudar para/ }).locator("visible=true").first();
  if (await later.waitFor({ timeout: 5000 }).then(() => true, () => false)) await later.click();
  // No celular a comanda é a folha de baixo: abre para ver a linha.
  const sheet = page.getByRole("button", { name: "Ver a comanda" }).locator("visible=true").first();
  if (await sheet.isVisible().catch(() => false)) await sheet.click();
  await page.locator("[data-item-select]").locator("visible=true").first().click();
  const touch = page.locator("[data-pos-touch-editor]").locator("visible=true").first();
  if (await touch.waitFor({ timeout: 3000 }).then(() => true, () => false)) {
    // Toque: o numérico da linha escreve a quantidade, e "Pronto" fecha.
    const editor = page.locator("[data-pos-line-editor]").locator("visible=true").first();
    for (const digit of qty) await editor.getByRole("button", { name: `Dígito ${digit}`, exact: true }).click();
    await editor.locator("[data-pos-line-editor-close]").click();
  } else {
    // Balcão: o teclado físico digita a quantidade da linha aberta.
    await page.keyboard.type(qty);
    await page.keyboard.press("Enter");
  }
}

