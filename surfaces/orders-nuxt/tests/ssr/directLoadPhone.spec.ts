import { expect, test, type Page } from "@playwright/test";

// Carga direta (recarregar, PWA abrindo numa rota, link) com SSR, no build de produção.
//
// O defeito (alpha, 09/10/2026): dez telas decidiam `v-if` de layout com
// `useMediaQuery` próprio. O servidor desenhava a mesa; a 390 px o cliente hidratava
// outra árvore. A Fila ficava no esqueleto para sempre (`Cannot read properties of
// null (reading 'emitsOptions')`) e a toolbar do Histórico, dos Clientes e do Catálogo
// sumia. Navegando por dentro aparecia certo, por isso a matriz visual (client-only)
// nunca viu. A régua agora é a do kit (`useScreen`), segura para o SSR, e a trava
// estática está em `operator-kit/tests/guardrails.screen.test.ts`.
//
// Aqui: cada rota, aberta direto, não pode acusar mismatch de hidratação nem erro de
// página, e o que a tela do celular promete tem que estar na tela.

const ROUTES = [
  "/",
  "/?columns=expedition",
  "/history",
  "/customers",
  "/catalog",
  "/IFOOD-261006-W01",
  "/feeds",
  "/workstations",
  "/settings",
  "/customers/merges",
] as const;

const WIDTHS = [
  { name: "celular", width: 390, height: 844, isMobile: true, hasTouch: true },
  { name: "mesa", width: 1440, height: 900, isMobile: false, hasTouch: false },
] as const;

/** Abre a rota direto e devolve os erros de hidratação e de página. */
async function openDirect(page: Page, path: string): Promise<string[]> {
  const problems: string[] = [];
  page.on("pageerror", (error) => problems.push(`erro de página: ${error.message}`));
  page.on("console", (message) => {
    const text = message.text();
    if (/hydration|mismatch/i.test(text)) problems.push(`hidratação: ${text.slice(0, 300)}`);
    else if (message.type() === "error" && /emitsOptions|Cannot (read|destructure)/.test(text))
      problems.push(`erro: ${text.slice(0, 300)}`);
  });
  await page.goto(path, { waitUntil: "networkidle" });
  // A largura real entra depois da hidratação: dá tempo de a troca acontecer.
  await page.waitForTimeout(1_000);
  return problems;
}

for (const size of WIDTHS) {
  test.describe(`carga direta, ${size.name} (${size.width} px)`, () => {
    test.use({
      viewport: { width: size.width, height: size.height },
      isMobile: size.isMobile,
      hasTouch: size.hasTouch,
    });

    for (const path of ROUTES) {
      test(`${path} hidrata a mesma árvore do servidor`, async ({ page }) => {
        expect(await openDirect(page, path)).toEqual([]);
      });
    }
  });
}

test.describe("carga direta no celular: a tela que o celular promete", () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test("a Fila sai do esqueleto e mostra as abas e os cartões", async ({ page }) => {
    expect(await openDirect(page, "/")).toEqual([]);
    await expect(page.locator("[data-board-zone-tabs]")).toBeVisible();
    await expect(page.getByLabel("Carregando fila")).toHaveCount(0);
    await expect(page.locator("[data-card-primary]").first()).toBeVisible();
  });

  for (const path of ["/history", "/catalog"]) {
    test(`${path} tem a linha da toolbar com "Filtros"`, async ({ page }) => {
      expect(await openDirect(page, path)).toEqual([]);
      await expect(page.locator("[data-page-header-filter-line]")).toBeVisible();
      // O painel de filtros único (fase 2, K4): no celular, o ícone na ponta da linha.
      await expect(page.locator("[data-page-header-filter-panel] [data-operator-filter-panel-open]")).toBeVisible();
    });
  }

  test("/history abre o painel com a Data (o período da lista mora nele)", async ({ page }) => {
    await openDirect(page, "/history");
    await page.locator("[data-operator-filter-panel-open]").click();
    await expect(page.locator("[data-operator-filter-panel]")).toBeVisible();
    await expect(page.locator("[data-operator-filter-panel]").getByText("Data", { exact: true })).toBeVisible();
  });

  test("/catalog tem a Coleção na linha", async ({ page }) => {
    await openDirect(page, "/catalog");
    await expect(page.locator("[data-collection-select]")).toBeVisible();
  });

  test("/customers tem a linha da toolbar", async ({ page }) => {
    expect(await openDirect(page, "/customers")).toEqual([]);
    await expect(page.locator("[data-page-header-filter-line]")).toBeVisible();
  });
});

// O PRIMEIRO desenho (09/10/2026): a régua do kit responde "mesa" até montar, e a barra
// do topo da Fila nascia no celular com a linha da mesa (busca, som, "Urgência",
// "Grade | Lista") por cima do título "Pedidos", até a hidratação terminar. Em rede
// lenta, segundos. Sem JavaScript, o que fica na tela é o HTML do servidor: ele já tem
// de ser o layout do celular.
test.describe("primeiro desenho no celular (HTML do servidor, sem JavaScript)", () => {
  test.use({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    javaScriptEnabled: false,
  });

  for (const path of ROUTES) {
    test(`${path} já nasce com a barra do celular`, async ({ page }) => {
      await page.goto(path, { waitUntil: "load" });
      const bar = await page.evaluate(() => {
        const shown = (el: Element) =>
          el.getClientRects().length > 0 && getComputedStyle(el).visibility !== "hidden";
        const header = document.querySelector("[data-operator-page-header]");
        const title = header?.querySelector("[data-slot='title']");
        const titleBox = title?.getBoundingClientRect();
        // Os controles da barra que se desenham sobre o título.
        const covering = [...(header?.querySelectorAll("button, a, input") ?? [])]
          .filter(shown)
          .filter((el) => {
            if (!titleBox || title?.contains(el)) return false;
            const box = el.getBoundingClientRect();
            return (
              box.left < titleBox.right - 1 &&
              box.right > titleBox.left + 1 &&
              box.top < titleBox.bottom - 1 &&
              box.bottom > titleBox.top + 1
            );
          })
          .map((el) => el.getAttribute("aria-label") || el.textContent?.trim() || el.tagName);
        // O que só a mesa desenha (a linha encavalada de 09/10).
        const deskOnly = [
          "[data-sound-group]",
          "[data-page-header-actions] [data-view-switch]",
          "[data-page-header-actions] [data-board-sort]",
          "[data-action='menu']",
          "[data-page-header-filters]",
          "[data-queue-scopes]",
        ].filter((selector) => [...document.querySelectorAll(selector)].some(shown));
        return {
          title: title && shown(title) ? title.textContent?.trim() : "",
          titleFits: titleBox
            ? titleBox.width > 0 && titleBox.left >= 0 && titleBox.right <= window.innerWidth
            : false,
          covering,
          deskOnly,
          overflow: document.documentElement.scrollWidth - window.innerWidth,
        };
      });
      expect(bar.title, "título visível").toBeTruthy();
      expect(bar.titleFits, "título dentro da largura").toBe(true);
      expect(bar.covering, "nada por cima do título").toEqual([]);
      expect(bar.deskOnly, "nenhum controle da mesa visível").toEqual([]);
      expect(bar.overflow, "sem rolagem horizontal").toBeLessThanOrEqual(0);
    });
  }

  test('a Fila nasce com o ⋯ do celular e a linha "Filtros"', async ({ page }) => {
    await page.goto("/", { waitUntil: "load" });
    await expect(page.locator("[data-page-header-more]")).toBeVisible();
    await expect(page.locator("[data-page-header-filter-line]")).toBeVisible();
    await expect(page.locator("[data-page-header-filters-open]")).toBeVisible();
  });

  test("o pedido nasce com o título curto, o ⋯ do polegar e a ação na base", async ({ page }) => {
    await page.goto("/IFOOD-261006-W01", { waitUntil: "load" });
    await expect(page.locator("[data-page-header-phone-title]")).toBeVisible();
    await expect(page.locator("[data-action='menu-phone']")).toBeVisible();
    await expect(page.locator("[data-detail-thumb]")).toBeVisible();
  });
});
