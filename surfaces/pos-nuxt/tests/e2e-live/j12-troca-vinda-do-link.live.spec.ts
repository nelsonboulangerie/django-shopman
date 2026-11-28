// JORNADA J12 — a troca vinda do link do Gestor (EXCELENCIA-PDV, #2765).
//
// O "Trocar por <produto>" do diálogo "Resolver" da promessa em risco, no Gestor,
// abre o PDV em `/preorders/<ref>?swap=<sku em falta>`. O endereço leva só a
// intenção: as alternativas vêm do servidor, na hora.
//
// A Caixa (Fran) monta pela tela uma encomenda de 2 Baguette de Tradition para o
// próximo dia aberto (amanhã, ou a próxima data quando amanhã é dia fechado, #2976)
// e recebe em dinheiro. Depois abre a encomenda pelo link da troca, como o
// Gestor manda. O que a jornada prova, no celular (375 px) e no balcão (1280 px):
//   1. o foco vai para o bloco "Trocar 2x Baguette de Tradition";
//   2. uma alternativa por linha, na largura inteira, com o que o lote da data
//      cobre e a diferença de preço (o seed planeja Fendu e Tabatière para cada dia
//      aberto da semana);
//   3. o toque abre a conferência (Sai, Entra, totais, diferença, o que acontece
//      com o dinheiro); a encomenda paga que fica mais barata pede a Gerente, que
//      assina da lista com o próprio PIN;
//   4. trocado: o item novo está na encomenda, o bloco some e o endereço perde o
//      `swap` (recarregar não oferece de novo).
// Auditoria da prévia (contraste, letra, tela, alvo de toque, linhas alinhadas) no
// que esta tela pôs. Como rodar: README.md desta pasta.
import { audits, still } from "./support/audit";
import { capture, cast, expect, settled, test, type Page } from "./support/operator";
import { dayPhrase, picksNextOpenDay, type ChosenDay } from "./support/schedule";

const PRODUCT = process.env.PDV_LIVE_SWAP_PRODUCT || "Baguette de Tradition";
const PRODUCT_SKU = process.env.PDV_LIVE_SWAP_SKU || "TRADI";
const CUSTOMER = process.env.PDV_LIVE_SWAP_CUSTOMER || "Ana Ferreira";
const CUSTOMER_PHONE = process.env.PDV_LIVE_SWAP_PHONE || "43995555555";

function exact(text: string) {
  return new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
}

async function opensOrder(page: Page) {
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

async function identifiesCustomer(page: Page) {
  await page.getByRole("button", { name: "Identificar cliente" }).locator("visible=true").first().click();
  const search = page.getByRole("combobox", { name: "Buscar cliente" }).locator("visible=true").first();
  await search.click();
  await search.pressSequentially(CUSTOMER_PHONE);
  const dialog = page.getByRole("dialog").filter({ has: page.getByRole("combobox", { name: "Buscar cliente" }) });
  await dialog.getByRole("option", { name: exact(CUSTOMER) }).first().click({ timeout: 30_000 });
  // Escolher o cadastro pode fechar o diálogo sozinho; se não fechar, "Concluir".
  const done = dialog.getByRole("button", { name: "Concluir", exact: true });
  await expect(async () => {
    if (await done.isVisible().catch(() => false)) await done.click({ timeout: 2000 });
    await expect(dialog).toBeHidden({ timeout: 2000 });
  }).toPass({ timeout: 30_000 });
}

// A ordem do funil (WP-E13, #2754): depois do cliente vem "para quando", e só
// então o recebimento.
async function schedulesNextOpenDayPickup(page: Page): Promise<ChosenDay> {
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


/** Lança 2 do produto (dois toques no cartão da grade). */
async function ordersTwo(page: Page) {
  const search = page.getByPlaceholder(/Buscar produto/).locator("visible=true").first();
  await search.click();
  await search.pressSequentially(PRODUCT);
  const tile = page.locator("button[data-pos-product]").filter({ hasText: exact(PRODUCT) }).first();
  await tile.click({ timeout: 30_000 });
  const later = page.getByRole("button", { name: /^Mudar para/ }).locator("visible=true").first();
  if (await later.waitFor({ timeout: 5000 }).then(() => true, () => false)) await later.click();
  await tile.click({ timeout: 30_000 });
}

/** Recebe em dinheiro e fecha a encomenda; devolve o número dela (da resposta do fechamento). */
async function closesInCash(page: Page): Promise<string> {
  const sheet = page.getByRole("button", { name: "Ver a comanda" }).locator("visible=true").first();
  if (await sheet.isVisible().catch(() => false)) await sheet.click();
  await page.getByRole("button", { name: /^Pagamento|^Outras formas|^Cobrar/ }).locator("visible=true").first().click();
  await page.getByRole("button", { name: /^Dinheiro/ }).and(page.locator(":enabled")).locator("visible=true").first().click();
  const closed = page.waitForResponse((r) => r.url().includes("/pos/sale/close/") && r.request().method() === "POST", { timeout: 90_000 });
  await page.getByRole("button", { name: /^Validar/ }).and(page.locator(":enabled")).locator("visible=true").first().click({ timeout: 30_000 });
  const response = await closed;
  const ref = String((await response.json()).order_ref || "");
  expect(ref, "o fechamento devolve o número da encomenda").not.toBe("");
  return ref;
}

/** As linhas da troca: largura inteira do bloco, alvo de toque, nada para o lado. */
async function auditsSwapRows(page: Page, label: string) {
  const report = await page.evaluate(() => {
    const block = document.querySelector("[data-preorder-swap-item]")!;
    const style = getComputedStyle(block);
    const box = block.getBoundingClientRect();
    const inner = {
      left: Math.round(box.left + Number.parseFloat(style.paddingLeft) + Number.parseFloat(style.borderLeftWidth)),
      right: Math.round(box.right - Number.parseFloat(style.paddingRight) - Number.parseFloat(style.borderRightWidth)),
    };
    const rows = Array.from(block.querySelectorAll("[data-preorder-swap-option]")).map((row) => {
      const r = row.getBoundingClientRect();
      return { left: Math.round(r.left), right: Math.round(r.right), height: Math.round(r.height) };
    });
    return { inner, rows, overflowX: document.documentElement.scrollWidth - window.innerWidth, viewport: window.innerWidth };
  });
  console.log(`AUDITORIA geometria ${label}: ${JSON.stringify(report)}`);
  expect(report.rows.length, `${label}: nenhuma alternativa`).toBeGreaterThan(0);
  for (const row of report.rows) {
    expect(Math.abs(row.left - report.inner.left), `${label}: a linha começa na borda do bloco`).toBeLessThanOrEqual(1);
    expect(Math.abs(row.right - report.inner.right), `${label}: a linha termina na borda do bloco`).toBeLessThanOrEqual(1);
    expect(row.height, `${label}: altura da linha (alvo de toque)`).toBeGreaterThanOrEqual(44);
  }
  expect(report.overflowX, `${label}: transbordo horizontal`).toBeLessThanOrEqual(0);
}

/** Os botões da conferência: alvo de toque de 44 px. */
async function auditsTargets(page: Page, label: string, selector: string) {
  const heights = await page.locator(selector).evaluateAll((els) =>
    els.filter((el) => (el as HTMLElement).offsetParent !== null).map((el) => ({
      text: (el.textContent || "").trim().slice(0, 40), height: Math.round(el.getBoundingClientRect().height),
    })));
  console.log(`AUDITORIA alvos ${label}: ${JSON.stringify(heights)}`);
  expect(heights.length, `${label}: nenhum botão`).toBeGreaterThan(0);
  for (const target of heights) expect(target.height, `${label}: altura de "${target.text}"`).toBeGreaterThanOrEqual(44);
}

test.describe.configure({ mode: "serial" });

for (const device of ["phone", "counter"] as const) {
  test.describe(`J12 Troca vinda do link do Gestor · ${device === "phone" ? "375 px" : "1280 px"}`, () => {
    test.use({ device });

    test("a encomenda aberta com swap mostra as alternativas, e um toque troca pela edição", async ({ cashierAtCounter: page }, testInfo) => {
      test.setTimeout(8 * 60_000);
      if (device === "counter") await page.setViewportSize({ width: 1280, height: 800 });

      await opensOrder(page);
      await identifiesCustomer(page);
      const chosen = await schedulesNextOpenDayPickup(page);
      await ordersTwo(page);
      const ref = await closesInCash(page);

      // 1 · O link do Gestor: só a intenção no endereço.
      await page.goto(`/preorders/${encodeURIComponent(ref)}?swap=${PRODUCT_SKU}`);
      await settled(page);
      const block = page.locator(`[data-preorder-swap-item="${PRODUCT_SKU}"]`);
      await expect(block).toBeVisible({ timeout: 60_000 });
      await expect(block.locator("[data-preorder-swap-title]")).toHaveText(`Trocar 2x ${PRODUCT}`);
      // O próximo foco leva a página ao item a trocar.
      await expect(block).toBeFocused({ timeout: 15_000 });
      await expect(block).toBeInViewport();

      // 2 · Uma alternativa por linha, com o lote de amanhã e a diferença de preço.
      const rows = block.locator("[data-preorder-swap-option]");
      await expect(rows.first()).toBeVisible();
      await expect(rows.first()).toContainText(/Trocar por /);
      await expect(rows.first().locator("[data-preorder-swap-available]")).toContainText(new RegExp(`livres? para ${dayPhrase(chosen)}`, "iu"));
      await expect(rows.first().locator("[data-preorder-swap-difference]")).toContainText(/a mais|a menos|Mesmo total/);
      await still(page);
      await audits(page, "bloco da troca", "[data-preorder-swap-title], [data-preorder-swap-option] span span, [data-preorder-swap-difference]", { fontScale: true, crushed: true });
      await auditsSwapRows(page, "linhas da troca");
      await capture(page, testInfo, "alternativas-pelo-link");

      // 3 · O toque abre a conferência.
      const offerName = ((await rows.first().locator("span span").first().textContent()) || "").trim().replace(/^Trocar por /, "");
      await rows.first().click();
      const dialog = page.locator("[data-preorder-swap-dialog]");
      await expect(dialog).toBeVisible({ timeout: 30_000 });
      await expect(dialog.locator("[data-preorder-swap-out]")).toHaveText(`2x ${PRODUCT}`);
      await expect(dialog.locator("[data-preorder-swap-in]")).toHaveText(`2x ${offerName}`);
      await still(page);
      await audits(page, "conferência", "[data-preorder-swap-dialog] dt, [data-preorder-swap-dialog] dd, [data-preorder-swap-money], [data-preorder-swap-manager]", { fontScale: true, crushed: true });
      await auditsTargets(page, "conferência", "[data-preorder-swap-confirm], [role=dialog] button:has-text('Voltar')");
      await capture(page, testInfo, "conferencia-da-troca");
      await page.locator("[data-preorder-swap-confirm]").click();

      // A encomenda paga em dinheiro que fica mais barata: a Gerente assina da lista.
      // Mais cara ou igual, a troca entra direto e o "Trocado" é um aviso breve: espera
      // o que vier primeiro. Esperar o gerente antes de olhar o aviso deixava o aviso
      // sumir no meio da espera (a alternativa da segunda-feira é mais cara, #2976).
      const manager = page.getByRole("dialog", { name: "Autorizar a devolução" });
      const swapped = page.getByText(`Trocado: 2x ${offerName} no lugar de 2x ${PRODUCT}.`).first();
      const first = await Promise.race([
        manager.waitFor({ timeout: 60_000 }).then(() => "manager" as const),
        swapped.waitFor({ timeout: 60_000 }).then(() => "swapped" as const),
      ]).catch(() => "nothing" as const);
      expect(first, "nem o gerente nem o aviso da troca apareceram").not.toBe("nothing");
      if (first === "manager") {
        await still(page);
        await capture(page, testInfo, "gerente-autoriza-a-devolucao");
        await manager.getByRole("button", { name: new RegExp(cast.manager.name) }).first().click();
        for (const digit of cast.manager.pin) await manager.getByRole("button", { name: digit, exact: true }).click();
        const confirm = manager.getByRole("button", { name: /^Confirmar|^Autorizar/ }).first();
        if (await confirm.isVisible({ timeout: 2000 }).catch(() => false)) await confirm.click();
        // 4 · Trocado: o item novo na encomenda, o bloco some, o endereço perde o swap.
        await expect(swapped).toBeVisible({ timeout: 60_000 });
      }
      await expect(block).toBeHidden({ timeout: 30_000 });
      await expect(page).not.toHaveURL(/swap=/);
      await expect(page.locator("[data-order-items]").locator("visible=true").first()).toContainText(offerName);
      await still(page);
      await capture(page, testInfo, "depois-da-troca");
    });
  });
}
