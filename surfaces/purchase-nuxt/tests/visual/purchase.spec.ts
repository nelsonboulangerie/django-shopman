import { expect, test } from "@playwright/test";

import { captureOperatorEvidence } from "../../../operator-kit/visual/playwright";
import { selectedOperatorViewports } from "../../../operator-kit/visual/matrix";

// Matriz visual do Compras (fase 2). O mock hermético serve a sessão autorizada e o
// cadastro sintético; o cenário é trocado no backend antes de cada navegação. Roda nos
// viewports oficiais (OPERATOR_VISUAL_VIEWPORTS) e aceita OPERATOR_VISUAL_SCENARIO para
// rodar só um estado. Sem baseline de pixel: o gate é o scanner de geometria do kit
// (nada estoura a largura, nenhum alvo de toque pequeno, nenhum texto cortado).

const BACKEND = "http://127.0.0.1:" + (process.env.PURCHASE_VISUAL_BACKEND_PORT || "35021");

const SCREENS = [
  { surface: "purchase-panel", route: "/", scenario: "normal", state: "normal", ready: "[data-purchase-panel]" },
  { surface: "purchase-panel", route: "/", scenario: "error", state: "recoverable-error", ready: "[data-purchase-load-error]" },
  { surface: "purchase-buy", route: "/buy", scenario: "normal", state: "normal", ready: "[data-buy-row]" },
  { surface: "purchase-receive", route: "/receive", scenario: "normal", state: "normal", ready: "[data-receipt-key-entry]" },
  { surface: "purchase-receive", route: "/receive", scenario: "receiving", state: "dense", ready: "[data-receive]" },
  { surface: "purchase-base-materials", route: "/base/materials", scenario: "normal", state: "normal", ready: "[data-base-table]" },
  { surface: "purchase-base-materials", route: "/base/materials", scenario: "empty", state: "empty", ready: "[data-base-materials]" },
  { surface: "purchase-base-materials", route: "/base/materials/MANTEIGA-82", scenario: "normal", state: "normal", ready: "[data-material-panel]" },
  { surface: "purchase-base-suppliers", route: "/base/suppliers", scenario: "normal", state: "normal", ready: "[data-base-suppliers-table]" },
  { surface: "purchase-base-costs", route: "/base/costs", scenario: "normal", state: "normal", ready: "[data-cost-batch]" },
  { surface: "purchase-base-count", route: "/base/count", scenario: "normal", state: "normal", ready: "[data-count-table]" },
];

const selectedScenario = process.env.OPERATOR_VISUAL_SCENARIO || "";
const selectedRoute = process.env.OPERATOR_VISUAL_ROUTE || "";
const screens = SCREENS.filter(
  (item) => (!selectedScenario || item.scenario === selectedScenario) && (!selectedRoute || item.route === selectedRoute),
);

for (const viewport of selectedOperatorViewports()) {
  for (const item of screens) {
    test(`${item.surface} ${item.route} ${item.scenario} · ${viewport.id}`, async ({ page, request }, testInfo) => {
      await request.get(BACKEND + "/__visual/scenario?set=" + item.scenario);
      await page.setViewportSize({
        width: Math.round(viewport.width / (viewport.zoom || 1)),
        height: Math.round(viewport.height / (viewport.zoom || 1)),
      });
      await page.goto(item.route);
      await expect(page.locator("[data-purchase-app]")).toBeVisible();
      await expect(page.locator(item.ready).first()).toBeAttached({ timeout: 20_000 });
      await page.waitForTimeout(800);
      await captureOperatorEvidence(page, testInfo, {
        app: "purchase",
        surface: item.surface,
        route: item.route,
        scenario: item.scenario,
        state: item.state,
        theme: "light",
        viewport,
      }, {
        // Duas réguas do kit em conflito, declaradas aqui com o motivo (e no relatório da
        // onda), sem esconder o resto (estouro de largura, texto cortado, sobreposição):
        //   - touch-target: o conjunto mínimo aprovado (08/10/2026) põe botão e campo em
        //     `md` (32 px) em todo lugar, e o scanner ainda cobra 44 px no toque, inclusive
        //     no chrome do kit (☰, ⋯, Avisos);
        //   - focus-clipping: o botão de ordenar do cabeçalho da `OperatorTable` (margem
        //     negativa) e os itens da barra inferior do shell têm o anel de foco cortado
        //     pelo `overflow` da própria peça do kit.
        allowedFindings: ["touch-target", "focus-clipping"],
      });
    });
  }
}
