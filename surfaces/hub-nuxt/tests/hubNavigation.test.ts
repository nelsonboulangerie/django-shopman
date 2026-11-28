import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  quickBarLayout,
  quickBarProblems,
  withSectionShortcuts,
} from "../../operator-kit/app/presentation/suiteChrome";
import { HUB_SECTIONS } from "../app/presentation/hub";

// O modelo de navegação na Central (aprovado 31/10/2026, implementado app a app desde
// 02/11): o que se aplica a ela. A Central é a tela inicial e não tem trocador (o shell é
// `home`), tem uma seção só e, no celular, ganha a linha do chão.
const app = readFileSync(new URL("../app/app.vue", import.meta.url), "utf8");

describe("Central: seções", () => {
  it("uma seção só, Início, com o atalho Alt+1", () => {
    expect(HUB_SECTIONS.map((section) => section.key)).toEqual(["home"]);
    expect(withSectionShortcuts(HUB_SECTIONS)[0]?.shortcut).toBeTruthy();
  });

  it("sem barra de baixo: uma vaga só não aparece, e isso está dentro da regra do kit", () => {
    expect(quickBarLayout(HUB_SECTIONS).shown).toBe(false);
    expect(quickBarProblems(HUB_SECTIONS)).toEqual([]);
  });

  it("nenhum nome de forma chega ao operador", () => {
    for (const section of HUB_SECTIONS) {
      expect(section.label).not.toMatch(/chão|escritório|parede|No posto|Na parede/i);
    }
  });

  it("o shell segue sem trocador (trocar de app não passa pela Central)", () => {
    expect(app).toMatch(/<OperatorSuiteShell[^>]*\n\s*home\b/);
    expect(app).not.toContain(":switcher-sections");
  });
});

describe("Central no celular: a linha do chão", () => {
  it("a página se declara compacta e põe a linha antes do cabeçalho", () => {
    expect(app).toContain("data-compact-page");
    const bar = app.indexOf("<OperatorCompactBar");
    const header = app.indexOf("<OperatorPageHeader");
    expect(bar).toBeGreaterThan(-1);
    expect(bar).toBeLessThan(header);
  });

  it("a leitura vira o ponto do selo, e o ⋮ é o mesmo da mesa", () => {
    const bar = app.slice(app.indexOf("<OperatorCompactBar"), app.indexOf("<OperatorPageHeader"));
    expect(bar).toContain(':tone="compactTone"');
    expect(bar).toContain(':time="readClock"');
    expect(bar).toContain(':conn-label="HUB_REFRESH_LABEL"');
    expect(bar).toContain(':options="headerActions"');
  });

  it("o selo diz só Central, e a saudação é o <h1> da página, só no celular (dono, 04/11)", () => {
    const bar = app.slice(app.indexOf("<OperatorCompactBar"), app.indexOf("<OperatorPageHeader"));
    expect(bar).toContain("seal-app-as-title");
    const greeting = app.indexOf("data-hub-phone-greeting");
    const apps = app.indexOf('id="hub-apps-title"');
    expect(greeting).toBeGreaterThan(-1);
    expect(greeting).toBeLessThan(apps);
    const tag = app.slice(app.lastIndexOf("<h1", greeting), greeting);
    expect(tag).toContain("md:hidden");
  });

  it("aviso de tela só pela prop `alerts` do cabeçalho, nunca NuxtAlert solto", () => {
    expect(app).not.toContain("<NuxtAlert");
    expect(app).toContain(':alerts="alerts"');
  });
});
