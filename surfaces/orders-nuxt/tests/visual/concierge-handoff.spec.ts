import { expect, test, type Page } from "@playwright/test";

// Prévia do handoff com aviso no Gestor (dono, 19/11/2026, camada 3): o aviso no topo,
// na cor de erro, com a causa; o X o dispensa nesta tela e ele volta na próxima enquanto a
// causa durar; e o cartão no sino. Nos dois temas.
const BACKEND = "http://127.0.0.1:" + process.env.ORDERS_VISUAL_BACKEND_PORT;
const OUT = process.env.PREVIA_DIR || "";

test.skip(!OUT, "prévia sob pedido: defina PREVIA_DIR");

const VIEWPORTS = [
  { id: "celular-375", width: 375, height: 812 },
  { id: "escritorio-1366", width: 1366, height: 768 },
];
const THEMES = ["light", "dark"] as const;

async function open(page: Page, scenario: string, viewport: (typeof VIEWPORTS)[number]) {
  await page.request.get(BACKEND + "/__visual/scenario?set=" + scenario);
  await page.setViewportSize({ width: viewport.width, height: viewport.height });
  await page.goto("/");
  await expect(page.locator("[data-orders-app]")).toBeVisible();
  await page.waitForTimeout(1200);
  await page.evaluate(() => document.fonts.ready);
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
    for (const el of box.querySelectorAll("[data-operator-inbox-answer] *, [data-operator-inbox-answer-field] textarea, [data-page-header-alert] *, button, button *, [data-operator-inbox-panel] p")) {
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
  for (const theme of THEMES) {
    test(`prévia handoff com aviso · ${viewport.id} · ${theme}`, async ({ page }) => {
      const id = `${viewport.id}-${theme}`;
      await page.addInitScript(
        ([value, key]) => {
          localStorage.setItem("nuxt-color-mode", value);
          localStorage.setItem(key, value);
        },
        [theme, "orders-nuxt-color-mode"],
      );

      // 1. O aviso no topo, cor de erro, com a causa.
      await open(page, "concierge-handoff", viewport);
      await expect(page.locator("html")).toHaveClass(theme === "dark" ? /dark/ : /light/);
      const notice = page.locator("[data-page-header-alert]", { hasText: "Ana pediu para falar com alguém da equipe" });
      await expect(notice).toBeVisible();
      // Só o que ela escreveu e há quanto tempo (coordenação, 20/11/2026).
      await expect(notice).toContainText("“Quero falar com um humano” ·\u00a0há\u00a03\u00a0min");
      for (const noise of ["urgência", "Cliente:", "Responda pelo", "/admin/"]) {
        await expect(notice).not.toContainText(noise);
      }
      await expect(notice.getByRole("link", { name: "Responder no Live Chat" })).toHaveAttribute(
        "href", "https://app.manychat.com/fb486126/chat/1234567890",
      );
      await expect(notice.getByRole("link", { name: "Abrir conversa" })).toHaveAttribute(
        "href", "https://admin.boulangerie.com.br/admin/shop/conversation/2/change/",
      );
      if (viewport.width < 768) {
        // No celular o aviso vem DEPOIS das abas (as abas são barra; o aviso, o 1º conteúdo).
        const tabs = page.getByText("Em preparo", { exact: false }).first();
        const [tabBox, noticeBox] = [await tabs.boundingBox(), await notice.boundingBox()];
        expect(tabBox && noticeBox && noticeBox.y >= tabBox.y + tabBox.height).toBeTruthy();
      }
      await shot(page, `${id}-1-aviso-no-topo`);
      await audit(page, "[data-page-header-alerts]", `${id}-1-aviso-no-topo`);

      // 2. O X dispensa nesta tela; na próxima, volta (a causa continua).
      await notice.getByRole("button", { name: /fechar|close/i }).click();
      await expect(notice).toBeHidden();
      await shot(page, `${id}-2a-dispensado`);
      await page.goto("/history");
      await page.goto("/");
      await expect(page.locator("[data-orders-app]")).toBeVisible();
      await expect(notice).toBeVisible();
      await shot(page, `${id}-2b-voltou`);

      // 3. O cartão no sino.
      const trigger = page.locator("[data-operator-inbox-trigger]:visible").first();
      await trigger.click();
      const panel = page.locator("[data-operator-inbox-panel]");
      if (!(await panel.isVisible())) {
        await page.waitForTimeout(1500);
        await trigger.click();
      }
      await expect(panel).toContainText("conversa para a equipe");
      await expect(panel.getByRole("link", { name: /Responder no Live Chat/ }).first()).toBeVisible();
      await expect(panel.getByRole("link", { name: /Abrir conversa/ }).first()).toBeVisible();
      // #3578 (dono, 24/11: "Com confirmação"): "Responder no Live Chat" é o principal; "Devolver à Concierge"
      // vem em contorno, e pede confirmação.
      const giveBack = panel.getByRole("button", { name: "Devolver à Concierge" });
      await expect(giveBack).toBeVisible();
      const [liveChatBox, giveBackBox] = [
        await panel.getByRole("link", { name: /Responder no Live Chat/ }).first().boundingBox(),
        await giveBack.boundingBox(),
      ];
      expect(liveChatBox && giveBackBox && liveChatBox.y < giveBackBox.y).toBeTruthy();
      await shot(page, `${id}-3-cartao-no-sino`);
      await audit(page, "[data-operator-inbox-panel]", `${id}-3-cartao-no-sino`);

      // 4. Sem confirmar, nada é devolvido: o "Cancelar" fecha o diálogo e nenhuma chamada sai.
      const posts: string[] = [];
      page.on("request", (request) => {
        if (request.method() === "POST" && request.url().includes("/concierge-handoff/give-back/")) posts.push(request.url());
      });
      await giveBack.click();
      const dialog = page.getByRole("alertdialog").or(page.getByRole("dialog")).filter({ hasText: "A equipe terminou com este cliente?" });
      await expect(dialog).toBeVisible();
      await expect(dialog).toContainText("A Concierge volta a responder.");
      await shot(page, `${id}-4-confirmacao`);
      await audit(page, "body", `${id}-4-confirmacao`);
      await dialog.getByRole("button", { name: "Cancelar" }).click();
      await expect(dialog).toBeHidden();
      await page.waitForTimeout(400);
      expect(posts).toEqual([]);

      // 5. Com o "Devolver" do diálogo, a conversa volta, e o cartão sai.
      await giveBack.click();
      await dialog.getByRole("button", { name: "Devolver" }).click();
      await expect.poll(() => posts.length).toBe(1);
      await expect(panel.getByRole("button", { name: "Devolver à Concierge" })).toBeHidden();
    });
  }
}
