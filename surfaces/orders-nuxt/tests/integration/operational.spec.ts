import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test, expect, type Page } from "@playwright/test";

const lab = JSON.parse(readFileSync(new URL("../../../../.orders-lab/manifest.json", import.meta.url), "utf8"));

async function login(page: Page) {
  await page.goto("/");
  await page.getByRole("textbox", { name: "Usuário", exact: true }).fill("orders-lab");
  await page.getByLabel("Senha", { exact: true }).fill("synthetic-lab-only-20260910");
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Entre para operar" })).toHaveCount(0);
}

test("lost response after the Django commit queries receipt and advances only once", async ({ page }) => {
  await login(page);
  let posts = 0;
  let lookups = 0;
  await page.route(`**/api/v1/backstage/orders/${lab.advance_ref}/advance/**`, async (route) => {
    if (route.request().method() === "POST") {
      posts += 1;
      const response = await route.fetch(); // The real Nitro/Django command commits first.
      expect(response.status()).toBe(200);
      await route.abort("failed"); // Only the browser's response is lost.
    } else { lookups += 1; await route.continue(); }
  });
  await page.goto(`/${lab.advance_ref}`);
  await expect(page.getByRole("button", { name: "Iniciar preparo", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Iniciar preparo", exact: true }).click();
  await expect(page.getByRole("button", { name: "Marcar pronto", exact: true })).toBeVisible();
  const canonical = await (await page.request.get(`/api/v1/backstage/orders/${lab.advance_ref}/`)).json();
  expect(canonical.order.status).toBe("preparing");
  expect(posts).toBe(1);
  expect(lookups).toBe(1);
  await page.screenshot({ path: fileURLToPath(new URL("../../../../.orders-lab/integration-advance.png", import.meta.url)), fullPage: true });
});

test("SSE during notes draft preserves text and offers explicit same-field resolution", async ({ page }) => {
  await login(page);
  await page.goto(`/${lab.notes_ref}`);
  const editor = page.locator("textarea").first();
  await expect(editor).toHaveValue("Nota inicial");
  await editor.fill("Rascunho preservado");
  const fresh = await (await page.request.get(`/api/v1/backstage/orders/${lab.notes_ref}/`)).json();
  const action = fresh.order.actions.find((value: { ref: string }) => value.ref === "notes");
  const response = await page.request.post(`/api/v1/backstage/orders/${lab.notes_ref}/notes/`, {
    headers: { "Idempotency-Key": crypto.randomUUID() }, data: { ...action.payload_schema, notes: "Outra estação" },
  });
  expect(response.status()).toBe(200);
  await expect(page.getByText("No servidor: Outra estação")).toBeVisible();
  await expect(editor).toHaveValue("Rascunho preservado");
  await expect(page.getByRole("button", { name: "Salvar nota", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Manter meu texto", exact: true }).click();
  await page.getByRole("button", { name: "Salvar nota", exact: true }).click();
  await expect.poll(async () => (await (await page.request.get(`/api/v1/backstage/orders/${lab.notes_ref}/`)).json()).order.kitchen_note).toBe("Rascunho preservado");
  await page.screenshot({ path: fileURLToPath(new URL("../../../../.orders-lab/integration-notes.png", import.meta.url)), fullPage: true });
});

test("price preview confirms exact canonical values through Nitro and Django", async ({ page }) => {
  await login(page);
  await page.goto("/catalog");
  const matrix = await (await page.request.get("/api/v1/backstage/catalog/")).json();
  const before = matrix.matrix.rows.find((row: { sku: string }) => row.sku === "LAB-PROD").cells.find((cell: { surface_ref: string }) => cell.surface_ref === "lab").price_q;
  await page.locator('[data-dragkey="LAB-PROD"]').getByRole("checkbox").check();
  await page.locator('select').filter({ has: page.locator('option[value="*"]') }).selectOption("lab");
  await page.getByRole("button", { name: "Preço…", exact: true }).click();
  await page.getByPlaceholder("+10 ou -20").fill("10");
  await page.getByRole("button", { name: "Revisar alterações", exact: true }).click();
  await expect(page.getByText("Revise 1 células antes de confirmar")).toBeVisible();
  const unchanged = await (await page.request.get("/api/v1/backstage/catalog/")).json();
  expect(unchanged.matrix.rows.find((row: { sku: string }) => row.sku === "LAB-PROD").cells.find((cell: { surface_ref: string }) => cell.surface_ref === "lab").price_q).toBe(before);
  await page.screenshot({ path: fileURLToPath(new URL("../../../../.orders-lab/integration-price-preview.png", import.meta.url)), fullPage: true });
  const result = page.waitForResponse((response) => response.url().endsWith("/catalog/bulk-price/") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Confirmar alterações", exact: true }).click();
  expect((await (await result).json()).outcome).toBe("applied");
  const after = await (await page.request.get("/api/v1/backstage/catalog/")).json();
  expect(after.matrix.rows.find((row: { sku: string }) => row.sku === "LAB-PROD").cells.find((cell: { surface_ref: string }) => cell.surface_ref === "lab").price_q).toBe(Math.round(before * 1.1));
});
