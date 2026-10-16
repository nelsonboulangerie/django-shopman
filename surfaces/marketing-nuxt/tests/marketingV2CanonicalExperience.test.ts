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
  const campaigns = read("../app/pages/settings/campaigns.vue");
  const templates = read("../app/pages/settings/templates.vue");
  const platforms = read("../app/pages/settings/platforms.vue");
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
    // O corpo rola pelo tema do NuxtModal: com `scrollable` desligado (o padrão) o
    // slot `body` recebe `overflow-y-auto` e o cabeçalho com o fechar fica parado.
    // Para isso o conteúdo tem de ir no `#body` e o modal não pode ligar `scrollable`
    // nem trocar as classes do corpo por `:ui`.
    const template = workspaceDialog.slice(workspaceDialog.indexOf("<template>"));
    expect(template).toMatch(/<NuxtModal[\s\S]*<template #body>[\s\S]*<slot \/>/);
    expect(template).not.toMatch(/\bscrollable\b/);
    expect(template).not.toMatch(/:ui=/);
  });

  it("faz Plataformas voltar sempre à própria rota (o panorama V2 saiu)", () => {
    expect(platforms).toContain('path: "/settings/platforms"');
    expect(platforms).toContain("closePlatformWorkspace");
    expect(platforms).toContain(':data-marketing-platform="platform.platform"');
    expect(platforms).not.toContain("/v2");
    expect(campaignForm).toContain("path: '/settings/platforms'");
    expect(campaignForm).not.toContain("'/v2'");
  });
});
