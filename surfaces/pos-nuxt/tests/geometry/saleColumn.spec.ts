import { expect, test, type Page } from "@playwright/test";

// A COMANDA DE ALTURA INTEIRA (dono, 10/10, com a captura do PDV a 100% de zoom): nas
// quatro resoluções comuns de mesa e notebook, sem zoom, a coluna da comanda vai de
// cima a baixo da janela, e nela, no cabeçalho e na barra da venda nenhum texto corta
// ("Pagamento R$ 135,0…", "6 i… em 8 linhas", "Fecha…", "Croque Monsieu…") e nada se
// sobrepõe (o "Alt S" em cima do título). A coluna é a das quatro zonas (WP-PDV-COLUNA-
// COMANDA): cabeçalho fixo, lista, bloco de ação colado no pé e o pé. O total é sagrado: nunca corta. A comanda é
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

// A largura da coluna da comanda é ajustável (DashboardSidebar do Nuxt UI, em rem,
// gravada no cookie `pos-sale-sidebar-ticket`): a trava cobre o padrão, o mínimo e o
// máximo. Os números são os de `pages/index.vue` (TICKET_*_REM).
const TICKET_REM = { min: 22, default: 25, max: 32 } as const;
type TicketWidth = keyof typeof TICKET_REM;

/** A divisória de baixo do cabeçalho da comanda corre na MESMA linha da barra do topo
 *  da venda (dono, 10/10: o degrau de poucos pixels é desalinhamento barato). */
async function headerStep(page: Page, ticketHeader: string) {
  return page.evaluate((selector) => {
    const top = document.querySelector("[data-pos-context-header] > [data-operator-page-header]")!.getBoundingClientRect().bottom;
    const ticket = document.querySelector(selector)!.getBoundingClientRect().bottom;
    return Math.abs(top - ticket);
  }, ticketHeader);
}

/** Abre a comanda cheia (13) e, por padrão, deixa uma linha em edição. */
async function openFullTab(
  page: Page,
  size: { width: number; height: number },
  scheme: "light" | "dark",
  width: TicketWidth = "default",
  selectLine = true,
) {
  await page.setViewportSize(size);
  if (width !== "default") {
    await page.context().addCookies([{
      name: "pos-sale-sidebar-ticket",
      value: encodeURIComponent(JSON.stringify({ size: TICKET_REM[width], collapsed: false })),
      url: `http://127.0.0.1:${process.env.POS_GEOMETRY_PORT || 33032}`,
    }]);
  }
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: scheme });
  // O PDV é claro por preferência (`colorMode.preference`), não pelo sistema: o escuro
  // é o toggle, guardado no dispositivo.
  await page.addInitScript((mode) => window.localStorage.setItem("pos-nuxt-color-mode", mode), scheme);
  await page.goto("/");
  await page.getByRole("button", { name: /#13/ }).first().click();
  const rows = page.locator("[data-pos-ticket-column] [data-item-select]");
  await expect(rows).toHaveCount(9);
  if (selectLine) {
    await rows.nth(4).click();
    await expect(page.locator("[data-pos-line-editor]")).toBeVisible();
  } else if (await page.locator("[data-pos-line-editor-close]").isVisible()) {
    // Sem linha aberta: o editor fechado (×, Esc), só a lista e as ações da comanda.
    await page.locator("[data-pos-line-editor-close]").click();
    await expect(page.locator("[data-pos-line-editor]")).toHaveCount(0);
  }
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

const CASES = [
  ...(["light", "dark"] as const).flatMap((scheme) => SIZES.map((size) => ({ scheme, size, width: "default" as TicketWidth }))),
  ...(["min", "max"] as const).flatMap((width) => SIZES.map((size) => ({ scheme: "light" as const, size, width }))),
];
for (const { scheme, size, width } of CASES) {
  {
    test(`venda ${size.width}x${size.height} (${scheme}, coluna ${width}): comanda de altura inteira, nada corta, nada se sobrepõe`, async ({ page }) => {
      await openFullTab(page, size, scheme, width);
      const aside = page.locator("[data-pos-ticket-column]");
      const box = (await aside.boundingBox())!;
      // A largura é a escolhida (rem × 16 px), dentro do mínimo e do máximo.
      expect(Math.abs(box.width - TICKET_REM[width] * 16)).toBeLessThanOrEqual(1);
      // De cima a baixo, como a barra lateral; o cabeçalho mora só à esquerda dela.
      expect(box.y).toBeLessThanOrEqual(1);
      expect(box.y + box.height).toBeGreaterThanOrEqual(size.height - 1);
      // O cabeçalho é `display: contents`: quem tem caixa é a faixa dele e a barra da venda.
      for (const band of ["[data-pos-context-header] > [data-operator-page-header]", "[data-pos-sale-bar]"]) {
        const header = (await page.locator(band).boundingBox())!;
        expect(header.x + header.width, band).toBeLessThanOrEqual(box.x + 1);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      expect(await headerStep(page, "[data-pos-ticket-header]")).toBeLessThanOrEqual(0.5);

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
      const croque = page.locator("[data-pos-ticket-column] [data-pos-line-name]").first();
      await expect(croque).toHaveText("Croque Monsieur com salada verde e molho de mostarda Dijon");

      expect(await scan(page, ["[data-pos-ticket-column]", "[data-pos-context-header] > [data-operator-page-header]", "[data-pos-sale-bar]"])).toEqual([]);

      // A grade de controles: duas colunas de MESMA largura, bordas batendo, e o
      // Pagamento com a largura da grade inteira.
      const grid = await page.evaluate(() => {
        const cells = [...document.querySelectorAll<HTMLElement>("[data-pos-ticket-controls] > [data-pos-control-cell]")].map((el) => el.getBoundingClientRect());
        const pay = document.querySelector("[data-pos-primary]")!.getBoundingClientRect();
        const lefts = [...new Set(cells.map((r) => Math.round(r.left)))].sort((a, b) => a - b);
        const rights = [...new Set(cells.map((r) => Math.round(r.right)))].sort((a, b) => a - b);
        const halves = cells.filter((r) => r.width < pay.width / 2 + 1).map((r) => Math.round(r.width));
        return { lefts, rights, halves: [...new Set(halves)], payLeft: Math.round(pay.left), payRight: Math.round(pay.right), count: cells.length };
      });
      expect(grid.count).toBe(6);
      expect(grid.lefts.length).toBe(2);
      expect(grid.rights.length).toBe(2);
      expect(grid.halves.length).toBe(1);
      expect(grid.lefts[0]).toBe(grid.payLeft);
      expect(grid.rights[1]).toBe(grid.payRight);

      // MARCAR SEM MODO (dono, 10/10): a caixa aparece sem empurrar nada (a coluna do
      // nome e do preço fica onde estava), o cabeçalho não troca nem pula, e o bloco de N
      // tem as MESMAS colunas do bloco de 1.
      const rowsBefore = await page.evaluate(() =>
        [...document.querySelectorAll<HTMLElement>("[data-pos-ticket-column] [data-pos-line-name]")].map((el) => Math.round(el.getBoundingClientRect().left)),
      );
      const headerBefore = (await page.locator("[data-pos-ticket-header]").boundingBox())!;
      await page.locator("[data-pos-ticket-column] [data-pos-line-mark]").nth(1).click();
      await page.locator("[data-pos-ticket-column] [data-pos-line-mark]").nth(2).click();
      await expect(page.locator("[data-pos-marked-title]")).toContainText("3 linhas marcadas");
      await expect(page.locator("[data-pos-fire]")).toContainText(/Enviar 3|Enviar 3 marcadas/);
      const rowsAfter = await page.evaluate(() =>
        [...document.querySelectorAll<HTMLElement>("[data-pos-ticket-column] [data-pos-line-name]")].map((el) => Math.round(el.getBoundingClientRect().left)),
      );
      expect(rowsAfter).toEqual(rowsBefore);
      const headerAfter = (await page.locator("[data-pos-ticket-header]").boundingBox())!;
      expect(Math.abs(headerAfter.height - headerBefore.height)).toBeLessThanOrEqual(0.5);
      expect(await headerStep(page, "[data-pos-ticket-header]")).toBeLessThanOrEqual(0.5);
      const marked = await page.evaluate(() => {
        const cells = [...document.querySelectorAll<HTMLElement>("[data-pos-ticket-controls] > [data-pos-control-cell]")].map((el) => el.getBoundingClientRect());
        const pay = document.querySelector("[data-pos-primary]")!.getBoundingClientRect();
        return {
          lefts: [...new Set(cells.map((r) => Math.round(r.left)))].sort((a, b) => a - b),
          rights: [...new Set(cells.map((r) => Math.round(r.right)))].sort((a, b) => a - b),
          payLeft: Math.round(pay.left),
          payRight: Math.round(pay.right),
          count: cells.length,
        };
      });
      expect(marked.count).toBe(6);
      expect(marked.lefts).toEqual(grid.lefts);
      expect(marked.rights).toEqual(grid.rights);
      expect(await scan(page, ["[data-pos-ticket-column]"])).toEqual([]);
      // Esc desmarca tudo e volta ao bloco de 1.
      await page.keyboard.press("Escape");
      await expect(page.locator("[data-pos-marked-title]")).toHaveCount(0);
    });
  }
}

for (const size of SIZES) {
  test(`venda ${size.width}x${size.height} sem linha aberta: só as ações da comanda, sem buraco`, async ({ page }) => {
    await openFullTab(page, size, "light", "min", false);
    const cells = page.locator("[data-pos-ticket-controls] > [data-pos-control-cell]");
    await expect(cells).toHaveCount(2);
    await expect(page.locator("[data-pos-control-cell='fire']")).toBeVisible();
    await expect(page.locator("[data-pos-control-cell='split']")).toBeVisible();
    expect(await scan(page, ["[data-pos-ticket-column]"])).toEqual([]);
  });
}

test("a alça do Nuxt UI ajusta a largura entre o mínimo e o máximo", async ({ page }) => {
  await openFullTab(page, { width: 1366, height: 768 }, "light", "default", false);
  const column = page.locator("[data-pos-ticket-column]");
  const handle = page.locator("[data-pos-sale-layout] [data-slot='handle']");
  const start = (await column.boundingBox())!;
  const grip = (await handle.boundingBox())!;
  await page.mouse.move(grip.x + grip.width / 2, grip.y + grip.height / 2);
  await page.mouse.down();
  await page.mouse.move(grip.x - 600, grip.y + grip.height / 2, { steps: 8 });
  await page.mouse.up();
  expect(Math.abs((await column.boundingBox())!.width - TICKET_REM.max * 16)).toBeLessThanOrEqual(1);
  const now = (await handle.boundingBox())!;
  await page.mouse.move(now.x + now.width / 2, now.y + now.height / 2);
  await page.mouse.down();
  await page.mouse.move(now.x + 800, now.y + now.height / 2, { steps: 8 });
  await page.mouse.up();
  expect(Math.abs((await column.boundingBox())!.width - TICKET_REM.min * 16)).toBeLessThanOrEqual(1);
  expect(start.width).toBeGreaterThan(0);
});

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
        // As linhas do TEXTO (o `min-h-[2lh]` reserva duas mesmo com uma só, então a
        // altura da caixa não conta): uma linha por topo distinto dos retângulos dele.
        const range = document.createRange();
        range.selectNodeContents(name);
        const rows = new Set([...range.getClientRects()].map((rect) => Math.round(rect.top))).size;
        return { name: name.textContent?.trim(), rows, clamped: name.scrollHeight > name.clientHeight + 1, title: name.title };
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

// A EDIÇÃO DA LINHA no editor (dono, 10/10): desconto e observação no lugar da grade,
// com Cancelar/Aplicar; o formato do desconto e os botões batem com as colunas.
for (const width of ["min", "max"] as const) {
  test(`edição da linha no editor (coluna ${width}): desconto e observação cabem e alinham`, async ({ page }) => {
    await openFullTab(page, { width: 1280, height: 720 }, "light", width);
    await page.locator("[data-pos-line-discount]").click();
    await page.keyboard.press("1");
    await expect(page.locator("[data-pos-discount-panel]")).toBeVisible();
    const aligned = await page.evaluate(() => {
      const panel = document.querySelector("[data-pos-discount-panel]")!.getBoundingClientRect();
      const pay = document.querySelector("[data-pos-primary]")!.getBoundingClientRect();
      const buttons = [...document.querySelectorAll<HTMLElement>("[data-pos-discount-panel] > button")].map((b) => b.getBoundingClientRect());
      return {
        panelEdges: [Math.round(panel.left), Math.round(panel.right)],
        payEdges: [Math.round(pay.left), Math.round(pay.right)],
        firstRowWidths: [...new Set(buttons.slice(0, 2).map((r) => Math.round(r.width)))].length,
      };
    });
    expect(aligned.panelEdges).toEqual(aligned.payEdges);
    expect(aligned.firstRowWidths).toBe(1);
    expect(await scan(page, ["[data-pos-ticket-column]"])).toEqual([]);
    await page.keyboard.press("Escape");
    await expect(page.locator("[data-pos-discount-panel]")).toHaveCount(0);

    await page.locator("[data-pos-line-note]").click();
    await expect(page.locator("[data-pos-note-panel] textarea")).toBeFocused();
    expect(await scan(page, ["[data-pos-ticket-column]"])).toEqual([]);
    await page.keyboard.press("Escape");
    await expect(page.locator("[data-pos-note-panel]")).toHaveCount(0);
  });
}

test("cabeçalho da comanda alinhado com a barra do topo também na comanda curta", async ({ page }) => {
  for (const size of SIZES) {
    await page.setViewportSize(size);
    await page.goto("/");
    await page.getByRole("button", { name: /#14/ }).first().click();
    await expect(page.locator("[data-pos-ticket-header]")).toBeVisible();
    expect(await headerStep(page, "[data-pos-ticket-header]"), `${size.width}`).toBeLessThanOrEqual(0.5);
  }
});

// SEM CONEXÃO: o que precisa do servidor apaga com o motivo em palavra, e nada corta.
for (const width of ["min", "max"] as const) {
  test(`sem conexão (coluna ${width}): o motivo cabe, nada corta`, async ({ page }) => {
    await openFullTab(page, { width: 1366, height: 768 }, "light", width);
    await page.context().setOffline(true);
    await expect(page.locator("[data-pos-kitchen-offline]")).toBeVisible();
    await expect(page.locator("[data-pos-block-offline]")).toBeVisible();
    expect(await scan(page, ["[data-pos-ticket-column]"])).toEqual([]);
    await page.context().setOffline(false);
  });
}
