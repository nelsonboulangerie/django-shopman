import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

function read(relativePath: string): string {
  return readFileSync(
    fileURLToPath(new URL(relativePath, import.meta.url)),
    "utf8",
  );
}

describe("entrada funcional do Marketing V2", () => {
  const currentEntry = read("../app/pages/index.vue");
  const v2Entry = read("../app/pages/v2.vue");
  const workspace = read("../app/components/MarketingV2Workspace.vue");
  // As quatro seções e as de Ajustes moram em `useMarketingSections` (fonte única do
  // rail, da barra do polegar e da segunda linha de Ajustes).
  const topBar =
    read("../app/components/MarketingSettingsNav.vue") +
    read("../app/composables/useMarketingSections.ts");
  const board = read("../app/components/MarketingBoard.vue");
  const shell = read("../app/app.vue");

  it("faz da fila de decisões a casa e mantém o workspace V2 nos ajustes", () => {
    // Decisão do dono (03/10/2026): a casa é a fila de decisões, não um redirect.
    expect(currentEntry).toContain("<MarketingDecisionQueue />");
    expect(currentEntry).not.toContain("navigateTo(");
    expect(currentEntry).not.toContain("<MarketingBoard />");
    expect(v2Entry).toContain("<MarketingV2Workspace />");
    expect(workspace).toContain('data-marketing-experience="v2"');
    expect(workspace).toContain("useCampaignBoard()");
    expect(workspace).toContain("useCampaigns()");
    expect(workspace).toContain("usePlatforms()");
    expect(v2Entry).not.toContain("window.location");
    expect(v2Entry).not.toContain("marketing-v2-preview");
  });

  it("torna as áreas esperadas alcançáveis com gestão comercial real", () => {
    // Operação: quatro seções. Ajustes entra por um item só, com as próprias seções.
    for (const area of [
      "Decisões",
      "Agendados",
      "Enviados",
      "Ajustes",
      "Campanhas",
      "Modelos",
      "Ofertas e cupons",
      "Plataformas",
    ]) {
      expect(topBar).toContain(area);
    }
    expect(topBar).toContain('to: "/v2?area=campaigns"');
    expect(topBar).toContain('to: "/v2?area=offers"');
    expect(topBar).toContain('to: "/v2?area=platforms"');
    expect(topBar).toContain('to: "/scheduled"');
    expect(topBar).toContain('to: "/history"');
    expect(topBar).not.toContain("legacySections");
    expect(workspace).not.toContain('aria-label="Áreas do Marketing V2"');
    expect(workspace).toContain("marketingV2Destinations");
    expect(workspace).toContain("Criar oferta");
    expect(workspace).toContain("Criar cupom");
    expect(workspace).toContain("useMarketingOffers()");
    expect(workspace).toContain("providerCapabilities");
    expect(workspace).toContain("plannedDestinations");
    expect(workspace).not.toContain("Visível como direção de produto");
    expect(workspace).not.toContain("fetch(");
  });

  it("mantém a V2 atrás do mesmo gate de operador", () => {
    expect(shell).toContain('const OPERATOR_PERM = "shop.view_marketing"');
    expect(shell).toContain("sessionState === 'authenticated'");
    expect(shell).toContain('<component :is="Component" />');
  });

  it("preserva as decisões e comprovantes do painel atual", () => {
    expect(board).toContain("useCampaignBoard()");
    expect(board).toContain('@approve="onApprove"');
    expect(board).toContain("confirmReject");
    expect(board).toContain("confirmServerDecision");
    expect(board).toContain("resumeServerDecision");
    expect(board).toContain("preserveMarketingReceipt");
    expect(board).toContain('to="/campaigns"');
    expect(board).toContain('to="/history"');
  });
});
