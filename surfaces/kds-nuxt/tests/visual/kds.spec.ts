import { expect, test, type Page } from "@playwright/test";

// Matriz da Cozinha (fase 2): as três telas na carga direta, a 390 (celular de toque)
// e a 1280 (mesa), nos dois temas. Cada caso confere que a tela abre sem erro de
// página e sem aviso de hidratação, e anexa a captura ao relatório. Sem
// `toHaveScreenshot`: retrato só se grava com o browser da CI.
//
// Duas travas de desenho moram aqui, porque só o navegador mede posição:
//   - a ORDEM DE ATAQUE (dono, 09/10/2026): na mesa a ordem visual dos tickets (de
//     cima para baixo, da esquerda para a direita) é a ordem da fila, e a posição está
//     escrita no ticket (Agora, Próximo, Depois);
//   - no celular o ato do ticket em foco está na ação na base ("Pronto …"), e o
//     quadro da mesa não aparece nem antes de hidratar.

const VIEWPORTS = [
  { id: "390", width: 390, height: 844, touch: true },
  { id: "1280", width: 1280, height: 800, touch: false },
] as const;
const THEMES = ["light", "dark"] as const;
const ROUTES = [
  { id: "estacoes", path: "/", heading: "Estações" },
  { id: "bancada", path: "/bancada", heading: "Bancada" },
  { id: "pickup", path: "/pickup", heading: "" },
] as const;

async function watchProblems(page: Page): Promise<string[]> {
  const problems: string[] = [];
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (/hydrat|mismatch/i.test(message.text())) problems.push(`console: ${message.text()}`);
  });
  return problems;
}

for (const viewport of VIEWPORTS) {
  for (const theme of THEMES) {
    test.describe(`${viewport.id} ${theme}`, () => {
      test.use({
        viewport: { width: viewport.width, height: viewport.height },
        hasTouch: viewport.touch,
        isMobile: viewport.touch,
        colorScheme: theme,
      });
      test.beforeEach(async ({ page }) => {
        await page.addInitScript((value) => {
          try {
            localStorage.setItem("kds-nuxt-color-mode", value);
          } catch {
            /* sem storage, segue o padrão */
          }
        }, theme);
        await page.clock.setFixedTime(new Date("2026-10-09T08:30:00-03:00"));
      });

      for (const route of ROUTES) {
        test(`${route.id} abre sem erro e sem aviso de hidratação`, async ({ page }, testInfo) => {
          const problems = await watchProblems(page);
          const response = await page.goto(route.path);
          expect(response?.status()).toBeLessThan(500);
          if (route.heading) await expect(page.getByRole("heading", { name: route.heading }).first()).toBeVisible();
          await page.waitForLoadState("networkidle");
          await testInfo.attach(`${route.id}-${viewport.id}-${theme}`, {
            body: await page.screenshot(),
            contentType: "image/png",
          });
          expect(problems).toEqual([]);
        });
      }

      if (viewport.id === "1280") {
        test("bancada: a ordem visual dos tickets é a ordem da fila", async ({ page }) => {
          await page.goto("/bancada");
          const cards = page.locator("[data-kds-grid] article");
          await expect(cards.first()).toBeVisible();
          const boxes = await cards.evaluateAll((nodes) =>
            nodes.map((node, index) => {
              const rect = node.getBoundingClientRect();
              return { index, top: Math.round(rect.top), left: Math.round(rect.left) };
            }),
          );
          const reading = [...boxes].sort((a, b) => a.top - b.top || a.left - b.left).map((box) => box.index);
          expect(reading).toEqual(boxes.map((box) => box.index));
          const grid = page.locator("[data-kds-grid]");
          expect(await grid.evaluate((node) => getComputedStyle(node).gridAutoFlow)).not.toContain("dense");
          await expect(cards.nth(0)).toContainText("Agora");
          await expect(cards.nth(1)).toContainText("Próximo");
        });
      } else {
        test("bancada: o ato do pedido em foco está na base, e a grade da mesa não aparece", async ({ page }) => {
          await page.goto("/bancada");
          await expect(page.locator("[data-operator-action-bar-action]")).toContainText(/Pronto|Iniciar/);
          await expect(page.locator("[data-kds-grid]")).toBeHidden();
          await expect(page.locator("[data-kds-phone-queue]")).toBeVisible();
        });
      }
    });
  }
}
