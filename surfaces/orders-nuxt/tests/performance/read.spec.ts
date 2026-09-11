import { readFileSync, writeFileSync } from "node:fs";
import { test, expect } from "@playwright/test";

const n = Number(process.env.ORDERS_PERF_N);
if (![1, 10, 100, 500].includes(n)) throw new Error("Declare the seeded synthetic queue size");
const root = new URL("../../../../.orders-lab/", import.meta.url);
const auth = JSON.parse(readFileSync(new URL("http-lab-auth.json", root), "utf8"));

test("rendered queue becomes usable and filtering remains local", async ({ browser }) => {
  const samples = [];
  const context = await browser.newContext();
  await context.addCookies(Object.entries(auth.cookies).map(([name, value]) => ({ name, value: String(value), url: "http://127.0.0.1:3005", sameSite: "Lax" as const })));
  try {
    for (let sample = 0; sample < 20; sample++) {
      const page = await context.newPage();
      const metrics = await context.newCDPSession(page);
      await metrics.send("Performance.enable");
      const start = Date.now();
      await page.goto("/", { waitUntil: "domcontentloaded" });
      const pageReadyMs = Date.now() - start;
      await expect(page.getByRole("link", { name: `Abrir pedido HTTP-LAB-${n}-0`, exact: true })).toBeVisible();
      const queueVisibleMs = Date.now() - start;
      const search = page.getByRole("searchbox", { name: "Buscar por código, cliente ou item (atalho: /)", exact: true });
      await search.fill(`HTTP-LAB-${n}-0`);
      const filledMs = Date.now() - start;
      // Inventory links keep their delivery context when the queue is filtered.
      await expect(page.locator('article a[aria-label^="Abrir pedido HTTP-LAB-"], tbody a[aria-label^="Abrir pedido HTTP-LAB-"]')).toHaveCount(1);
      const usableMs = Date.now() - start;
      const navigation = await page.evaluate(() => {
        const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
        return { ttfb_ms: nav.responseStart - nav.requestStart, dom_content_ms: nav.domContentLoadedEventEnd - nav.startTime,
          transfer_bytes: nav.transferSize, encoded_bytes: nav.encodedBodySize };
      });
      const measured = await metrics.send("Performance.getMetrics");
      const work = Object.fromEntries(measured.metrics.filter(({ name }) => ["ScriptDuration", "LayoutDuration", "RecalcStyleDuration", "TaskDuration"].includes(name)).map(({ name, value }) => [name, value]));
      samples.push({ sample, page_ready_ms: pageReadyMs, queue_visible_ms: queueVisibleMs, filled_ms: filledMs, usable_ms: usableMs, ...navigation, work });
      await page.close();
    }
  } finally { await context.close(); }
  const values = samples.map(sample => sample.usable_ms).sort((a, b) => a - b);
  writeFileSync(new URL(`browser-read-${n}.json`, root), JSON.stringify({ n, samples, first_page: samples[0], p50_ms: (values[9]! + values[10]!) / 2, p95_ms: values[18],
    scope: "Chromium desktop, localhost Nitro/Daphne/PostgreSQL/Redis; logged-in session; navigate + hydrate + type filter + observe one row; first sample cold context, later warm cache; login excluded and no field claim" }, null, 2));
});
