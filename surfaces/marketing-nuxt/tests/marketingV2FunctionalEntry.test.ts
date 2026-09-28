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
  const board = read("../app/components/MarketingBoard.vue");
  const shell = read("../app/app.vue");

  it("compartilha o painel operacional em vez de redirecionar para a prévia", () => {
    expect(currentEntry).toContain("<MarketingBoard />");
    expect(v2Entry).toContain('<MarketingBoard experience="v2" />');
    expect(v2Entry).toContain('data-marketing-experience="v2"');
    expect(v2Entry).not.toContain("window.location");
    expect(v2Entry).not.toContain("marketing-v2-preview");
  });

  it("mantém a V2 atrás do mesmo gate de operador", () => {
    expect(shell).toContain('const OPERATOR_PERM = "shop.view_marketing"');
    expect(shell).toContain("sessionState === 'authenticated'");
    expect(shell).toContain('<component :is="Component" />');
  });

  it("preserva as decisões e comprovantes do painel atual", () => {
    expect(board).toContain("useCampaignBoard()");
    expect(board).toContain("@approve=\"onApprove\"");
    expect(board).toContain("confirmReject");
    expect(board).toContain("confirmServerDecision");
    expect(board).toContain("resumeServerDecision");
    expect(board).toContain("preserveMarketingReceipt");
    expect(board).toContain('to="/campaigns"');
    expect(board).toContain('to="/history"');
  });
});
