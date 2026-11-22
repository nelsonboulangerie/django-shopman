// JORNADA J6 — receber e entregar (EXCELENCIA-PDV WP-E5: P1-3, P1-6, P2-14).
//
// Gesto de dinheiro tem UMA tela (dono, 16/11/2026). A Caixa (Fran) monta pela tela
// uma encomenda de hoje, a pagar na retirada, e a encontra na lista das Encomendas
// quando a cliente chega. "Receber R$ X e entregar" abre a MESMA tela de Pagamento
// da venda, com o saldo como total. O que a jornada prova, no celular (375 px) e no
// balcão (1366 px):
//   1. o Pagamento abre com o saldo no lugar do total, as formas do saldo
//      (dinheiro, débito, crédito e Pix, #2897) e a encomenda na coluna do pedido;
//   2. a Tela do cliente (outra janela do mesmo navegador) mostra o valor a pagar;
//   3. R$ 9.000,00 recebidos pedem a MESMA conferência da venda (troco alto, #2212);
//   4. uma nota de R$ 100,00 vira o troco grande, e Receber e entregar conclui: a
//      encomenda sai entregue, o PDV volta à lista e a Tela do cliente às boas-vindas.
// E P1-6: uma encomenda paga em dinheiro, cancelada pela tela, mostra o valor que
// volta ao cliente a quem cancela e à Gerente (Joyce), que assina com o próprio PIN.
// Auditoria da prévia (contraste, letra, tela, encoberto) no que esta tela pôs.
// Como rodar: README.md desta pasta.
import type { Page } from "@playwright/test";

import { audits, still } from "./support/audit";
import { capture, cast, expect, settled, stack, test } from "./support/operator";

const PRODUCT = process.env.PDV_LIVE_J6_PRODUCT || "Baguette de Tradition";
const CUSTOMER = process.env.PDV_LIVE_J6_CUSTOMER || "Ana Ferreira";
const CUSTOMER_PHONE = process.env.PDV_LIVE_J6_PHONE || "43995555555";

function exact(text: string) {
  return new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
}
const money = (text: string) => (text.match(/R\$\s?[\d.]+,\d{2}/)?.[0] ?? "").replace(/\s/, " ");
const cents = (display: string) => Number(display.replace(/[^\d]/g, ""));
const brl = (q: number) => `R$ ${Math.floor(q / 100).toLocaleString("pt-BR")},${String(q % 100).padStart(2, "0")}`;

async function opensOrder(page: Page) {
  await page.getByRole("link", { name: /^Encomendas/ }).locator("visible=true").first().click();
  await settled(page);
  await page.getByRole("button", { name: /^Nova( encomenda)?$/ }).locator("visible=true").first().click({ timeout: 30_000 });
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
  const done = dialog.getByRole("button", { name: "Concluir", exact: true });
  await expect(async () => {
    if (await done.isVisible().catch(() => false)) await done.click({ timeout: 2000 });
    await expect(dialog).toBeHidden({ timeout: 2000 });
  }).toPass({ timeout: 30_000 });
}

/**
 * Para hoje, retirada no balcão: o primeiro horário que ainda cabe, ou "O quanto
 * antes" quando o dia já não tem outro horário combinável (fim de tarde).
 */
async function schedulesTodayPickup(page: Page, day: RegExp = /^Hoje/) {
  await page.getByRole("radio", { name: day }).locator("visible=true").first().click();
  const slot = page
    .locator('[data-order-step="schedule"]')
    .getByRole("button")
    .filter({ hasText: /\d{1,2}h|\d{2}:\d{2}|^O quanto antes/ })
    .and(page.locator(":enabled"))
    .first();
  await slot.click({ timeout: 30_000 });
  await page.getByRole("button", { name: "Continuar", exact: true }).click();
  await page.locator("[data-order-fulfillment-options]").getByRole("radio", { name: /^Retirada/ }).click();
  await page.getByRole("button", { name: /Montar encomenda/ }).click();
  await expect(page.getByPlaceholder(/Buscar produto/).locator("visible=true").first()).toBeVisible({ timeout: 30_000 });
}

/** Lança `qty` do produto (um toque por unidade). */
async function orders(page: Page, qty: number) {
  const search = page.getByPlaceholder(/Buscar produto/).locator("visible=true").first();
  await search.click();
  await search.pressSequentially(PRODUCT);
  const tile = page.locator("button[data-pos-product]").filter({ hasText: exact(PRODUCT) }).first();
  for (let i = 0; i < qty; i += 1) {
    await tile.click({ timeout: 30_000 });
    const later = page.getByRole("button", { name: /^Mudar para/ }).locator("visible=true").first();
    if (await later.waitFor({ timeout: 3000 }).then(() => true, () => false)) await later.click();
  }
}

/**
 * Fecha a encomenda: `pickup` deixa o saldo para a retirada ("Na retirada" e
 * dinheiro previsto); senão recebe em dinheiro agora. Devolve o número do pedido.
 */
async function closesOrder(page: Page, pickup: boolean): Promise<string> {
  const sheet = page.getByRole("button", { name: "Ver a comanda" }).locator("visible=true").first();
  if (await sheet.isVisible().catch(() => false)) await sheet.click();
  await page.getByRole("button", { name: /^Pagamento|^Outras formas|^Cobrar/ }).locator("visible=true").first().click();
  if (pickup) await page.getByRole("button", { name: "Na retirada", exact: true }).locator("visible=true").first().click({ timeout: 30_000 });
  await page.getByRole("button", { name: /^Dinheiro/ }).and(page.locator(":enabled")).locator("visible=true").first().click();
  const closed = page.waitForResponse((r) => r.url().includes("/pos/sale/close/") && r.request().method() === "POST", { timeout: 90_000 });
  await page.getByRole("button", { name: /^Validar/ }).and(page.locator(":enabled")).locator("visible=true").first().click({ timeout: 30_000 });
  const response = await closed;
  const ref = String((await response.json()).order_ref || "");
  expect(ref, "o fechamento devolve o número da encomenda").not.toBe("");
  // A tela do resultado: segue para o quadro ("Nova encomenda" abriria outra comanda).
  const next = page.getByRole("button", { name: /^Nova venda/ }).locator("visible=true").first();
  if (await next.waitFor({ timeout: 30_000 }).then(() => true, () => false)) await next.click();
  return ref;
}

/** A cliente chegou: Encomendas, a encomenda na lista de hoje, o detalhe. */
async function opensFromList(page: Page, ref: string) {
  await page.getByRole("link", { name: /^Encomendas/ }).locator("visible=true").first().click();
  await settled(page);
  const row = page.locator(`[data-preorder="${ref}"]`).locator("visible=true").first();
  await row.click({ timeout: 60_000 });
  await expect(page.getByRole("heading", { name: `Encomenda ${ref}` }).locator("visible=true").first()).toBeVisible({ timeout: 60_000 });
  await settled(page);
}

/** Nada passa da borda: a página não rola para o lado. */
async function noSideScroll(page: Page, label: string) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  console.log(`AUDITORIA transbordo ${label}: ${overflow}`);
  expect(overflow, `${label}: transbordo horizontal`).toBeLessThanOrEqual(0);
}

/**
 * O foco de teclado à vista: o elemento focado existe, está na tela e, quando o
 * foco chegou pelo teclado (`:focus-visible`), desenha o anel.
 */
async function focusVisible(page: Page, label: string, { ring = true } = {}) {
  const focus = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) return null;
    const box = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return {
      text: (el.getAttribute("aria-label") || el.textContent || "").trim().slice(0, 60),
      inView: box.top >= 0 && box.bottom <= window.innerHeight && box.left >= 0 && box.right <= window.innerWidth,
      focusVisible: el.matches(":focus-visible"),
      ring: (style.outlineStyle !== "none" && Number.parseFloat(style.outlineWidth) > 0) || style.boxShadow !== "none",
    };
  });
  console.log(`AUDITORIA foco ${label}: ${JSON.stringify(focus)}`);
  expect(focus, `${label}: nenhum elemento com foco`).not.toBeNull();
  expect(focus!.inView, `${label}: o foco está fora da tela`).toBe(true);
  if (ring) expect(focus!.ring, `${label}: o foco de teclado não desenha anel`).toBe(true);
}

const PAYMENT_TEXT = [
  "[data-pos-total] p",
  "[data-preorder-balance-payment] [data-payment-method]",
  "[data-balance-summary] h3 span",
  "[data-balance-customer]",
  "[data-balance-totals] dt",
  "[data-balance-totals] dd",
  "[data-balance-adjustment] dt",
].join(", ");

test.describe.configure({ mode: "serial" });

for (const device of ["phone", "counter"] as const) {
  test.describe(`J6 Receber e entregar · ${device === "phone" ? "375 px" : "1366 px"}`, () => {
    test.use({ device });

    test("o saldo se recebe na tela de Pagamento da venda, com troco, conferência e Tela do cliente", async (
      { cashierAtCounter: page },
      testInfo,
    ) => {
      test.setTimeout(10 * 60_000);

      // 0 · A encomenda nasce pela tela: hoje, retirada, a pagar na retirada.
      await opensOrder(page);
      await identifiesCustomer(page);
      await schedulesTodayPickup(page);
      await orders(page, 2);
      const ref = await closesOrder(page, true);

      // A Tela do cliente: a segunda janela do mesmo navegador, como no balcão.
      const display = await page.context().newPage();
      await display.goto("/display");
      await settled(display);

      // 1 · A cliente chegou: a encomenda pela lista, e o gesto principal com o valor.
      await opensFromList(page, ref);
      const handOver = page.locator("[data-preorder-hand-over], [data-preorder-hand-over-bar] button").locator("visible=true").first();
      await expect(handOver).toContainText(/^Receber R\$ [\d.,]+ e entregar$/, { timeout: 30_000 });
      const due = money((await handOver.textContent()) || "");
      const dueQ = cents(due);
      expect(dueQ, "o saldo da encomenda").toBeGreaterThan(0);
      expect(dueQ, "o roteiro dá o troco com uma nota de R$ 100").toBeLessThan(10000);
      await still(page);
      await capture(page, testInfo, "detalhe-com-saldo");

      // 2 · O Pagamento da venda, com o saldo como total.
      await handOver.click();
      const payment = page.locator("[data-preorder-balance-payment]");
      await expect(payment).toBeVisible({ timeout: 30_000 });
      const hero = page.locator("[data-pos-total]");
      await expect(hero).toContainText("A receber");
      await expect(hero).toContainText(due);
      const methods = await payment.locator("[data-payment-method]").evaluateAll((els) => els.map((el) => el.getAttribute("data-payment-method")));
      expect(methods.sort()).toEqual(["cash", "credit", "debit", "pix"]);
      await expect(page.locator("[data-balance-summary]")).toContainText(`Encomenda ${ref}`);
      // A coluna da encomenda fecha a conta: itens, desconto (quando há) e o total.
      await expect(page.locator("[data-balance-totals]")).toContainText("Total da encomenda");
      await expect(page.locator("[data-payment-cta]")).toBeDisabled();
      // O próximo foco ao abrir: a primeira forma (Enter lança ela), à vista.
      await expect(payment.locator('[data-payment-method="cash"]')).toBeFocused({ timeout: 15_000 });
      await focusVisible(page, "primeira forma", { ring: false });
      // A Tela do cliente acompanha: o valor a pagar.
      await expect(display.getByText("Total a pagar")).toBeVisible({ timeout: 15_000 });
      await expect(display.getByText(due).first()).toBeVisible();
      await still(page);
      await capture(page, testInfo, "pagamento-com-o-saldo");
      await audits(page, "pagamento do saldo", PAYMENT_TEXT, { scroll: true });
      await noSideScroll(page, "pagamento do saldo");
      await display.screenshot({ path: testInfo.outputPath("tela-do-cliente-recebendo.png") });

      // 3 · R$ 9.000,00 recebidos: a mesma conferência da venda.
      await payment.locator('[data-payment-method="cash"]').click();
      await page.locator('button[aria-label="Limpar: zera o valor da linha"]').click();
      for (const digit of "9000") await page.locator(`button[aria-label="Dígito ${digit}"]`).locator("visible=true").first().click();
      const bigChange = brl(900000 - dueQ);
      await expect(hero).toContainText(bigChange);
      await expect(page.getByText(`Troco de ${bigChange}.`).first()).toBeVisible();
      await expect(page.getByRole("button", { name: "O troco está certo" })).toBeVisible();
      await expect(page.locator("[data-payment-cta]")).toBeDisabled();
      // No celular o aviso que trava mora acima do teclado: a captura mostra o aviso.
      await page.getByRole("button", { name: "O troco está certo" }).scrollIntoViewIfNeeded();
      await still(page);
      await capture(page, testInfo, "troco-alto-pede-conferencia");
      await audits(page, "troco alto", "[data-pos-total] p", { scroll: true });

      // 4 · A nota certa: R$ 100,00. O troco é o número grande.
      await page.locator('button[aria-label="Limpar: zera o valor da linha"]').click();
      await page.getByRole("button", { name: /^Recebi nota de R\$\s100,00$/ }).locator("visible=true").first().click();
      const change = brl(10000 - dueQ);
      await expect(hero).toContainText("Troco");
      await expect(hero).toContainText(change);
      const cta = page.locator("[data-payment-cta]");
      await expect(cta).toBeEnabled();
      await hero.scrollIntoViewIfNeeded();
      await still(page);
      await capture(page, testInfo, "troco-grande");
      // O próximo gesto é receber: pelo teclado (Tab) o foco chega ao botão, à vista e com anel.
      await cta.focus();
      await page.keyboard.press("Shift+Tab");
      await page.keyboard.press("Tab");
      await expect(cta).toBeFocused();
      await focusVisible(page, "Receber e entregar");
      await audits(page, "troco", "[data-pos-total] p, [data-payment-cta]", { scroll: true });

      // 5 · Receber e entregar: entregue, o PDV volta à lista e a parede às boas-vindas.
      const handedOver = page.waitForResponse((r) => r.url().includes(`/pos/preorders/${ref}/hand-over/`) && r.request().method() === "POST", { timeout: 90_000 });
      await cta.click();
      const response = await handedOver;
      expect(response.status()).toBe(200);
      const sent = response.request().postDataJSON() as { tenders: Array<{ method: string; amount_q: number }>; cash_tendered_q: number };
      expect(sent.tenders).toEqual([{ method: "cash", amount_q: dueQ }]);
      expect(sent.cash_tendered_q).toBe(10000);
      await expect(page.getByText(`Recebido ${due}, com troco de ${change}. Encomenda entregue.`).first()).toBeVisible({ timeout: 30_000 });
      await expect(payment).toBeHidden({ timeout: 30_000 });
      await expect(page).toHaveURL(/\/preorders(\?|$)/, { timeout: 30_000 });
      await expect(display.getByText("Que bom ter você aqui.")).toBeVisible({ timeout: 15_000 });
      await still(page);
      await capture(page, testInfo, "entregue-volta-a-lista");
      await display.close();
    });

    test("P1-6: cancelar a encomenda paga mostra o valor que volta, e a Gerente assina vendo", async (
      { cashierAtCounter: page },
      testInfo,
    ) => {
      test.setTimeout(10 * 60_000);

      await opensOrder(page);
      await identifiesCustomer(page);
      await schedulesTodayPickup(page);
      await orders(page, 1);
      const ref = await closesOrder(page, false);

      await opensFromList(page, ref);
      if ((page.viewportSize()?.width ?? 0) >= 768) {
        await page.locator("[data-preorder-cancel]").locator("visible=true").first().click({ timeout: 30_000 });
      } else {
        // No celular, os gestos de uso médio moram no ⋮ da linha do chão.
        await page.getByRole("button", { name: /Mais ações|Opções/ }).locator("visible=true").first().click();
        await page.getByRole("menuitem", { name: "Cancelar encomenda" }).first().click();
      }
      const reasons = page.getByRole("dialog", { name: /^Cancelar a encomenda de/ });
      await expect(reasons).toBeVisible({ timeout: 30_000 });
      await expect(reasons).toContainText(/R\$ [\d.,]+ em dinheiro ficam a devolver no caixa\./);
      const refund = money((await reasons.textContent()) || "");
      await still(page);
      await capture(page, testInfo, "cancelar-mostra-o-valor");
      await reasons.locator('[data-reason-keyed] [role="radio"]').first().click();
      await reasons.locator("[data-reason-confirm]").click();

      const manager = page.getByRole("dialog", { name: "Autorizar cancelamento" });
      await expect(manager).toBeVisible({ timeout: 30_000 });
      await expect(manager).toContainText(`${refund} em dinheiro ficam a devolver no caixa.`);
      await still(page);
      await capture(page, testInfo, "gerente-ve-o-valor");
      await manager.getByRole("button", { name: new RegExp(cast.manager.name) }).first().click();
      for (const digit of cast.manager.pin) await manager.getByRole("button", { name: digit, exact: true }).click();
      const confirm = manager.getByRole("button", { name: /^Confirmar|^Autorizar/ }).first();
      if (await confirm.isVisible({ timeout: 2000 }).catch(() => false)) await confirm.click();
      await expect(page.getByText("Encomenda cancelada.").first()).toBeVisible({ timeout: 60_000 });
      await capture(page, testInfo, "cancelada");
    });
  });
}

// ── O SALDO EM PIX (#2897) ──────────────────────────────────────────────────
//
// O Pix entra pela MESMA tela: escolhido sozinho, "Receber e entregar" gera a
// cobrança Pix do pedido e mostra o QR da venda, na tela e na Tela do cliente; a
// espera é a da venda. Pagamento só no simulador local (`payment_mock`), nunca a
// Efí. Duas rodadas, porque o simulador confirma (ou não) por configuração da pilha:
//   PDV_LIVE_J6_PIX=pago    com SHOPMAN_MOCK_PIX_AUTO_CONFIRM=1: o banco confirma
//                           sozinho em segundos, e a encomenda é entregue;
//   PDV_LIVE_J6_PIX=nao-chega sem confirmação e com o Pix do canal `pdv` em 1 minuto
//                           (ajuste declarado do banco local): o Pix vence, o aviso
//                           traz "Gerar outro Pix" (o QR morto sai), e o operador recebe em dinheiro,
//                           o que cancela o Pix antes.
const PIX_ROUND = process.env.PDV_LIVE_J6_PIX || "";
/** `antes`: só a captura da tela decisiva, no código de antes (#2916/#2917). */
const SIDE = process.env.PDV_LIVE_J6_SIDE || "depois";

/**
 * O teste da rodada pedida roda; o das outras rodadas é declarado pulado, sem abrir o
 * PDV. O pulo dentro do corpo vinha depois da fixture `cashierAtCounter`: cada teste
 * que só ia pular entrava com a Gerente e destravava com o PIN da Fran, e no sexto em
 * sequência o freio de 5 identificações por minuto (`OperatorUnlockView`) barrava o
 * PIN ("Muitas tentativas de identificação") e a jornada seguinte caía (#3295).
 */
const inRound = (...rounds: string[]) => (rounds.includes(PIX_ROUND) ? test : test.skip);

async function choosesPixAndReceives(page: Page) {
  const payment = page.locator("[data-preorder-balance-payment]");
  await payment.locator('[data-payment-method="pix"]').click();
  const cta = page.locator("[data-payment-cta]");
  await expect(cta).toBeEnabled();
  const pixRequest = page.waitForResponse((r) => /\/pos\/preorders\/[^/]+\/pix\/$/.test(new URL(r.url()).pathname) && r.request().method() === "POST", { timeout: 60_000 });
  await cta.click();
  const response = await pixRequest;
  expect(response.status()).toBe(200);
  return (await response.json()) as { payment: { intent_ref: string; amount_display: string } };
}

for (const device of ["phone", "counter"] as const) {
  test.describe(`J6 Pix no saldo · ${device === "phone" ? "375 px" : "1366 px"}`, () => {
    test.use({ device });

    inRound("pago")("o saldo em Pix: o QR da venda, na tela e na Tela do cliente, e a entrega quando o banco confirma", async (
      { cashierAtCounter: page },
      testInfo,
    ) => {
      test.setTimeout(10 * 60_000);

      await opensOrder(page);
      await identifiesCustomer(page);
      await schedulesTodayPickup(page);
      await orders(page, 2);
      const ref = await closesOrder(page, true);
      const display = await page.context().newPage();
      await display.goto("/display");
      await settled(display);

      await opensFromList(page, ref);
      const handOver = page.locator("[data-preorder-hand-over], [data-preorder-hand-over-bar] button").locator("visible=true").first();
      await handOver.click();
      await expect(page.locator("[data-preorder-balance-payment]")).toBeVisible({ timeout: 30_000 });
      await page.locator('[data-preorder-balance-payment] [data-payment-method="pix"]').click();
      await still(page);
      await capture(page, testInfo, "pix-escolhido");
      await page.locator("[data-preorder-balance-payment]").locator('button[aria-label^="Remover Pix"]').click();

      const { payment } = await choosesPixAndReceives(page);
      const pix = page.locator("[data-balance-pix]");
      await expect(pix).toBeVisible({ timeout: 30_000 });
      await expect(pix.locator('img[alt="QR Code Pix"]')).toBeVisible();
      await expect(pix).toContainText("A confirmação chega aqui sozinha.");
      // A Tela do cliente: o MESMO QR da venda em Pix.
      await expect(display.locator('img[alt="QR Code Pix"], img[alt*="QR"]').first()).toBeVisible({ timeout: 15_000 });
      await still(page);
      await capture(page, testInfo, "pix-qr-na-tela");
      await audits(page, "pix na tela", "[data-balance-pix] header p, [data-balance-pix] p.text-sm, [data-balance-pix] button", { scroll: true });
      await noSideScroll(page, "pix na tela");
      await display.screenshot({ path: testInfo.outputPath("tela-do-cliente-pix.png") });
      if (stack.shots) await display.screenshot({ path: `${stack.shots}/${device}-tela-do-cliente-pix.png` });

      // O banco confirma (simulador, em segundos): a encomenda é entregue sozinha.
      await expect(page.getByText(`Pix de ${payment.amount_display} confirmado. Encomenda entregue.`).first()).toBeVisible({ timeout: 120_000 });
      await expect(page).toHaveURL(/\/preorders(\?|$)/, { timeout: 30_000 });
      await expect(display.getByText("Que bom ter você aqui.")).toBeVisible({ timeout: 15_000 });
      await still(page);
      await capture(page, testInfo, "pix-confirmado-entregue");
      await display.close();
    });

    inRound("nao-chega")("o Pix que não chega: o aviso traz Gerar outro Pix, e receber em dinheiro cancela o Pix antes", async (
      { cashierAtCounter: page },
      testInfo,
    ) => {
      test.setTimeout(12 * 60_000);

      await opensOrder(page);
      await identifiesCustomer(page);
      await schedulesTodayPickup(page);
      await orders(page, 2);
      const ref = await closesOrder(page, true);
      await opensFromList(page, ref);
      const handOver = page.locator("[data-preorder-hand-over], [data-preorder-hand-over-bar] button").locator("visible=true").first();
      await expect(handOver).toContainText(/^Receber R\$ [\d.,]+ e entregar$/, { timeout: 30_000 });
      const dueQ = cents(money((await handOver.textContent()) || ""));
      await handOver.click();
      await expect(page.locator("[data-preorder-balance-payment]")).toBeVisible({ timeout: 30_000 });
      const { payment } = await choosesPixAndReceives(page);
      await expect(page.locator("[data-balance-pix]")).toBeVisible({ timeout: 30_000 });

      // O Pix vence (1 minuto no canal de teste, mais a folga da espera da venda).
      const alert = page.getByText("O Pix não foi confirmado.").first();
      await expect(alert).toBeVisible({ timeout: 4 * 60_000 });
      await expect(page.getByRole("button", { name: "Gerar outro Pix" })).toHaveCount(1);
      // O Pix vencido não é pagável: sem QR e sem código para copiar; o cartão só diz o fato.
      await expect(page.locator('[data-balance-pix] img[alt^="QR Code"]')).toHaveCount(0);
      await expect(page.locator("[data-balance-pix]").getByText("Copiar código Pix")).toHaveCount(0);
      await expect(page.getByText(/não foi confirmado/)).toHaveCount(1);
      await expect(page.locator("[data-balance-pix-leave]")).toBeVisible();
      await still(page);
      await capture(page, testInfo, "pix-nao-confirmado");
      await audits(page, "aviso do Pix", "[data-balance-pix] header p, [data-balance-pix] button, [data-payment-proof-expired-note]", { scroll: true });

      // O operador recebe em dinheiro: a rota da entrega cancela o Pix antes.
      await page.locator("[data-balance-pix-leave]").click();
      await expect(page.locator("[data-payment-cta]")).toBeVisible({ timeout: 15_000 });
      await page.locator('[data-preorder-balance-payment] [data-payment-method="cash"]').click();
      await page.getByRole("button", { name: /^Recebi nota de R\$\s100,00$/ }).locator("visible=true").first().click();
      await expect(page.locator("[data-pos-total]")).toContainText(brl(10000 - dueQ));
      await still(page);
      await capture(page, testInfo, "recebe-em-dinheiro-depois-do-pix");
      const handedOver = page.waitForResponse((r) => r.url().includes(`/pos/preorders/${ref}/hand-over/`) && r.request().method() === "POST", { timeout: 90_000 });
      await page.locator("[data-payment-cta]").click();
      expect((await handedOver).status()).toBe(200);
      await expect(page.getByText(/Encomenda entregue\./).first()).toBeVisible({ timeout: 30_000 });
      // O Pix vencido ficou cancelado no servidor: o status do pedido diz que ele morreu.
      const status = await page.evaluate(async (orderRef) => {
        const response = await fetch(`/api/v1/backstage/pos/payment/${orderRef}/status/`, { credentials: "include" });
        return response.ok ? await response.json() : null;
      }, ref);
      console.log(`J6 Pix que não chega: intent ${payment.intent_ref}, status depois do dinheiro ${JSON.stringify(status)}`);
      await still(page);
      await capture(page, testInfo, "entregue-em-dinheiro");
    });

    inRound("pago", "misto")("Pix misto (#2916): parte em dinheiro, parte em Pix, o Recebi o Pix confere e a entrega sai", async (
      { cashierAtCounter: page },
      testInfo,
    ) => {
      test.setTimeout(10 * 60_000);

      await opensOrder(page);
      await identifiesCustomer(page);
      await schedulesTodayPickup(page);
      await orders(page, 2);
      const ref = await closesOrder(page, true);
      await opensFromList(page, ref);
      const handOver = page.locator("[data-preorder-hand-over], [data-preorder-hand-over-bar] button").locator("visible=true").first();
      await expect(handOver).toContainText(/^Receber R\$ [\d.,]+ e entregar$/, { timeout: 30_000 });
      const dueQ = cents(money((await handOver.textContent()) || ""));
      expect(dueQ, "o roteiro paga R$ 10,00 em dinheiro e o resto em Pix").toBeGreaterThan(1000);
      await handOver.click();
      const payment = page.locator("[data-preorder-balance-payment]");
      await expect(payment).toBeVisible({ timeout: 30_000 });

      // R$ 10,00 em dinheiro, e o Pix completa o saldo: a mesma tela, sem trava.
      await payment.locator('[data-payment-method="cash"]').click();
      await page.locator('button[aria-label="Limpar: zera o valor da linha"]').click();
      for (const digit of "10") await page.locator(`button[aria-label="Dígito ${digit}"]`).locator("visible=true").first().click();
      await payment.locator('[data-payment-method="pix"]').click();
      await still(page);
      await capture(page, testInfo, "misto-dinheiro-e-pix");
      if (SIDE === "antes") return;
      await expect(payment).not.toContainText("o Pix cobra o valor inteiro");
      const cta = page.locator("[data-payment-cta]");
      await expect(cta).toBeEnabled();

      // O degrau da venda mista: confira o Pix e toque em Recebi o Pix.
      await cta.click();
      const charged = page.locator("[data-pos-machine-charged]");
      await expect(charged).toContainText("Recebi o Pix", { timeout: 15_000 });
      await still(page);
      await capture(page, testInfo, "misto-confere-o-pix");
      await audits(page, "conferência do Pix misto", "[role=dialog] h2, [role=dialog] p, [data-pos-machine-charged]");
      const handedOver = page.waitForResponse((r) => r.url().includes(`/pos/preorders/${ref}/hand-over/`) && r.request().method() === "POST", { timeout: 90_000 });
      await charged.click();
      const response = await handedOver;
      expect(response.status()).toBe(200);
      const sent = response.request().postDataJSON() as { tenders: Array<{ method: string; amount_q: number; pix_confirmed?: boolean }> };
      expect(sent.tenders).toEqual([
        { method: "cash", amount_q: 1000 },
        { method: "pix", amount_q: dueQ - 1000, pix_confirmed: true },
      ]);
      await expect(page.getByText(/Encomenda entregue\./).first()).toBeVisible({ timeout: 30_000 });
      await expect(page).toHaveURL(/\/preorders(\?|$)/, { timeout: 30_000 });
      await still(page);
      await capture(page, testInfo, "misto-entregue");
    });

    inRound("pago")("saldo parcial (#2917): a encomenda paga e aumentada cobra em Pix só o que falta", async (
      { cashierAtCounter: page },
      testInfo,
    ) => {
      test.setTimeout(12 * 60_000);

      // A encomenda nasce paga em dinheiro, e a cliente pede mais um depois.
      await opensOrder(page);
      await identifiesCustomer(page);
      await schedulesTodayPickup(page);
      await orders(page, 1);
      const ref = await closesOrder(page, false);
      await opensFromList(page, ref);
      if ((page.viewportSize()?.width ?? 0) >= 768) {
        await page.locator("[data-preorder-edit]").locator("visible=true").first().click({ timeout: 30_000 });
      } else {
        await page.getByRole("button", { name: /Mais ações|Opções/ }).locator("visible=true").first().click();
        await page.getByRole("menuitem", { name: "Editar encomenda" }).first().click();
      }
      await orders(page, 1);
      const sheet = page.getByRole("button", { name: "Ver a comanda" }).locator("visible=true").first();
      if (await sheet.isVisible().catch(() => false)) await sheet.click();
      await page.getByRole("button", { name: /^Salvar alterações/ }).locator("visible=true").first().click({ timeout: 30_000 });
      const review = page.locator("[data-order-edit-review]");
      await expect(review).toBeVisible({ timeout: 30_000 });
      const saved = page.waitForResponse((r) => r.url().includes(ref) && r.request().method() === "POST" && r.status() < 500, { timeout: 90_000 });
      await review.locator("[data-order-edit-confirm]").click();
      await saved;
      await expect(page.getByRole("heading", { name: `Encomenda ${ref}` }).locator("visible=true").first()).toBeVisible({ timeout: 60_000 });
      await settled(page);
      // O aviso de "atualizada" já disse o que tinha a dizer: ele sai sozinho (7 s) e não
      // cobre a tela seguinte. O mouse sai de cima dele, que pausaria a contagem.
      const updated = page.getByText(/atualizada\. O cliente foi avisado\./);
      await expect(updated.first()).toBeVisible({ timeout: 15_000 });
      await page.mouse.move(0, (page.viewportSize()?.height ?? 600) - 1);
      await expect(updated).toHaveCount(0, { timeout: 30_000 });

      // O saldo é só o item novo; o Pix cobra ele, e o que já entrou fica.
      const handOver = page.locator("[data-preorder-hand-over], [data-preorder-hand-over-bar] button").locator("visible=true").first();
      await expect(handOver).toContainText(/^Receber R\$ [\d.,]+ e entregar$/, { timeout: 30_000 });
      const due = money((await handOver.textContent()) || "");
      await handOver.click();
      await expect(page.locator("[data-preorder-balance-payment]")).toBeVisible({ timeout: 30_000 });
      await expect(page.locator("[data-balance-totals]")).toContainText("Já pago");
      await still(page);
      await capture(page, testInfo, "parcial-saldo-com-o-ja-pago");
      if (SIDE === "antes") return;
      await expect(page.locator('[data-preorder-balance-payment] [data-payment-method="pix"]')).toBeEnabled();
      const { payment } = await choosesPixAndReceives(page);
      expect(payment.amount_display.replace(/\s/, " ")).toBe(due);
      const pix = page.locator("[data-balance-pix]");
      await expect(pix.locator('img[alt="QR Code Pix"]')).toBeVisible({ timeout: 30_000 });
      await expect(pix).toContainText(`Pagamento Pix · ${due}`);
      await still(page);
      await capture(page, testInfo, "parcial-pix-so-do-saldo");
      await audits(page, "Pix do saldo parcial", "[data-balance-pix] header p, [data-balance-pix] p.text-sm, [data-balance-pix] button");
      await noSideScroll(page, "Pix do saldo parcial");

      await expect(page.getByText(`Pix de ${payment.amount_display} confirmado. Encomenda entregue.`).first()).toBeVisible({ timeout: 120_000 });
      await expect(page).toHaveURL(/\/preorders(\?|$)/, { timeout: 30_000 });
      await still(page);
      await capture(page, testInfo, "parcial-pix-confirmado-entregue");
    });
  });
}
