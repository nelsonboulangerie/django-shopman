import { expect, test, type Page } from "@playwright/test";

import type { OperatorVisualViewport } from "../../visual/matrix";

// Trava da regra única do celular (README do kit, "Barra do topo no celular" e "Toolbar
// no celular"; dono, 08/10/2026). A bancada (`catalog/OperatorKitPhoneHeaderPage.vue`)
// tem mais ações e controles do que cabem: cinco ações da tela, a busca, Avisos, o
// posto, o estado, o período, dois recortes e o frescor. O kit decide o transbordo, e
// esta trava mede no navegador, a 320 e a 390 px:
//   - a barra do topo: ☰, o título inteiro (até 2 linhas, sem corte) e no máximo 3
//     controles à direita (2 ícones fixos + o ⋯); nenhuma caixa se cruza, nenhuma sai
//     da largura;
//   - o ⋯ guarda TODAS as ações declaradas (nenhuma se perde);
//   - a toolbar: UMA linha de altura fixa (o período e "Filtros"); o resto no painel,
//     inteiro; o recorte ativo vira chip removível;
//   - nada rola a página na horizontal.
// Sem captura de baseline: só geometria e função.

const ROUTE = "/__operator_kit_catalog/phone-header";
const PHONES = new Set(["mobile-standard", "mobile-narrow"]);

async function headerGeometry(page: Page) {
  return page.evaluate(() => {
    const header = document.querySelector("[data-operator-page-header]")!;
    const visible = (element: Element) => {
      const box = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return box.width > 1 && box.height > 1 && style.visibility !== "hidden" && style.display !== "none";
    };
    const controls = [...header.querySelectorAll("button, a, h1, [data-operator-live-status], [data-page-header-eyebrow-phone]")]
      .filter(visible)
      .filter((element, _, all) => !all.some((other) => other !== element && element.contains(other)));
    const name = (element: Element) =>
      (element.getAttribute("aria-label") || element.textContent || element.tagName).trim().replace(/\s+/g, " ");
    const overlaps: string[] = [];
    for (let i = 0; i < controls.length; i += 1) {
      for (let j = i + 1; j < controls.length; j += 1) {
        const a = controls[i]!.getBoundingClientRect();
        const b = controls[j]!.getBoundingClientRect();
        const x = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const y = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (x > 1 && y > 1) overlaps.push(`${name(controls[i]!)} × ${name(controls[j]!)}`);
      }
    }
    const beyond = controls
      .filter((element) => {
        const box = element.getBoundingClientRect();
        return box.right > window.innerWidth + 0.5 || box.left < -0.5;
      })
      .map(name);
    const right = header.querySelector('[data-slot="right"]')!;
    const rightControls = [...right.querySelectorAll("button, a")].filter(visible).map(name);
    const title = header.querySelector("h1")!;
    const lineHeight = Number.parseFloat(getComputedStyle(title).lineHeight) || 24;
    return {
      overlaps,
      beyond,
      rightControls,
      titleLines: Math.round(title.getBoundingClientRect().height / lineHeight),
      titleCut: title.scrollWidth > title.clientWidth + 1,
      pageScrollsSideways: document.documentElement.scrollWidth > window.innerWidth,
    };
  });
}

test("celular: a barra do topo e a toolbar seguem a regra única do kit", async ({ page }, testInfo) => {
  const viewport = testInfo.project.metadata.operatorViewport as OperatorVisualViewport | undefined;
  test.skip(!viewport || !PHONES.has(viewport.id), "A regra é do celular: roda a 320 e a 390 px.");
  await page.setViewportSize({ width: viewport!.width, height: viewport!.height });
  await page.goto(ROUTE);
  await expect(page.locator("[data-phone-header-bench]")).toBeVisible();
  // O kit lê a largura depois da montagem: espera a linha da toolbar do celular.
  await expect(page.locator("[data-page-header-filter-line]")).toBeVisible();

  const geometry = await headerGeometry(page);
  expect(geometry.overlaps).toEqual([]);
  expect(geometry.beyond).toEqual([]);
  expect(geometry.pageScrollsSideways).toBe(false);
  expect(geometry.titleCut).toBe(false);
  expect(geometry.titleLines).toBeLessThanOrEqual(2);
  // Busca, ⋯ e Avisos: 2 ícones fixos + o ⋯. As ações da tela não ficam soltas.
  expect(geometry.rightControls.length).toBeLessThanOrEqual(3);
  await expect(page.locator("[data-page-header-actions]")).toBeHidden();
  // O selo do app mora na gaveta (☰), não na barra.
  await expect(page.locator("[data-operator-page-header] [data-page-header-app]")).toBeHidden();

  // O ⋯ guarda todas as ações declaradas, na ordem.
  await page.locator("[data-page-header-more]").click();
  const menu = page.getByRole("menu");
  await expect(menu).toBeVisible();
  await expect(menu.getByRole("menuitem")).toHaveText([
    "Copiar link desta leitura",
    "Compartilhar esta leitura",
    "Exportar CSV",
    "Imprimir",
    "Trocar o tema",
  ]);
  await page.keyboard.press("Escape");

  // Toolbar: uma linha de altura fixa, com o período e "Filtros".
  const line = page.locator("[data-page-header-filter-line]");
  const lineBox = (await line.boundingBox())!;
  expect(lineBox.height).toBeLessThanOrEqual(64);
  await expect(page.locator("[data-page-header-filters]")).toHaveCount(0);
  const primary = page.locator("[data-page-header-filters-primary]");
  expect(await primary.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
  await expect(page.locator("[data-page-header-active-filters]")).toHaveCount(0);

  // "Filtros" abre o painel com os controles inteiros; escolher um canal vira chip.
  await page.locator("[data-page-header-filters-open]").click();
  const panel = page.locator("[data-page-header-filters-panel]");
  await expect(panel).toBeVisible();
  await panel.locator("[data-bench-channel]").click();
  await page.getByRole("option", { name: "Balcão" }).click();
  await page.locator("[data-page-header-filters-done]").click();
  await expect(panel).toBeHidden();
  const chip = page.locator("[data-page-header-active-filter]");
  await expect(chip).toHaveText("Canal: Balcão");
  await expect(page.locator("[data-page-header-filters-count]")).toHaveText("1");
  await chip.click();
  await expect(page.locator("[data-page-header-active-filters]")).toHaveCount(0);
});

test("aviso da tela: um inteiro, o resto em \"e mais N\", com a saída na cor do aviso", async ({ page }, testInfo) => {
  const viewport = testInfo.project.metadata.operatorViewport as OperatorVisualViewport | undefined;
  test.skip(
    !viewport || !["mobile-standard", "mobile-narrow", "desktop-common"].includes(viewport.id),
    "Celular e mesa comum bastam: o aviso é o mesmo em toda largura.",
  );
  await page.setViewportSize({ width: viewport!.width, height: viewport!.height });
  await page.goto(ROUTE);
  await expect(page.locator("[data-phone-header-bench]")).toBeVisible();
  // O botão do aviso só age depois da hidratação.
  await page.waitForFunction(() => Boolean((document.querySelector("#__nuxt") as { __vue_app__?: unknown } | null)?.__vue_app__));
  await page.waitForLoadState("networkidle");

  const alerts = page.locator("[data-page-header-alert]");
  await expect(alerts).toHaveCount(1);
  await expect(alerts.first()).toContainText("2 pedidos passaram do horário");
  // A saída do aviso: botão do tamanho da suíte, não o xs do default.
  const exit = alerts.first().getByRole("button", { name: "Ver os atrasados" });
  expect((await exit.boundingBox())!.height).toBeGreaterThanOrEqual(30);
  await exit.click();
  await expect(page.locator("[data-phone-header-bench]")).toHaveAttribute("data-chosen", /atrasados/);

  const more = page.locator("[data-page-header-alerts-more]");
  await expect(more).toHaveText("e mais 2 avisos");
  await more.click();
  await expect(alerts).toHaveCount(3);
  await expect(more).toHaveCount(0);
  // O aviso não empurra nada para fora da largura.
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
});
