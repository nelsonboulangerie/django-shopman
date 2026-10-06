import { expect, test } from "@playwright/test";

import { captureOperatorEvidence } from "../../../operator-kit/visual/playwright";
import { selectedOperatorViewports } from "../../../operator-kit/visual/matrix";

// Matriz do board do Gestor. O mock hermético serve a sessão autorizada e a
// projection capturada do seed; o cenário é trocado no backend antes de cada
// navegação. Roda nos viewports oficiais (OPERATOR_VISUAL_VIEWPORTS) e aceita
// OPERATOR_VISUAL_SCENARIO para rodar só um estado.
//
// A espera é pela RESPOSTA do board (não por um card): no celular o board mostra
// uma zona por vez e no vazio não há card nenhum.

const BACKEND = "http://127.0.0.1:" + (process.env.ORDERS_VISUAL_BACKEND_PORT || "38793");

const STATES = [
  { scenario: "normal", state: "normal" },
  { scenario: "empty", state: "empty" },
  { scenario: "dense", state: "dense" },
  { scenario: "error", state: "recoverable-error" },
  { scenario: "unbound-device", state: "normal" },
];

const selectedScenario = process.env.OPERATOR_VISUAL_SCENARIO || "";
const scenarios = STATES.filter((item) => !selectedScenario || item.scenario === selectedScenario);

for (const viewport of selectedOperatorViewports()) {
  // Claro E escuro são obrigatórios. O Gestor é light-first, então o dark NÃO vem
  // do `prefers-color-scheme`: a preferência vive no storage do color-mode
  // (`orders-nuxt-color-mode`) e é cravada por `addInitScript` antes do boot.
  for (const theme of ["light", "dark"] as const) {
  // O CONTEXTO precisa emular a capacidade do viewport. O envelope de toque
  // (--spacing-control: 44 no celular, 48 no tablet) vive em
  // `@media (pointer: coarse)`. Com o contexto padrão o browser reporta
  // `pointer: fine`, a regra não casa e o scanner — avisado `touch: true` pelo
  // metadata do viewport — reprova controles que o CSS nunca pôde crescer. O
  // `test.use` por viewport dá ao browser a mesma capacidade que o scanner assume.
  test.describe(viewport.id + " · " + theme, () => {
    test.use({
      viewport: {
        width: Math.round(viewport.width / (viewport.zoom || 1)),
        height: Math.round(viewport.height / (viewport.zoom || 1)),
      },
      hasTouch: viewport.touch,
      isMobile: viewport.profile === "mobile-touch",
      deviceScaleFactor: viewport.zoom || 1,
      colorScheme: theme,
    });

    for (const item of scenarios) {
      test("orders-board " + item.scenario + " · " + viewport.id, async ({ page, request }, testInfo) => {
        await request.get(BACKEND + "/__visual/scenario?set=" + item.scenario);
        await page.addInitScript((value) => {
          try {
            localStorage.setItem("orders-nuxt-color-mode", value);
          } catch {
            /* storage indisponível: o app cai no light */
          }
        }, theme);
        const boardRead = page
        .waitForResponse(
          (response) =>
            response.url().includes("/api/v1/backstage/orders/") &&
            !response.url().includes("board-layout") &&
            !response.url().includes("rail-counts") &&
            response.request().method() === "GET",
          { timeout: 15_000 },
        )
        .catch(() => null);
      await page.goto("/");
      await expect(page.locator('[data-suite="v3"]')).toBeVisible();
      await boardRead;
      await page.waitForTimeout(1200);
      if (item.scenario === "error") {
        await expect(page.locator("[data-queue-error]")).toBeVisible();
      } else if (item.scenario === "empty") {
        await expect(page.locator("[data-queue-ref]")).toHaveCount(0);
      }
      await page.evaluate(() => document.fonts.ready);
      await captureOperatorEvidence(
        page,
        testInfo,
        {
          app: "orders",
          surface: "orders-board",
          route: "/",
          scenario: item.scenario,
          state: item.state,
          theme,
          viewport,
        },
        // Sem waiver: o scanner de geometria é o gate. No toque ele reprova o
        // header de controles com 40 px e a faixa de recortes que rola na
        // horizontal — achados reais da auditoria (WP-UX-13D), não do harness.
        { allowedFindings: [] },
      );
      });
    }
  });
  }
}
