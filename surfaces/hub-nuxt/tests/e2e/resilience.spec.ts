import { test, expect } from "@playwright/test";

// Banner de conexão (kit) — global, aparece em qualquer estado do Shopman Apps.
test.describe("Shopman Apps — banner de conexão", () => {
  test("aparece ao cair a rede e some ao voltar", async ({ page, context }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Olá, Ana/i })).toBeVisible();

    await expect(page.getByText(/Sem conexão/i)).toHaveCount(0);
    await context.setOffline(true);
    await expect(page.getByText(/Sem conexão/i)).toBeVisible();
    await context.setOffline(false);
    await expect(page.getByText(/Sem conexão/i)).toHaveCount(0);
  });
});
