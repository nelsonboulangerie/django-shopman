import { expect, test, type Page } from "@playwright/test";

// Prévia do "vou verificar" da Concierge no sino do Gestor (WP-07): o cartão com a pergunta
// do cliente, a resposta digitada, a resposta enviada, o erro de envio (o texto fica) e a
// janela do aviso com prazo. Só roda quando alguém pede a prévia (`PREVIA_DIR` = onde
// gravar as capturas): é a evidência para o dono, não uma baseline da matriz.
const BACKEND = "http://127.0.0.1:" + process.env.ORDERS_VISUAL_BACKEND_PORT;
const OUT = process.env.PREVIA_DIR || "";

test.skip(!OUT, "prévia sob pedido: defina PREVIA_DIR");

const VIEWPORTS = [
  { id: "celular-375", width: 375, height: 812 },
  { id: "tablet-768", width: 768, height: 1024 },
];

async function open(page: Page, scenario: string, viewport: (typeof VIEWPORTS)[number]) {
  await page.request.get(BACKEND + "/__visual/scenario?set=" + scenario);
  await page.setViewportSize({ width: viewport.width, height: viewport.height });
  await page.goto("/");
  await expect(page.locator("[data-orders-app]")).toBeVisible();
  await page.waitForTimeout(1200);
  await page.evaluate(() => document.fonts.ready);
}

async function openBell(page: Page) {
  // O primeiro toque pode chegar antes de a caixa hidratar: tenta de novo, uma vez.
  const trigger = page.locator("[data-operator-inbox-trigger]:visible").first();
  const answer = page.locator("[data-operator-inbox-panel] [data-operator-inbox-answer]");
  await trigger.click();
  const opened = await answer.waitFor({ state: "visible", timeout: 4000 }).then(() => true, () => false);
  if (!opened) {
    await page.waitForTimeout(1500);
    await trigger.click();
  }
  await expect(answer).toBeVisible();
}

// Auditoria antes de mostrar (regra da casa): contraste de texto/fundo e tamanho de
// cada peça do cartão, gravados ao lado das capturas.
async function audit(page: Page, scope: string, name: string) {
  const rows = await page.evaluate((root) => {
    const parse = (value: string) => (value.match(/[\d.]+/g) || []).map(Number);
    const lum = ([r, g, b]: number[]) => {
      const c = [r, g, b].map((v) => {
        const x = v / 255;
        return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * c[0]! + 0.7152 * c[1]! + 0.0722 * c[2]!;
    };
    const background = (el: Element | null): number[] => {
      while (el) {
        const rgba = parse(getComputedStyle(el).backgroundColor);
        if (rgba.length >= 3 && (rgba.length < 4 || rgba[3]! > 0.5)) return rgba.slice(0, 3);
        el = el.parentElement;
      }
      return [255, 255, 255];
    };
    const ratio = (a: number[], b: number[]) => {
      const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
      return Math.round(((hi! + 0.05) / (lo! + 0.05)) * 100) / 100;
    };
    const out: Array<Record<string, unknown>> = [];
    const box = document.querySelector(root);
    if (!box) return out;
    for (const el of box.querySelectorAll("[data-operator-inbox-answer] *, [data-operator-inbox-answer-field] textarea")) {
      const text = (el.childNodes.length && [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent!.trim()))
        ? el.textContent!.trim().slice(0, 50) : "";
      if (!text && el.tagName !== "TEXTAREA") continue;
      const style = getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      out.push({
        el: el.tagName.toLowerCase(), text: text || "(campo)", font_px: parseFloat(style.fontSize),
        contrast: ratio(parse(style.color).slice(0, 3), background(el)), width: Math.round(rect.width),
        height: Math.round(rect.height), disabled: (el.closest("button") as HTMLButtonElement | null)?.disabled ?? false,
      });
    }
    return out;
  }, scope);
  const fs = await import("node:fs");
  fs.writeFileSync(`${OUT}/${name}.audit.json`, JSON.stringify(rows, null, 2));
}

async function shot(page: Page, name: string) {
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${OUT}/${name}.png` });
}

for (const viewport of VIEWPORTS) {
  test(`prévia vou verificar · ${viewport.id}`, async ({ page }) => {
    await open(page, "concierge", viewport);
    await openBell(page);
    await shot(page, `${viewport.id}-1-cartao`);

    const field = page.locator("[data-operator-inbox-panel] textarea").first();
    await field.fill("Amanhã tem sim, fica pronto às 9h. A entrega sai a partir das 10h.");
    await shot(page, `${viewport.id}-2-resposta-digitada`);
    await audit(page, "[data-operator-inbox-panel]", `${viewport.id}-2-resposta-digitada`);

    await page.locator("[data-operator-inbox-answer-send]").click();
    await expect(page.getByText("Resposta enviada ao cliente.").first()).toBeVisible();
    await shot(page, `${viewport.id}-3-resposta-enviada`);

    await open(page, "concierge", viewport);
    await openBell(page);
    await field.fill("Teste de janela fechada");
    await page.locator("[data-operator-inbox-answer-send]").click();
    await expect(page.locator("[data-operator-inbox-answer-error]")).toBeVisible();
    await expect(field).toHaveValue("Teste de janela fechada");
    await shot(page, `${viewport.id}-4-erro-de-envio`);
    await audit(page, "[data-operator-inbox-panel]", `${viewport.id}-4-erro-de-envio`);

    await open(page, "concierge-urgent", viewport);
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.locator("[data-operator-inbox-answer]")).toBeVisible();
    await dialog.locator("textarea").fill("Amanhã tem sim, fica pronto às 9h.");
    await shot(page, `${viewport.id}-5-janela-com-prazo`);
    await audit(page, "[role=dialog]", `${viewport.id}-5-janela-com-prazo`);
  });
}
