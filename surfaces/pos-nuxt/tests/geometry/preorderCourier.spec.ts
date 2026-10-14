import { expect, test, type Page } from "@playwright/test";

import { OPERATOR_LABEL_FINDINGS, scanOperatorGeometry } from "../../../operator-kit/visual/scanner";

// O ENTREGADOR (TaOn) no PDV (dono, 13/10/2026): o estado da corrida na lista das
// Encomendas e o painel "Entregador" no painel do Balcão, nas três larguras da
// entrega (1366 e 1280 na mesa, 390 no celular), claro e escuro. O que se prova é a
// geometria: nenhum rótulo corta ou vaza, nada se sobrepõe, a página não rola para o
// lado e o painel do entregador não passa da borda do painel do Balcão. Backend
// hermético (`MOCK_SCENARIO=sale`: um cartão por estado da corrida).
const SIZES = [
  { width: 1366, height: 768 },
  { width: 1280, height: 720 },
  { width: 390, height: 844 },
] as const;

async function open(page: Page, path: string, size: { width: number; height: number }, scheme: "light" | "dark") {
  await page.setViewportSize(size);
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: scheme });
  await page.addInitScript((mode) => window.localStorage.setItem("pos-nuxt-color-mode", mode), scheme);
  await page.goto(path);
  await page.evaluate(() => document.fonts.ready);
}

async function fitsInside(page: Page, frameSelector: string): Promise<string[]> {
  return page.locator(frameSelector).evaluate((frame) => {
    const box = frame.getBoundingClientRect();
    return [...frame.querySelectorAll<HTMLElement>("*")]
      .filter((el) => {
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && (rect.left < box.left - 1 || rect.right > box.right + 1);
      })
      .map((el) => `${el.tagName.toLowerCase()} ${el.textContent?.trim().slice(0, 40) ?? ""}`);
  });
}

for (const scheme of ["light", "dark"] as const) {
  for (const size of SIZES) {
    test(`lista com a corrida em ${size.width}x${size.height} (${scheme})`, async ({ page }) => {
      await open(page, "/preorders?mode=day", size, scheme);
      const line = page.locator("[data-preorder-courier]:visible").first();
      // A primeira tela paga a compilação do `nuxt dev` a frio.
      await expect(line).toBeVisible({ timeout: 90_000 });
      await expect(page.locator("[data-preorder-courier]:visible", { hasText: "Entregador não chamado" }).first()).toBeVisible();
      await expect(page.locator("[data-preorder-courier]:visible", { hasText: "Não atendida" }).first()).toBeVisible();
      const findings = await scanOperatorGeometry(page, { only: ["horizontal-overflow", ...OPERATOR_LABEL_FINDINGS] });
      expect(findings).toEqual([]);
    });

    for (const ref of ["NB-1051", "NB-1052", "NB-1053", "NB-1054", "NB-1056", "NB-1057"]) {
      test(`painel do entregador ${ref} em ${size.width}x${size.height} (${scheme})`, async ({ page }) => {
        await open(page, `/preorders/${ref}`, size, scheme);
        const panel = page.locator("[data-pos-courier]");
        await expect(panel).toBeVisible({ timeout: 90_000 });
        const call = page.locator("[data-pos-courier-call]");
        if (await call.count()) {
          await call.click();
          await expect(page.locator("[data-pos-courier-confirm]")).toBeVisible();
          await expect(page.locator("[data-pos-courier-question]")).toContainText("A corrida é cobrada da casa.");
        }
        // Cancelar a corrida armado (o segundo toque) e a conferência do Entregador
        // voltou abertos: os estados mais largos do painel (dono, P=1, 14/10).
        const cancel = page.locator("[data-pos-courier-cancel]");
        if (await cancel.count()) {
          await cancel.click();
          await expect(cancel).toHaveText("Confirmar o cancelamento?");
        }
        const returned = page.locator("[data-pos-courier-returned]");
        if (await returned.count()) {
          await returned.click();
          await expect(page.locator("[data-pos-courier-back-lines] li")).toHaveCount(2);
        }
        await expect(page.locator("[data-pos-courier-gestor]")).toHaveCount(0);
        const findings = await scanOperatorGeometry(page, { only: ["horizontal-overflow", ...OPERATOR_LABEL_FINDINGS] });
        expect(findings).toEqual([]);
        expect(await fitsInside(page, "[data-preorder-counter-panel]")).toEqual([]);
        // Peças irmãs: Confirmar chamada e Voltar têm a MESMA altura.
        if (await page.locator("[data-pos-courier-confirm-actions]").count()) {
          const confirm = await page.locator("[data-pos-courier-confirm-actions] button").evaluateAll((els) =>
            [...new Set(els.map((el) => Math.round(el.getBoundingClientRect().height)))]);
          expect(confirm).toHaveLength(1);
        }
        // Conferido e Voltar: a MESMA altura.
        if (await page.locator("[data-pos-courier-back-actions]").count()) {
          const back = await page.locator("[data-pos-courier-back-actions] button").evaluateAll((els) =>
            [...new Set(els.map((el) => Math.round(el.getBoundingClientRect().height)))]);
          expect(back).toHaveLength(1);
        }
      });
    }
  }
}

test("chamar o entregador muda o estado na hora (mock: nunca a TaOn)", async ({ page }) => {
  await open(page, "/preorders/NB-1055", { width: 1366, height: 768 }, "light");
  await expect(page.locator("[data-pos-courier-state]")).toHaveText("Não atendida", { timeout: 90_000 });
  await page.locator("[data-pos-courier-call]").click();
  await page.locator("[data-pos-courier-confirm-call]").click();
  await expect(page.locator("[data-pos-courier-state]")).toHaveText("Procurando entregador");
  await expect(page.locator("[data-pos-courier-call]")).toHaveCount(0);
});

test("o andamento da TaOn: chega para coletar, entrega prevista e o aviso de sem notícias", async ({ page }) => {
  await open(page, "/preorders/NB-1053", { width: 1366, height: 768 }, "light");
  const progress = page.locator("[data-pos-courier-progress]");
  await expect(progress).toContainText(/Chega para coletar em ~\d+ min/, { timeout: 90_000 });
  await expect(progress).toContainText(/Entrega prevista ~\d{2}:\d{2}/);
  await open(page, "/preorders/NB-1057", { width: 1366, height: 768 }, "light");
  await expect(page.locator("[data-pos-courier-stale]")).toContainText("A TaOn não informa a corrida desde", { timeout: 90_000 });
});

test("cancelar a corrida antes da coleta pede o segundo toque (mock: nunca a TaOn)", async ({ page }) => {
  await open(page, "/preorders/NB-1057", { width: 1366, height: 768 }, "light");
  const cancel = page.locator("[data-pos-courier-cancel]");
  await expect(cancel).toHaveText("Cancelar a corrida", { timeout: 90_000 });
  await cancel.click();
  await cancel.click();
  await expect(page.locator("[data-pos-courier-state]")).toHaveText("Corrida cancelada");
  await expect(page.locator("[data-pos-courier-cancel]")).toHaveCount(0);
});

test("entregador voltou: confere a lista e fecha a saída (mock)", async ({ page }) => {
  await open(page, "/preorders/NB-1054", { width: 1366, height: 768 }, "light");
  await page.locator("[data-pos-courier-returned]").click({ timeout: 90_000 });
  await expect(page.locator("[data-pos-courier-back-lines]")).toContainText("Maquininha Azul");
  await page.locator("[data-pos-courier-back-done]").click();
  await expect(page.locator("[data-pos-courier-returned]")).toHaveCount(0);
});
