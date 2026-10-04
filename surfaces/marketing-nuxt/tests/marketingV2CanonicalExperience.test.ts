import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

function read(relativePath: string): string {
  return readFileSync(
    fileURLToPath(new URL(relativePath, import.meta.url)),
    "utf8",
  );
}

describe("experiência canônica do Marketing V2", () => {
  const campaigns = read("../app/pages/campaigns.vue");
  const templates = read("../app/pages/templates.vue");
  const platforms = read("../app/pages/platforms.vue");
  const campaignForm = read("../app/components/CampaignForm.vue");
  const workspaceDialog = read(
    "../app/components/MarketingWorkspaceDialog.vue",
  );

  it("usa workspace modal nos fluxos densos e não gavetas laterais", () => {
    for (const source of [campaigns, templates, platforms]) {
      expect(source).toContain("<MarketingWorkspaceDialog");
      expect(source).not.toContain("<UiSheet");
    }
    expect(workspaceDialog).toContain(
      "sm:max-w-[min(1280px,calc(100vw-3rem))]",
    );
    expect(workspaceDialog).toContain("h-dvh");
    expect(workspaceDialog).toContain("overflow-y-auto");
  });

  it("faz Plataformas voltar sempre à própria rota (o panorama V2 saiu)", () => {
    expect(platforms).toContain('path: "/platforms"');
    expect(platforms).toContain("closePlatformWorkspace");
    expect(platforms).toContain(':data-marketing-platform="platform.platform"');
    expect(platforms).not.toContain("/v2");
    expect(campaignForm).toContain("path: '/platforms'");
    expect(campaignForm).not.toContain("'/v2'");
  });
});
