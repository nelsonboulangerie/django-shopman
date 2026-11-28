// Devolver o lote que a jornada reservou (#2981).
//
// A J5 fecha uma encomenda de 200 Baguette de Tradition para a data, acima do lote
// planejado. Sem devolver, a passada seguinte no MESMO banco (o outro tamanho, ou a
// rodada de amanhã) encontrava o lote esgotado, o tile "Sem saldo para DD/MM", e
// parava antes de provar qualquer coisa. Cancelar pela tela, com o gerente, é o gesto
// que a casa já tem para isso (o mesmo da J6, P1-6): a reserva sai e o lote volta.
import { expect, type Page } from "@playwright/test";

import { cast, settled } from "./operator";

/**
 * Cancela pela tela a encomenda `ref`, paga em dinheiro: o motivo e o gerente da
 * lista com o próprio PIN. O dinheiro fica a devolver no caixa, como numa
 * desistência de verdade.
 */
export async function cancelsPaidPreorder(page: Page, ref: string): Promise<void> {
  await page.goto(`/preorders/${encodeURIComponent(ref)}`);
  await settled(page);
  await expect(page.getByRole("heading", { name: `Encomenda ${ref}` }).locator("visible=true").first()).toBeVisible({ timeout: 60_000 });
  if ((page.viewportSize()?.width ?? 0) >= 768) {
    await page.locator("[data-preorder-cancel]").locator("visible=true").first().click({ timeout: 30_000 });
  } else {
    // No celular, os gestos de uso médio moram no ⋮ da linha do chão.
    await page.getByRole("button", { name: /Mais ações|Opções/ }).locator("visible=true").first().click();
    await page.getByRole("menuitem", { name: "Cancelar encomenda" }).first().click();
  }
  const reasons = page.getByRole("dialog", { name: /^Cancelar a encomenda de/ });
  await expect(reasons).toBeVisible({ timeout: 30_000 });
  await reasons.locator('[data-reason-keyed] [role="radio"]').first().click();
  await reasons.locator("[data-reason-confirm]").click();

  const manager = page.getByRole("dialog", { name: "Autorizar cancelamento" });
  await expect(manager).toBeVisible({ timeout: 30_000 });
  // A prova é a resposta do cancelamento, não o aviso: cancelada, a encomenda sai das
  // Encomendas e a tela volta ao quadro, e o aviso "Encomenda cancelada." é breve. A
  // escuta nasce antes do PIN, porque o último dígito já pode cancelar.
  const cancelled = page.waitForResponse(
    (r) => r.url().includes(`/orders/${encodeURIComponent(ref)}/cancel/`) && r.request().method() === "POST",
    { timeout: 60_000 },
  );
  await manager.getByRole("button", { name: new RegExp(cast.manager.name) }).first().click();
  for (const digit of cast.manager.pin) await manager.getByRole("button", { name: digit, exact: true }).click();
  const confirm = manager.getByRole("button", { name: /^Confirmar|^Autorizar/ }).first();
  if (await confirm.isVisible({ timeout: 2000 }).catch(() => false)) await confirm.click();
  const response = await cancelled;
  expect(response.status(), `o cancelamento da encomenda ${ref}`).toBe(200);
  await expect(manager).toBeHidden({ timeout: 30_000 });
}
