import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { quickBarProblems } from "../../operator-kit/app/presentation/suiteChrome";
import {
  MARKETING_SETTINGS_SECTIONS,
  marketingSectionFor,
  marketingSettingsFor,
} from "../app/composables/useMarketingSections";

function read(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

// Fase 2 (WP-FASE2-UX-OPERADOR, onda do Marketing): o Marketing mora no shell da suíte,
// o mesmo do Gestor. A barra lateral (mesa), a gaveta (☰) e a barra inferior (abaixo de
// `lg`) são do `OperatorSuiteShell`; o app só declara as seções.
describe("navegação do Marketing", () => {
  const shell = read("../app/app.vue");

  it("mora no shell da suíte, sem a barra lateral e a barra do polegar antigas", () => {
    expect(shell).toContain("<OperatorSuiteShell");
    expect(shell).toContain('storage-key="marketing"');
    expect(shell).not.toContain("<OperatorSuiteRail");
    expect(shell).not.toContain("<OperatorSectionBar");
    expect(shell).not.toContain("MarketingNav");
  });

  it("a caixa pessoal tem um dono só, no shell, em qualquer largura", () => {
    expect(shell.match(/<MarketingInboxLive \/>/g)).toHaveLength(1);
  });

  // V6-KIT: o sino é a caixa de Avisos do kit; as decisões entram nela como um resumo
  // que leva à fila (decisão do dono de 03/10/2026: o sino não repete a lista).
  it("Avisos é a caixa do kit, com as decisões como um resumo que leva à fila", () => {
    expect(shell).toContain("provideOperatorInboxAlerts");
    expect(shell).toContain('href: "/"');
  });

  it("nenhuma tela monta a barra de base à mão nem pede tela cheia", () => {
    const review = read("../app/pages/announcements/[id].vue");
    expect(review).not.toContain("fullscreen: true");
  });
});

describe("seções do Marketing", () => {
  it("Decisões acende na revisão e na segunda confirmação", () => {
    expect(marketingSectionFor("/")).toBe("decisions");
    expect(marketingSectionFor("/announcements/41")).toBe("decisions");
    expect(marketingSectionFor("/second-control/abc")).toBe("decisions");
    expect(marketingSectionFor("/scheduled")).toBe("scheduled");
    expect(marketingSectionFor("/history")).toBe("sent");
  });

  it("Ajustes tem rota própria e cada sub-seção mora embaixo dela, em inglês", () => {
    expect(marketingSectionFor("/settings")).toBe("settings");
    expect(MARKETING_SETTINGS_SECTIONS.map((section) => section.to)).toEqual([
      "/settings/campaigns",
      "/settings/templates",
      "/settings/offers",
      "/settings/platforms",
    ]);
    for (const section of MARKETING_SETTINGS_SECTIONS) {
      expect(marketingSectionFor(section.to)).toBe("settings");
      expect(marketingSettingsFor(section.to)).toBe(section.key);
      expect(section.description).not.toMatch(/[—–]/);
    }
    expect(marketingSettingsFor("/settings")).toBeNull();
  });

  it("a barra inferior segue a regra do kit (3 a 5 vagas)", () => {
    const quick = [
      { key: "decisions", label: "Decisões", icon: "lucide:inbox", to: "/", quick: true },
      { key: "scheduled", label: "Agendados", icon: "lucide:calendar-clock", to: "/scheduled", quick: true },
      { key: "sent", label: "Enviados", icon: "lucide:send", to: "/history", quick: true },
      { key: "settings", label: "Ajustes", icon: "lucide:settings-2", to: "/settings", foot: true, quick: true },
    ];
    expect(quickBarProblems(quick)).toEqual([]);
    const source = read("../app/composables/useMarketingSections.ts");
    expect(source.match(/quick: true/g)).toHaveLength(4);
  });

  it("a faixa de Ajustes é o OperatorQuickFilters do kit no modo de rota", () => {
    const nav = read("../app/components/MarketingSettingsNav.vue");
    expect(nav).toContain("<OperatorQuickFilters");
    expect(nav).toContain("to: section.to");
    // Quatro opções: no celular, lista (seção 11: mais de 3 vira `NuxtSelect`), pela
    // régua do kit, sem teto avulso na tela.
    expect(nav).not.toContain("phone-max");
    expect(nav).not.toContain("<NuxtTabs");
    expect(nav).not.toContain("useMediaQuery");
  });
});
