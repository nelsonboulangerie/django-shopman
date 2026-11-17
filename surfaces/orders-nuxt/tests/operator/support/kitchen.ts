import { expect, type Page } from "@playwright/test";
import { shortCode } from "./gestor";

// A Cozinha na estação: o ticket chega sozinho (SSE) e quem está na bancada dá Pronto.
export async function kitchenMarksReady(page: Page, ref: string): Promise<void> {
  const code = shortCode(ref);
  const ready = page.getByRole("button", { name: new RegExp(`^Pronto ${code}\\b`) }).first();
  await expect(ready).toBeVisible({ timeout: 120_000 });
  await ready.click();
  // O Pronto tem uma janela de Desfazer; o ticket sai da fila quando ela fecha.
  await expect(page.getByRole("button", { name: new RegExp(`^Pronto ${code}\\b`) })).toHaveCount(0, { timeout: 60_000 });
}
