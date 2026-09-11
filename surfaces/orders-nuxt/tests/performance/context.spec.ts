import { readFileSync } from "node:fs";
import { test, expect } from "@playwright/test";

const auth = JSON.parse(readFileSync(new URL("../../../../.orders-lab/http-lab-auth.json", import.meta.url), "utf8"));
for (const back of ["link", "history"]) {
  test(`queue context survives detail and ${back} return`, async ({ page, context }) => {
    await context.addCookies(Object.entries(auth.cookies).map(([name, value]) => ({ name, value: String(value), url: "http://127.0.0.1:3005", sameSite: "Lax" as const })));
    await page.goto("/");
    const search = page.getByRole("searchbox", { name: "Buscar por código, cliente ou item (atalho: /)", exact: true });
    await search.fill("HTTP-LAB-500");
    await page.getByRole("button", { name: "Ver em tabela", exact: true }).click();
    await expect(page).toHaveURL(/view=table/);
    await expect(page).toHaveURL(/q=HTTP-LAB-500/);
    const link = page.getByRole("link", { name: "Abrir pedido HTTP-LAB-500-250", exact: true });
    const row = page.getByRole("row").filter({ has: link });
    await row.getByRole("button", { name: "Selecionar pedido", exact: true }).click();
    await link.scrollIntoViewIfNeeded();
    const scroll = await page.evaluate(() => window.scrollY);
    expect(scroll).toBeGreaterThan(100);
    await link.click();
    await expect(page.getByRole("link", { name: "Voltar para a fila", exact: true })).toBeVisible();
    if (back === "link") await page.getByRole("link", { name: "Voltar para a fila", exact: true }).click();
    else await page.goBack();
    await expect(search).toHaveValue("HTTP-LAB-500");
    await expect(page).toHaveURL(/view=table/);
    await expect(row.getByRole("button", { name: "Desmarcar pedido", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(link).toBeFocused();
    await expect.poll(async () => Math.abs((await page.evaluate(() => window.scrollY)) - scroll)).toBeLessThan(4);
  });
}
