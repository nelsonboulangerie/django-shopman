import { expect, type Page } from "@playwright/test";
import { shortCode } from "./gestor";

// A Cozinha na estação: o ticket chega sozinho (SSE). A estação mostra só os mais
// urgentes; o da jornada pode estar atrás de atrasados do seed ou de uma rodada que
// parou no meio. Quem está na bancada acha o pedido pelo código, na busca da estação,
// inicia o preparo do ticket e dá Pronto.
export async function kitchenMarksReady(page: Page, ref: string): Promise<void> {
  const code = shortCode(ref);
  const ticket = page.getByRole("article").filter({
    has: page.getByRole("button", { name: `Ver o detalhe do pedido ${code}`, exact: true }),
  });
  await expect(page.getByText(/na fila|A fazer/).first()).toBeVisible({ timeout: 120_000 });
  if (!(await ticket.isVisible().catch(() => false))) {
    await page.getByRole("button", { name: /^Buscar pedido por código/ }).click();
    await page.getByRole("textbox", { name: "Código, cliente ou item" }).pressSequentially(code);
    await page.getByRole("option", { name: `Filtrar os tickets por “${code}”` }).click();
  }
  await expect(ticket).toBeVisible({ timeout: 120_000 });

  const start = ticket.getByRole("button", { name: `Iniciar o preparo do pedido ${code}`, exact: true });
  if (await start.isVisible().catch(() => false)) {
    await start.click();
    await expect(start).toHaveCount(0, { timeout: 60_000 });
  }
  // O botão diz "Pronto N81"; o nome acessível é a frase inteira.
  const ready = ticket.getByRole("button", { name: `Marcar o pedido ${code} como pronto`, exact: true });
  await expect(ready).toBeVisible({ timeout: 60_000 });
  await ready.click();
}
