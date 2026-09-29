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
  const topBar = read("../app/components/CampaignTopBar.vue");
  const board = read("../app/components/MarketingBoard.vue");
  const shell = read("../app/app.vue");

  it("torna o workspace V2 operacional a entrada canônica", () => {
    expect(currentEntry).toContain("navigateTo(");
    expect(currentEntry).toContain('path: "/v2"');
    expect(currentEntry).toContain('area: "today"');
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
    for (const area of [
      "Hoje",
      "Campanhas",
      "Ofertas e cupons",
      "Plataformas",
    ]) {
      expect(topBar).toContain(area);
    }
    expect(topBar).toContain("activeV2Section");
    expect(topBar).not.toContain("legacySections");
    expect(workspace).not.toContain('aria-label="Áreas do Marketing V2"');
    expect(workspace).toContain("marketingV2Destinations");
    expect(workspace).toContain("Criar oferta");
    expect(workspace).toContain("Criar cupom");
    expect(workspace).toContain("useMarketingOffers()");
    expect(workspace).toContain("TikTok via Relay");
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
