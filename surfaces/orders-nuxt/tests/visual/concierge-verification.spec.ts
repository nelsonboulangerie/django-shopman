import { expect, test, type Page } from "@playwright/test";

// Prévia do "vou verificar" da Concierge no Gestor (WP-07): a pergunta chega como aviso de
// tela no topo, na cor da atenção (dono, 19/11/2026); o X o dispensa nesta tela e ele volta
// na próxima; "Responder" abre a janela com o campo; respondida, tudo some; vencido o
// prazo, a janela interrompe a tela e o aviso fica vermelho. Nos dois temas. Só roda quando alguém pede a prévia (`PREVIA_DIR` = onde
// gravar as capturas): é a evidência para o dono, não uma baseline da matriz.
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
async function audit(page: Page, scope: string, name: string, toastText = "") {
  const rows = await page.evaluate(([root, toast]) => {
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
    // O toast (WP-15): o item da lista de avisos que contém o texto, inteiro.
    const toastBox = toast
      ? [...document.querySelectorAll("li")].find((li) => (li.textContent || "").includes(toast)) ?? null
      : null;
    const box = toast ? toastBox : document.querySelector(root);
    if (!box) return out;
    const pieces = toast
      ? box.querySelectorAll("*")
      : box.querySelectorAll("[data-operator-inbox-answer] *, [data-operator-inbox-answer-field] textarea, [data-page-header-alert] *");
    for (const el of pieces) {
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
  }, [scope, toastText] as const);
  const fs = await import("node:fs");
  fs.writeFileSync(`${OUT}/${name}.audit.json`, JSON.stringify(rows, null, 2));
}

async function shot(page: Page, name: string) {
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${OUT}/${name}.png` });
}

for (const viewport of VIEWPORTS) {
  for (const theme of THEMES) {
    test(`prévia vou verificar · ${viewport.id} · ${theme}`, async ({ page }) => {
      const id = `${viewport.id}-${theme}`;
      await page.addInitScript(
        ([value, key]) => {
          localStorage.setItem("nuxt-color-mode", value);
          localStorage.setItem(key, value);
        },
        [theme, "orders-nuxt-color-mode"],
      );
      // 1. A pergunta chega: o aviso no topo, âmbar, sem janela por cima.
      await open(page, "concierge", viewport);
      await expect(page.locator("html")).toHaveClass(theme === "dark" ? /dark/ : /light/);
      const notice = page.locator("[data-page-header-alert]", { hasText: "Ana espera a resposta da equipe" });
      const dialog = page.getByRole("dialog");
      await expect(notice).toBeVisible();
      await expect(notice).toContainText(/Ana espera a resposta da equipe\s·\saté\s\d{1,2}h(\d{2})?/);
      await expect(dialog).toBeHidden();
      await shot(page, `${id}-1-aviso-chegando`);
      await audit(page, "[data-page-header-alerts]", `${id}-1-aviso-chegando`);

      // 2. O X dispensa nesta tela; na próxima (aqui, a volta à fila), o aviso volta.
      await notice.getByRole("button", { name: /fechar|close/i }).click();
      await expect(notice).toBeHidden();
      await shot(page, `${id}-2a-aviso-dispensado`);
      await page.goto("/history");
      await page.goto("/");
      await expect(page.locator("[data-orders-app]")).toBeVisible();
      await expect(notice).toBeVisible();
      await shot(page, `${id}-2b-aviso-voltou`);

      // 3. "Responder" abre a janela com o campo.
      await notice.getByRole("button", { name: "Responder" }).click();
      await expect(dialog.locator("[data-operator-inbox-answer]")).toBeVisible();
      await shot(page, `${id}-3-janela-pelo-responder`);
      await audit(page, "[role=dialog]", `${id}-3-janela-pelo-responder`);

      // 4. Respondida: a pergunta sai, e não sobra aviso.
      await dialog.locator("textarea").fill("Amanhã tem sim, fica pronto às 9h. A entrega sai a partir das 10h.");
      await dialog.locator("[data-operator-inbox-answer-send]").click();
      await expect(page.getByText("Resposta enviada ao cliente.").first()).toBeVisible();
      await expect(dialog).toBeHidden();
      await expect(notice).toBeHidden();
      await shot(page, `${id}-4-respondido-sem-aviso`);

      // 4b. WP-15: o aviso de "Resposta enviada" traz "Promover a pergunta frequente".
      const promote = page.getByRole("button", { name: "Promover a pergunta frequente" });
      await expect(promote).toBeVisible();
      await shot(page, `${id}-4b-promover-no-aviso`);
      await audit(page, "", `${id}-4b-promover-no-aviso`, "Resposta enviada ao cliente.");
      await promote.click();
      // 4c. Virou rascunho (aqui com o aviso de data: a resposta diz "Amanhã"), e o Admin.
      await expect(page.getByText(/Virou rascunho em Perguntas frequentes/).first()).toBeVisible();
      await expect(page.getByText(/cita um dia ou uma data/).first()).toBeVisible();
      await expect(page.getByRole("link", { name: "Abrir no Admin" })).toHaveAttribute(
        "href", "https://admin.boulangerie.com.br/admin/shop/faqentry/12/change/",
      );
      await shot(page, `${id}-4c-rascunho-criado`);
      await audit(page, "", `${id}-4c-rascunho-criado`, "Virou rascunho em Perguntas frequentes");

      // 5. A promessa venceu: a janela interrompe a tela; depois do Visto, o aviso fica vermelho.
      await open(page, "concierge-late", viewport);
      await expect(dialog).toBeVisible();
      await expect(dialog.getByText(/Passou do prazo/)).toBeVisible();
      await shot(page, `${id}-5a-vencido-janela`);
      await dialog.getByRole("button", { name: "Visto" }).click();
      await expect(dialog).toBeHidden();
      await expect(notice).toBeVisible();
      await expect(notice).toContainText(/Ana espera a resposta da equipe\s·\spassou\sdo\sprazo\shá\s\d+\smin/);
      await shot(page, `${id}-5b-vencido-aviso`);
      await audit(page, "[data-page-header-alerts]", `${id}-5b-vencido-aviso`);
    });
  }
}
