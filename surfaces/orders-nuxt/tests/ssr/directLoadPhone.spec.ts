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
      await expect(page.locator("[data-page-header-filters-open]")).toBeVisible();
    });
  }

  test("/history tem o período na linha", async ({ page }) => {
    await openDirect(page, "/history");
    await expect(page.getByRole("button", { name: /Hoje/ })).toBeVisible();
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
