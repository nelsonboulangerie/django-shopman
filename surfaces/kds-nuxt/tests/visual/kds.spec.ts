import { expect, test, type Page } from "@playwright/test";

import { expectOperatorLabelsFit } from "../../../operator-kit/visual/playwright";

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

// A mesma porta do mock que o `playwright.visual.config.ts` sobe.
const BACKEND_PORT = Number(process.env.KDS_VISUAL_BACKEND_PORT || 38797);

const VIEWPORTS = [
  { id: "390", width: 390, height: 844, touch: true },
  { id: "1280", width: 1280, height: 800, touch: false },
] as const;
const THEMES = ["light", "dark"] as const;
const ROUTES = [
  { id: "estacoes", path: "/", heading: "Estações" },
  { id: "bancada", path: "/bancada", heading: "Bancada" },
  // A mudança com alarde (dono, 10/10/2026): a estação `cafes` da prévia tem item
  // cancelado, quantidade e observação novas, comanda que virou pedido e um pedido que
  // caiu inteiro.
  { id: "alarde", path: "/cafes", heading: "Cafés" },
  { id: "pickup", path: "/pickup", heading: "" },
] as const;

/** As caixas dos tickets da grade, lidas só quando a grade parou de mexer (a entrada
 *  e a troca de linha animam, e o aviso que chega depois empurra a grade). */
async function settledBoxes(page: Page) {
  const read = () =>
    page.locator("[data-kds-grid] article").evaluateAll((nodes) =>
      nodes.map((node, index) => {
        const rect = node.getBoundingClientRect();
        return {
          index,
          top: Math.round(rect.top),
          left: Math.round(rect.left),
          bottom: Math.round(rect.bottom),
          height: Math.round(rect.height),
        };
      }),
    );
  let previous = await read();
  for (let attempt = 0; attempt < 20; attempt++) {
    await page.waitForTimeout(150);
    const current = await read();
    if (JSON.stringify(current) === JSON.stringify(previous)) return current;
    previous = current;
  }
  return previous;
}

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
      test.beforeEach(async ({ page, request }) => {
        // O quadro da prévia volta ao começo: a ciência dada num caso não apaga o
        // alarme da captura seguinte.
        await request.post(`http://127.0.0.1:${BACKEND_PORT}/__preview/reset`);
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
          // O rótulo que cabe (dono, 10/10/2026): nenhum texto de botão vaza ou corta.
          await expectOperatorLabelsFit(page, `${route.id} ${viewport.id} ${theme}`);
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
          const boxes = await settledBoxes(page);
          const reading = [...boxes].sort((a, b) => a.top - b.top || a.left - b.left).map((box) => box.index);
          expect(reading).toEqual(boxes.map((box) => box.index));
          const grid = page.locator("[data-kds-grid]");
          expect(await grid.evaluate((node) => getComputedStyle(node).gridAutoFlow)).not.toContain("dense");
          await expect(cards.nth(0)).toContainText("Agora");
          await expect(cards.nth(1)).toContainText("Próximo");
        });

        test("bancada: cada ticket tem a altura do próprio conteúdo, e as linhas se alinham pelo topo", async ({ page }) => {
          // Dono, 09/10/2026: o ticket não estica até o pé da linha; a linha seguinte
          // começa abaixo do mais alto da linha de cima.
          await page.goto("/bancada");
          await page.getByRole("button", { name: /Ver a fila inteira/ }).click();
          const cards = page.locator("[data-kds-grid] article");
          await expect(cards.nth(3)).toBeVisible();
          const boxes = await settledBoxes(page);
          const rows = new Map<number, typeof boxes>();
          for (const box of boxes) rows.set(box.top, [...(rows.get(box.top) ?? []), box]);
          const ordered = [...rows.entries()].sort(([a], [b]) => a - b).map(([, row]) => row);
          expect(ordered.length).toBeGreaterThan(1);
          // A primeira linha tem tickets de alturas diferentes: nenhum foi esticado.
          expect(new Set(ordered[0]!.map((box) => box.height)).size).toBeGreaterThan(1);
          for (let index = 1; index < ordered.length; index++) {
            const tallestAbove = Math.max(...ordered[index - 1]!.map((box) => box.bottom));
            for (const box of ordered[index]!) expect(box.top).toBeGreaterThanOrEqual(tallestAbove);
          }
        });

        test("alarde: o que mudou vem antes da fila, vermelho, e só sai com a ciência", async ({ page }) => {
          await page.goto("/cafes");
          const cards = page.locator("[data-kds-grid] article");
          await expect(cards.first()).toBeVisible();
          // O pedido que caiu inteiro não some: é o primeiro card, riscado, "Não preparar".
          await expect(cards.nth(0)).toContainText("Pedido cancelado às 08:22. Não preparar.");
          await expect(cards.nth(0).locator("ul")).toHaveCSS("text-decoration-line", "line-through");
          await expect(cards.nth(1)).toContainText("Cancelado: 1× Pão de queijo");
          await expect(cards.nth(1).locator("[data-kds-action]")).toHaveText("Recebi o cancelamento");
          await expect(page.getByText("Pão de queijo: agora 1, eram 3")).toBeVisible();
          await expect(page.getByText("Era a comanda Mesa 5")).toBeVisible();
          // O trabalho que não mudou segue com a posição na fila e o ato de sempre.
          await expect(cards.nth(4)).toContainText("Agora");
          await expect(cards.nth(4).locator("[data-kds-action]")).toHaveText("Iniciar preparo");
          // A ciência no card: a caixa vermelha some e o card vira trabalho de novo.
          const moved = cards.filter({ hasText: "Era a comanda Mesa 5" });
          await moved.locator("[data-kds-action]").click();
          await expect(page.getByText("Era a comanda Mesa 5")).toHaveCount(0);
          await expect(page.locator("[data-kds-grid] article", { hasText: "Croque monsieur" }).last()).toContainText(
            "Iniciar preparo",
          );
        });
      } else {
        test("alarde: no celular o card que mudou vem ao foco e a base é a ciência", async ({ page }) => {
          await page.goto("/cafes");
          await expect(page.locator("[data-operator-action-bar-action]")).toContainText("Recebi o cancelamento");
          await expect(page.locator("[data-kds-phone-queue] [data-kds-changes]").first()).toContainText(
            "Pedido cancelado às 08:22",
          );
          await expect(page.locator("[data-kds-queue-alarm]").first()).toContainText(/Mudou|Cancelado/);
        });

        test("bancada: o ato do pedido em foco está na base, e a grade da mesa não aparece", async ({ page }) => {
          await page.goto("/bancada");
          await expect(page.locator("[data-operator-action-bar-action]")).toContainText(/Pronto|Iniciar/);
          await expect(page.locator("[data-kds-grid]")).toBeHidden();
          await expect(page.locator("[data-kds-phone-queue]")).toBeVisible();
        });

        test("bancada: no Pronto a barra fica a mesma, e só o botão vira Desfazer", async ({ page }) => {
          // Dono, 09/10/2026: a barra de ação não some nem se troca no estado de prazo.
          await page.goto("/bancada");
          const action = page.locator("[data-operator-action-bar-action]");
          await expect(action).toContainText(/Pronto \d+/);
          const label = (await action.innerText()).trim();
          const code = label.replace(/^Pronto\s+/, "");
          await action.click();
          await expect(action).toContainText(`Desfazer ${code}`);
          await expect(page.locator("[data-operator-action-bar]")).toBeVisible();
          await expect(page.locator("[data-kds-phone-queue] [data-kds-action]")).toHaveCount(0);
          // Desfazer dentro da janela: o Pronto volta e nada sai para o servidor.
          await action.click();
          await expect(action).toContainText(label);
        });
      }
    });
  }
}
