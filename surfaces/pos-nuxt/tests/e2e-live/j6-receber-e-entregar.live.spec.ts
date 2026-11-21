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

async function still(page: Page) {
  await page.waitForFunction(() =>
    document.getAnimations().every(
      (animation) => animation.playState !== "running" || animation.effect?.getTiming().iterations === Infinity,
    ),
  );
}

/**
 * A AUDITORIA da prévia (regra da casa, 16/11): contraste do texto contra o fundo
 * efetivo, tamanho da letra, caixa dentro da tela, sem texto cortado e sem outra
 * camada por cima. Mesma régua da J5, J7 e J12.
 */
async function audits(page: Page, label: string, selector: string) {
  const { rows, unparsed } = await page.evaluate((sel) => {
    const unparsed: string[] = [];
    const parse = (value: string) => {
      const srgb = value.match(/color\(srgb ([^)]+)\)/);
      if (srgb) {
        const [r, g, b, a = "1"] = srgb[1]!.split(/[\s/]+/).filter(Boolean);
        return [Number(r) * 255, Number(g) * 255, Number(b) * 255, Number(a)];
      }
      const ok = value.match(/okl(ab|ch)\(([^)]+)\)/);
      if (ok) {
        const [p0, p1, p2, alpha = "1"] = ok[2]!.split(/[\s/]+/).filter(Boolean);
        const L = Number.parseFloat(p0!) / (p0!.endsWith("%") ? 100 : 1);
        let A = Number(p1);
        let B = Number(p2);
        if (ok[1] === "ch") {
          const h = (Number.parseFloat(p2!) * Math.PI) / 180;
          [A, B] = [Number(p1) * Math.cos(h), Number(p1) * Math.sin(h)];
        }
        const l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3;
        const m2 = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3;
        const s2 = (L - 0.0894841775 * A - 1.291485548 * B) ** 3;
        const linear = [
          4.0767416621 * l - 3.3077115913 * m2 + 0.2309699292 * s2,
          -1.2684380046 * l + 2.6097574011 * m2 - 0.3413193965 * s2,
          -0.0041960863 * l - 0.7034186147 * m2 + 1.707614701 * s2,
        ];
        const encoded = linear.map((c) => {
          const v = Math.min(1, Math.max(0, c));
          return 255 * (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055);
        });
        return [...encoded, Number.parseFloat(alpha) / (alpha.endsWith("%") ? 100 : 1)];
      }
      const m = value.match(/rgba?\(([^)]+)\)/);
      if (!m) {
        if (value && value !== "transparent") unparsed.push(value);
        return null;
      }
      const [r, g, b, a = "1"] = m[1]!.split(/[\s,/]+/).filter(Boolean);
      return [Number(r), Number(g), Number(b), Number(a)];
    };
    const luminance = ([r, g, b]: number[]) => {
      const [R, G, B] = [r, g, b].map((c) => {
        const v = c! / 255;
        return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * R! + 0.7152 * G! + 0.0722 * B!;
    };
    const background = (el: Element) => {
      const layers: number[][] = [];
      for (let node: Element | null = el; node; node = node.parentElement) {
        const c = parse(getComputedStyle(node).backgroundColor);
        if (c && c[3]! > 0) {
          layers.push(c);
          if (c[3] === 1) break;
        }
      }
      let out = [255, 255, 255];
      for (const layer of layers.reverse()) {
        const alpha = layer[3]!;
        out = out.map((v, i) => layer[i]! * alpha + v * (1 - alpha));
      }
      return out;
    };
    const rows = Array.from(document.querySelectorAll(sel))
      .filter((el) => (el as HTMLElement).offsetParent !== null && (el.textContent || "").trim())
      .map((el) => {
        const style = getComputedStyle(el);
        const fg = parse(style.color)!;
        for (let node: Element | null = el; node; node = node.parentElement) fg[3] = fg[3]! * Number(getComputedStyle(node).opacity);
        const bg = background(el);
        const blended = fg.slice(0, 3).map((v, i) => v * fg[3]! + bg[i]! * (1 - fg[3]!));
        const [l1, l2] = [luminance(blended), luminance(bg)].sort((x, y) => y - x);
        // Cada texto é medido onde o operador o lê: rolado até o meio da área visível
        // (no celular a página rola; na mesa, a coluna). Abaixo da dobra não é defeito;
        // encoberto pela barra de baixo depois de rolar, é.
        (el as HTMLElement).scrollIntoView({ block: "center", behavior: "instant" });
        const box = el.getBoundingClientRect();
        const visible = box.bottom > 0 && box.top < window.innerHeight;
        return {
          text: (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 70),
          contrast: Math.round(((l1! + 0.05) / (l2! + 0.05)) * 100) / 100,
          fontPx: Number.parseFloat(style.fontSize),
          color: `rgb(${blended.map(Math.round).join(", ")})`,
          background: `rgb(${bg.map(Math.round).join(", ")})`,
          left: Math.round(box.left),
          right: Math.round(box.right),
          top: Math.round(box.top),
          visible,
          clipped: (el as HTMLElement).scrollWidth > (el as HTMLElement).clientWidth + 1,
          inside: box.left >= 0 && box.right <= window.innerWidth + 0.5,
          // A dica "tem mais abaixo" (`MoreBelow`) flutua por cima do conteúdo enquanto
          // há o que rolar, e some quando o operador chega ao fim: ela não conta como
          // camada por cima (fica registrada em `underScrollHint`).
          underScrollHint: Boolean(
            document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2)?.closest("[data-more-below]"),
          ),
          covered: visible && (() => {
            const top = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
            if (top?.closest("[data-more-below]")) return false;
            return !(top && (top === el || el.contains(top) || top.contains(el)));
          })(),
          coveredBy: (() => {
            const top = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
            if (!top || top === el || el.contains(top) || top.contains(el)) return "";
            return `${top.tagName.toLowerCase()} ${(top.getAttribute("class") || "").slice(0, 60)} ${(top.textContent || "").trim().slice(0, 40)}`;
          })(),
        };
      });
    return { rows, unparsed: [...new Set(unparsed)] };
  }, selector);
  expect(unparsed, `cores não lidas pela auditoria: ${unparsed.join(" | ")}`).toEqual([]);
  console.log(`AUDITORIA ${label}: ${JSON.stringify(rows)}`);
  expect(rows.length, `${label}: nada medido`).toBeGreaterThan(0);
  for (const row of rows) {
    expect(row.contrast, `${label}: contraste de "${row.text}"`).toBeGreaterThanOrEqual(4.5);
    expect(row.fontPx, `${label}: letra de "${row.text}"`).toBeGreaterThanOrEqual(12);
    expect(row.inside, `${label}: "${row.text}" fora da tela`).toBe(true);
    expect(row.clipped, `${label}: "${row.text}" cortado`).toBe(false);
    expect(row.covered, `${label}: "${row.text}" encoberto por outra camada`).toBe(false);
  }
  return rows;
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
      await audits(page, "pagamento do saldo", PAYMENT_TEXT);
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
      await audits(page, "troco alto", "[data-pos-total] p");

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
      await audits(page, "troco", "[data-pos-total] p, [data-payment-cta]");

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

    test("o saldo em Pix: o QR da venda, na tela e na Tela do cliente, e a entrega quando o banco confirma", async (
      { cashierAtCounter: page },
      testInfo,
    ) => {
      test.skip(PIX_ROUND !== "pago", "rodada do Pix confirmado (PDV_LIVE_J6_PIX=pago)");
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
      await audits(page, "pix na tela", "[data-balance-pix] header p, [data-balance-pix] p.text-sm, [data-balance-pix] button");
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

    test("o Pix que não chega: o aviso traz Gerar outro Pix, e receber em dinheiro cancela o Pix antes", async (
      { cashierAtCounter: page },
      testInfo,
    ) => {
      test.skip(PIX_ROUND !== "nao-chega", "rodada do Pix que não chega (PDV_LIVE_J6_PIX=nao-chega)");
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
      await audits(page, "aviso do Pix", "[data-balance-pix] header p, [data-balance-pix] button, [data-payment-proof-expired-note]");

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
  });
}
