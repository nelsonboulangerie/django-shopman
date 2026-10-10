import { writeFileSync } from "node:fs";

import { expect, test, type Page, type Request } from "@playwright/test";

// Sonda AO VIVO do tempo até o total: do toque em "Pagamento" ao número
// confirmado pelo servidor. Mede cada requisição que a tela faz nesse intervalo
// (série ou paralelo), para dizer onde o tempo vai. Como rodar: README.md.
const ROUNDS = Number(process.env.PDV_LIVE_ROUNDS || "3");

type Hit = { method: string; path: string; start: number; end: number; status: number };

async function login(page: Page) {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  const user = page.getByPlaceholder("Usuário");
  if (await user.isVisible({ timeout: 8000 }).catch(() => false)) {
    const enter = page.getByRole("button", { name: "Entrar" });
    await expect(async () => {
      await user.fill(process.env.PDV_LIVE_USER || "");
      await page.getByPlaceholder("Senha").fill(process.env.PDV_LIVE_PASSWORD || "");
      await expect(enter).toBeEnabled({ timeout: 1000 });
    }).toPass({ timeout: 20_000 });
    await enter.click();
  }
  const station = page.getByRole("button", { name: /^É este balcão|^Vincular a este posto/ });
  const board = page.getByRole("button", { name: /Próxima livre/ });
  await station.or(board).first().waitFor({ timeout: 30_000 });
  await expect(async () => {
    if (await station.first().isVisible().catch(() => false)) await station.first().click({ timeout: 2000 });
    await board.waitFor({ timeout: 3000 });
  }).toPass({ timeout: 40_000 });
}

async function openFreshTab(page: Page) {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await expect(async () => {
    const back = page.getByRole("button", { name: "Voltar para comandas" });
    if (await back.isVisible().catch(() => false)) await back.click();
    await page.getByRole("button", { name: /Próxima livre/ }).click({ timeout: 3000 });
    await page.getByPlaceholder(/Buscar produto/).waitFor({ timeout: 3000 });
  }).toPass({ timeout: 30_000 });
}

async function addProducts(page: Page) {
  // Os N primeiros produtos disponíveis da grade (sem escolhas nem peso), um toque
  // cada, como o operador lançando a venda.
  const tiles = page.locator("button[data-pos-product]:enabled:not([data-pos-product-options])");
  await tiles.first().waitFor({ timeout: 15_000 });
  const want = Number(process.env.PDV_LIVE_LINES || "10");
  let added = 0;
  for (let i = 0; added < want && i < (await tiles.count()); i += 1) {
    await tiles.nth(i).click();
    added += 1;
    await page.waitForTimeout(Number(process.env.PDV_LIVE_TAP_MS || "250"));
  }
  return added;
}

test("tempo do toque em Pagamento até o total confirmado", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const page = await context.newPage();
  page.on("response", (response) => {
    if (response.status() >= 400) console.log(`  [${response.status()}] ${response.request().method()} ${response.url()}`);
  });
  await login(page);
  const report: Record<string, unknown>[] = [];
  for (let round = 0; round < ROUNDS; round += 1) {
    await openFreshTab(page);
    const added = await addProducts(page);
    // O operador termina de lançar e toca em Pagamento logo em seguida (o
    // autosave e a revisão da tela de venda ainda podem estar em voo).
    await page.waitForTimeout(Number(process.env.PDV_LIVE_PAUSE_MS || "300"));
    const hits: Hit[] = [];
    const starts = new Map<Request, number>();
    const t0 = Date.now();
    const onRequest = (request: Request) => starts.set(request, Date.now());
    const onFinished = async (request: Request) => {
      const url = new URL(request.url());
      if (!url.pathname.startsWith("/api/")) return;
      const response = await request.response().catch(() => null);
      hits.push({
        method: request.method(),
        path: url.pathname.replace("/api/v1/backstage/", ""),
        start: (starts.get(request) ?? t0) - t0,
        end: Date.now() - t0,
        status: response?.status() ?? 0,
      });
    };
    page.on("request", onRequest);
    page.on("requestfinished", onFinished);
    page.on("requestfailed", onFinished);
    await page.getByRole("button", { name: /^Pagamento/ }).first().click();
    // Pagamento aberto (o botão de validar existe) e nenhum "Calculando…" na tela.
    await expect(async () => {
      expect(await page.getByRole("button", { name: /^Validar|^Autorizar|^Tentar de novo/ }).count()).toBeGreaterThan(0);
      expect(await page.locator("[data-pos-total-calculating]").count()).toBe(0);
    }).toPass({ timeout: 120_000, intervals: [25] });
    const totalMs = Date.now() - t0;
    await page.waitForTimeout(1500);
    page.off("request", onRequest);
    page.off("requestfinished", onFinished);
    page.off("requestfailed", onFinished);
    hits.sort((a, b) => a.start - b.start);
    console.log(`rodada ${round + 1}: ${added} itens, total em ${totalMs} ms`);
    for (const hit of hits) {
      console.log(`  ${String(hit.start).padStart(6)} → ${String(hit.end).padStart(6)} ms  ${hit.method} ${hit.path} ${hit.status}`);
    }
    report.push({ round: round + 1, added, totalMs, hits });
    await page.keyboard.press("Escape");
  }
  if (process.env.PDV_LIVE_REPORT) writeFileSync(process.env.PDV_LIVE_REPORT, JSON.stringify(report, null, 2));
});
