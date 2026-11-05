import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { OperatorSection } from "../../operator-kit/app/presentation/appBar";
import { quickBarLayout, quickBarProblems } from "../../operator-kit/app/presentation/suiteChrome";
import {
  MARKETING_FLOOR_SECTIONS,
  MARKETING_SETTINGS_SECTIONS,
  marketingSwitcherSections,
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
    // As quatro da barra lateral, e a do chão no trocador.
    expect(source.match(/quick: true/g)).toHaveLength(5);
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

// O modelo de navegação (dono, 31/10/2026; implementar autorizado em 02/11): o selo abre
// o trocador, a forma decide a barra de baixo e nunca vira palavra na tela. Seção vai
// para baixo; o atalho existe sempre e não se renumera (dono, 03/11/2026).
describe("trocador e barra de baixo do Marketing", () => {
  // As seções da barra lateral, como o composable as monta (o selo de Decisões vem da fila).
  const rail: OperatorSection[] = [
    { key: "decisions", label: "Decisões", icon: "lucide:inbox", to: "/", match: ["/announcements", "/second-control"], quick: true, badge: "2" },
    { key: "scheduled", label: "Agendados", icon: "lucide:calendar-clock", to: "/scheduled", quick: true },
    { key: "sent", label: "Enviados", icon: "lucide:send", to: "/history", quick: true },
    { key: "settings", label: "Ajustes", icon: "lucide:settings-2", to: "/settings", match: ["/settings"], foot: true, quick: true },
  ];
  const all = () => marketingSwitcherSections(rail);

  it("lista a operação e o que mora em Ajustes, na ordem do app, sem o item Ajustes", () => {
    expect(all().map((s) => `${s.key}:${s.form}`)).toEqual([
      "decisions:floor",
      "scheduled:floor",
      "sent:floor",
      "campaigns:office",
      "templates:office",
      "offers:office",
      "platforms:office",
    ]);
    expect(all().map((s) => s.to)).toEqual([
      "/",
      "/scheduled",
      "/history",
      "/settings/campaigns",
      "/settings/templates",
      "/settings/offers",
      "/settings/platforms",
    ]);
  });

  it("o chão vai para a barra de baixo: Decisões, Agendados e Enviados, sem Mais", () => {
    const floor = all().filter((s) => s.form === "floor");
    expect(floor.map((s) => s.key)).toEqual([...MARKETING_FLOOR_SECTIONS]);
    expect(quickBarProblems(floor)).toEqual([]);
    const layout = quickBarLayout(floor);
    expect(layout.items.map((s) => s.label)).toEqual(["Decisões", "Agendados", "Enviados"]);
    expect(layout.more).toBe(false);
    expect(all().filter((s) => s.quick).map((s) => s.key)).toEqual(["decisions", "scheduled", "sent"]);
  });

  it("Decisões leva o selo da fila e acende na revisão e na segunda confirmação", () => {
    const decisions = all().find((s) => s.key === "decisions")!;
    expect(decisions.badge).toBe("2");
    expect(decisions.match).toEqual(["/announcements", "/second-control"]);
  });

  it("nenhum rótulo diz a forma da tela, e nenhum tem travessão", () => {
    for (const section of all()) {
      expect(section.label).not.toMatch(/ch[aã]o|escrit[oó]rio|parede|no posto|na parede/i);
      expect(section.label).not.toMatch(/[—–]/);
    }
  });

  it("as teclas Alt+N da barra lateral não mudam: a barra lateral segue a mesma", () => {
    const source = read("../app/composables/useMarketingSections.ts");
    expect(source).not.toMatch(/shortcut:/);
  });

  it("o shell liga o trocador, a barra de baixo do chão e a forma de escritório para Ajustes", () => {
    const shell = read("../app/app.vue");
    expect(shell).toContain(':switcher-sections="switcherSections"');
    expect(shell).toContain('default-form="office"');
    expect(shell).toContain("floor-bar");
    // Sem `current`: o trocador acende a sub-seção de Ajustes pelo caminho.
    expect(shell).not.toContain(":current=");
  });

  it("as telas do chão usam a linha do chão, com a conexão no ponto do selo", () => {
    for (const file of [
      "../app/components/MarketingDecisionQueue.vue",
      "../app/pages/scheduled.vue",
      "../app/pages/history.vue",
    ]) {
      const page = read(file);
      expect(page, file).toContain("data-compact-page");
      expect(page, file).toContain("<OperatorCompactBar");
      expect(page, file).toContain(':tone="live.tone"');
      expect(page, file).toContain(':conn-label="live.label"');
      // O "Ao vivo" da tela fica só na mesa (o kit esconde o cabeçalho no celular).
      expect(page, file).not.toContain("segunda linha");
    }
  });
});
