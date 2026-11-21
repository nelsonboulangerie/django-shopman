// SONDA — o Pix que vence na VENDA de balcão (#2918, auditoria da coordenação).
//
// A venda fecha em Pix e o cliente não paga. O que a tela diz quando o Pix vence:
// um aviso só, com o botão que resolve (o pedido no Gestor), e o QR que não pode
// mais ser pago some. Pagamento só no simulador local (`payment_mock`), sem
// confirmação; o Pix do canal `pdv` fica em 1 minuto por ajuste declarado do banco
// local, para o vencimento caber na sonda.
//
// Roda à parte (não é jornada `jN`): `PDV_LIVE_PIX_SALE=1 scripts/run_pos_e2e_live.sh pix-vencido`.
// `PDV_LIVE_PIX_SIDE=antes` só captura (a base sem a correção); sem ele, confere.
import type { Page } from "@playwright/test";

import { capture, expect, settled, test } from "./support/operator";

const SIDE = process.env.PDV_LIVE_PIX_SIDE || "depois";
const PRODUCT = process.env.PDV_LIVE_PIX_PRODUCT || "Croissant";

function exact(text: string) {
  return new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
}

async function sellsInPix(page: Page) {
  await page.getByRole("button", { name: /Próxima livre/ }).first().click();
  await settled(page);
  const search = page.getByPlaceholder(/Buscar produto/).locator("visible=true").first();
  await search.click();
  await search.pressSequentially(PRODUCT);
  await page.locator("button[data-pos-product]").filter({ hasText: exact(PRODUCT) }).first().click({ timeout: 30_000 });
  const sheet = page.getByRole("button", { name: "Ver a comanda" }).locator("visible=true").first();
  if (await sheet.isVisible().catch(() => false)) await sheet.click();
  await page.getByRole("button", { name: /^Pagamento|^Outras formas|^Cobrar/ }).locator("visible=true").first().click();
  await page.locator('[data-payment-method="pix"]').and(page.locator(":enabled")).locator("visible=true").first().click();
  await page.getByRole("button", { name: /^Validar/ }).and(page.locator(":enabled")).locator("visible=true").first().click({ timeout: 30_000 });
  await expect(page.locator("[data-sale-result]")).toBeVisible({ timeout: 60_000 });
  await expect(page.locator('img[alt^="QR Code"]').first()).toBeVisible({ timeout: 30_000 });
}

async function still(page: Page) {
  await page.waitForFunction(() =>
    document.getAnimations().every(
      (animation) => animation.playState !== "running" || animation.effect?.getTiming().iterations === Infinity,
    ),
  );
}

/** Contraste, letra, dentro da tela, cortado e encoberto: a régua das jornadas. */
async function audits(page: Page, label: string, selector: string) {
  const rows = await page.evaluate((sel) => {
    const rgb = (value: string) => (value.match(/[\d.]+/g) || []).map(Number);
    const lum = ([r, g, b]: number[]) => {
      const [R, G, B] = [r, g, b].map((c) => {
        const v = c! / 255;
        return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * R! + 0.7152 * G! + 0.0722 * B!;
    };
    const background = (el: Element) => {
      for (let node: Element | null = el; node; node = node.parentElement) {
        const c = rgb(getComputedStyle(node).backgroundColor);
        if (c.length >= 3 && (c[3] ?? 1) === 1) return c;
      }
      return [255, 255, 255];
    };
    return Array.from(document.querySelectorAll(sel))
      .filter((el) => (el as HTMLElement).offsetParent !== null && (el.textContent || "").trim())
      .map((el) => {
        (el as HTMLElement).scrollIntoView({ block: "center", behavior: "instant" });
        const style = getComputedStyle(el);
        const [l1, l2] = [lum(rgb(style.color)), lum(background(el))].sort((x, y) => y - x);
        const box = el.getBoundingClientRect();
        const top = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
        return {
          text: (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 70),
          contrast: Math.round(((l1! + 0.05) / (l2! + 0.05)) * 100) / 100,
          fontPx: Number.parseFloat(style.fontSize),
          left: Math.round(box.left),
          right: Math.round(box.right),
          inside: box.left >= 0 && box.right <= window.innerWidth + 0.5,
          clipped: (el as HTMLElement).scrollWidth > (el as HTMLElement).clientWidth + 1,
          covered: !(top && (top === el || el.contains(top) || top.contains(el) || top.closest("[data-more-below]"))),
        };
      });
  }, selector);
  console.log(`AUDITORIA ${label}: ${JSON.stringify(rows)}`);
  expect(rows.length, `${label}: nada medido`).toBeGreaterThan(0);
  for (const row of rows) {
    expect(row.contrast, `${label}: contraste de "${row.text}"`).toBeGreaterThanOrEqual(4.5);
    expect(row.fontPx, `${label}: letra de "${row.text}"`).toBeGreaterThanOrEqual(12);
    expect(row.inside, `${label}: "${row.text}" fora da tela`).toBe(true);
    expect(row.clipped, `${label}: "${row.text}" cortado`).toBe(false);
    expect(row.covered, `${label}: "${row.text}" encoberto`).toBe(false);
  }
}

test.describe.configure({ mode: "serial" });

for (const device of ["phone", "counter"] as const) {
  test.describe(`Pix vencido na venda · ${device === "phone" ? "375 px" : "1366 px"}`, () => {
    test.use({ device });

    test("o Pix que vence na venda: um aviso só, com o botão que resolve, e sem QR pagável", async (
      { cashierAtCounter: page },
      testInfo,
    ) => {
      test.skip(process.env.PDV_LIVE_PIX_SALE !== "1", "sonda do Pix vencido na venda (PDV_LIVE_PIX_SALE=1)");
      test.setTimeout(10 * 60_000);

      await sellsInPix(page);
      await still(page);
      await capture(page, testInfo, "venda-aguardando-pix");

      // O Pix vence (1 minuto no canal de teste; o worker cancela pelo prazo).
      await expect(page.locator('[data-sale-result] img[alt^="QR Code"]').first()).toBeHidden({ timeout: 4 * 60_000 })
        .catch(() => undefined);
      await expect(page.getByText(/não foi confirmado|Não confirmamos o PIX/).first()).toBeVisible({ timeout: 4 * 60_000 });
      await still(page);
      await capture(page, testInfo, "venda-pix-vencido");
      if (SIDE === "antes") return;

      const result = page.locator("[data-sale-result]");
      await expect(result.locator('img[alt^="QR Code"]')).toHaveCount(0);
      await expect(result.getByText("Copiar código Pix")).toHaveCount(0);
      await expect(result).not.toContainText(/Confira no gestor/i);
      await expect(result).not.toContainText("PIX");
      await expect(result.getByText("O Pix não foi confirmado.")).toHaveCount(1);
      const gestor = result.locator("[data-sale-result-pix-expired] a");
      await expect(gestor).toHaveText(/Abrir o pedido no Gestor/);
      await expect(gestor).toHaveAttribute("href", /\/[A-Z0-9-]+$/);
      await audits(
        page,
        `pix vencido na venda (${device === "phone" ? "375" : "1366"} px)`,
        "[data-sale-result] h2, [data-sale-result-pix-expired] p, [data-sale-result-pix-expired] a, [data-payment-proof-expired] p",
      );
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      console.log(`TRANSBORDO pix vencido na venda (${device === "phone" ? "375" : "1366"} px): ${overflow}`);
      expect(overflow).toBe(0);
    });
  });
}
