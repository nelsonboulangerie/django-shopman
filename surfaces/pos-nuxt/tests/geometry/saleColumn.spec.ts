import { expect, test, type Page } from "@playwright/test";

// A COMANDA DE ALTURA INTEIRA (dono, 10/10, com a captura do PDV a 100% de zoom): nas
// quatro resoluções comuns de mesa e notebook, sem zoom, a coluna da comanda vai de
// cima a baixo da janela, e nela, no cabeçalho e na barra da venda nenhum texto corta
// ("Pagamento R$ 135,0…", "6 i… em 8 linhas", "Fecha…", "Croque Monsieu…") e nada se
// sobrepõe (o "Alt S" em cima do título). O total é sagrado: nunca corta. A comanda é
// a cheia do mock (`MOCK_SCENARIO=sale`, comanda 13: nove linhas, nomes compridos, uma
// já na cozinha), com a linha em edição.
const SIZES = [
  { width: 1280, height: 720 },
  { width: 1366, height: 768 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
] as const;

interface Problem {
  kind: "clipped" | "leak" | "overlap";
  text: string;
  detail: string;
}

/** Abre a comanda cheia (13) e deixa uma linha em edição. */
async function openFullTab(page: Page, size: { width: number; height: number }, scheme: "light" | "dark") {
  await page.setViewportSize(size);
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: scheme });
  await page.goto("/");
  await page.getByRole("button", { name: /#13/ }).first().click();
  const rows = page.locator("aside[data-pos-ticket] [data-item-select]");
  await expect(rows).toHaveCount(9);
  await rows.nth(4).click();
  await expect(page.locator("[data-pos-line-editor]")).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

/**
 * Procura, dentro de cada região, texto cortado (largura de conteúdo maior que a
 * caixa, reticências, ou passando da borda do botão ou da região) e sobreposição de
 * dois textos visíveis. Só o que se VÊ: o recorte de rolagem dos ancestrais conta, e
 * o `sr-only` não.
 */
async function scan(page: Page, regions: string[]): Promise<Problem[]> {
  return page.evaluate((selectors) => {
    const problems: Problem[] = [];
    const label = (el: Element) => (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 60);
    function shown(el: Element): el is HTMLElement {
      const style = getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity) > 0 && rect.width > 1 && rect.height > 1;
    }
    function srOnly(el: Element) {
      return Boolean(el.closest(".sr-only"));
    }
    /** O retângulo que se vê: o do elemento recortado pelos ancestrais que recortam. */
    function visibleRect(el: Element) {
      const r = el.getBoundingClientRect();
      let left = r.left, top = r.top, right = r.right, bottom = r.bottom;
      for (let parent = el.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
        const style = getComputedStyle(parent);
        if (/(auto|scroll|hidden|clip)/.test(`${style.overflowX} ${style.overflowY}`)) {
          const f = parent.getBoundingClientRect();
          if (/(auto|scroll|hidden|clip)/.test(style.overflowX)) { left = Math.max(left, f.left); right = Math.min(right, f.right); }
          if (/(auto|scroll|hidden|clip)/.test(style.overflowY)) { top = Math.max(top, f.top); bottom = Math.min(bottom, f.bottom); }
        }
      }
      return { left, top, right, bottom, empty: right - left < 1 || bottom - top < 1 };
    }
    function ownsText(el: Element) {
      return [...el.childNodes].some((node) => node.nodeType === Node.TEXT_NODE && (node.textContent || "").trim());
    }
    for (const selector of selectors) {
      for (const region of document.querySelectorAll<HTMLElement>(selector)) {
        if (!shown(region)) continue;
        const frame = region.getBoundingClientRect();
        const texts = [...region.querySelectorAll<HTMLElement>("*")].filter(
          (el) => shown(el) && !srOnly(el) && ownsText(el) && !visibleRect(el).empty,
        );
        for (const el of texts) {
          const style = getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          // Rolagem de propósito (a faixa da barra da venda rola; a lista da comanda
          // rola na vertical): conteúdo maior que a caixa ali não é corte de texto.
          const scroller = /(auto|scroll)/.test(style.overflowX);
          if (!scroller && el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0 && style.display !== "inline") {
            problems.push({ kind: "clipped", text: label(el), detail: `conteúdo ${el.scrollWidth}px numa caixa de ${el.clientWidth}px` });
          }
          if (style.textOverflow === "ellipsis" && el.scrollWidth > el.clientWidth) {
            problems.push({ kind: "clipped", text: label(el), detail: "reticências" });
          }
          const clamp = style.getPropertyValue("-webkit-line-clamp");
          if (clamp && clamp !== "none" && el.scrollHeight > el.clientHeight + 1) {
            problems.push({ kind: "clipped", text: label(el), detail: `line-clamp ${clamp}` });
          }
          const button = el.parentElement?.closest("button, a[href], [role='button']");
          if (button && region.contains(button)) {
            const b = button.getBoundingClientRect();
            if (rect.left < b.left - 1 || rect.right > b.right + 1 || rect.top < b.top - 1 || rect.bottom > b.bottom + 1) {
              problems.push({ kind: "leak", text: label(el), detail: `passa da borda do botão "${label(button)}"` });
            }
          }
          if (rect.left < frame.left - 1 || rect.right > frame.right + 1) {
            problems.push({ kind: "leak", text: label(el), detail: `passa da borda da região ${selector}` });
          }
        }
        // Sobreposição entre dois textos visíveis (nenhum dentro do outro).
        for (let i = 0; i < texts.length; i += 1) {
          for (let j = i + 1; j < texts.length; j += 1) {
            const a = texts[i]!, b = texts[j]!;
            if (a.contains(b) || b.contains(a)) continue;
            const ra = visibleRect(a), rb = visibleRect(b);
            const w = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left);
            const h = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
            if (w > 2 && h > 2) {
              problems.push({ kind: "overlap", text: `${label(a)} × ${label(b)}`, detail: `${Math.round(w)}×${Math.round(h)}px` });
            }
          }
        }
      }
    }
    return problems;
  }, regions);
}

for (const scheme of ["light", "dark"] as const) {
  for (const size of SIZES) {
    test(`venda ${size.width}x${size.height} (${scheme}): comanda de altura inteira, nada corta, nada se sobrepõe`, async ({ page }) => {
      await openFullTab(page, size, scheme);
      const aside = page.locator("aside[data-pos-ticket]");
      const box = (await aside.boundingBox())!;
      // De cima a baixo, como a barra lateral; o cabeçalho mora só à esquerda dela.
      expect(box.y).toBeLessThanOrEqual(1);
      expect(box.y + box.height).toBeGreaterThanOrEqual(size.height - 1);
      const header = (await page.locator("[data-pos-context-header]").boundingBox())!;
      expect(header.x + header.width).toBeLessThanOrEqual(box.x + 1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

      // O total confirmado: inteiro, dentro do botão do Pagamento.
      const total = page.locator("[data-pos-primary-total-value]");
      await expect(total).toHaveText(/R\$\s?210,10/);
      const totalFits = await total.evaluate((el) => {
        const button = el.closest("[data-pos-primary]")!.getBoundingClientRect();
        const rect = el.getBoundingClientRect();
        return el.scrollWidth <= el.clientWidth + 1 && rect.left >= button.left && rect.right <= button.right && rect.bottom <= button.bottom;
      });
      expect(totalFits).toBe(true);

      // O nome da casa quebra a linha; o comprido ocupa mais de uma.
      const croque = page.locator("aside [data-pos-line-name]").first();
      await expect(croque).toHaveText("Croque Monsieur com salada verde e molho de mostarda Dijon");

      expect(await scan(page, ["aside[data-pos-ticket]", "[data-pos-context-header]"])).toEqual([]);

      // Seleção (Alt S): a barra do lote também cabe.
      await page.locator("[data-pos-select-lines]").click();
      await page.locator("aside [data-item-select]").nth(1).click();
      await page.locator("aside [data-item-select]").nth(2).click();
      await expect(page.locator("[data-pos-selection-bar]")).toContainText("2 selecionadas");
      expect(await scan(page, ["aside[data-pos-ticket]"])).toEqual([]);
    });
  }
}

test("cartões de produto: a mesma altura com nome de 1, 2 ou 3+ linhas", async ({ page }) => {
  for (const size of SIZES) {
    await openFullTab(page, size, "light");
    const cards = page.locator("[data-pos-product]");
    await expect(cards.first()).toBeVisible();
    const report = await page.evaluate(() => {
      const tiles = [...document.querySelectorAll<HTMLElement>("[data-pos-product]")].filter((el) => el.getBoundingClientRect().height > 0);
      const heights = tiles.map((el) => Math.round(el.getBoundingClientRect().height));
      const lines = tiles.map((el) => {
        const name = el.querySelector<HTMLElement>("[data-pos-product-name]")!;
        const lineHeight = Number.parseFloat(getComputedStyle(name).lineHeight);
        return { name: name.textContent?.trim(), rows: Math.round(name.scrollHeight / lineHeight), clamped: name.scrollHeight > name.clientHeight + 1, title: name.title };
      });
      return { heights, lines };
    });
    expect(new Set(report.heights).size, `alturas em ${size.width}: ${report.heights.join(",")}`).toBe(1);
    expect(report.lines.some((line) => line.rows === 1)).toBe(true);
    // O nome de três linhas ou mais corta com reticências e guarda o nome inteiro no `title`.
    const long = report.lines.find((line) => line.name?.startsWith("Croque Monsieur"))!;
    expect(long.title).toBe("Croque Monsieur com salada verde e molho de mostarda Dijon");
    if (long.rows > 2) expect(long.clamped).toBe(true);
  }
});
