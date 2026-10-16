import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// A tela do cliente é função do BALCÃO, e mora na barra lateral — alcançável de
// qualquer tela. Antes ela só existia no cabeçalho da antessala de caixa: fechada a
// janela sem querer no meio do turno, não havia caminho de volta de dentro da venda.
//
// Fase 2: a navegação é a do shell da suíte, montada UMA vez (`PosOperatorShell` +
// `usePosShell`). A varredura exige que a abertura more lá, pela peça compartilhada,
// e que nenhuma tela ressuscite o botão próprio.
const here = dirname(fileURLToPath(import.meta.url));
const app = (...parts: string[]) => resolve(here, "..", "app", ...parts);

const SECTIONS = readFileSync(app("presentation", "sections.ts"), "utf8");
const SHELL = readFileSync(app("composables", "usePosShell.ts"), "utf8");
const SCREENS = ["pages/index.vue", "pages/session/index.vue", "components/PosPreordersShell.vue", "components/PosSettingsShell.vue", "pages/settings/seating.vue"] as const;

describe("tela do cliente na barra lateral do PDV", () => {
  it("a seção existe só na barra lateral, e o shell a abre pela peça compartilhada", () => {
    expect(SECTIONS).toContain('label: "Tela do cliente"');
    expect(SECTIONS).toContain('key: "display"');
    expect(SHELL).toContain('key === "display"');
    // A abertura é a peça compartilhada, nunca um window.open copiado: é ela que leva
    // a sonda de versão junto.
    expect(SHELL).toContain("useCustomerDisplayWindow()");
    expect(SHELL).not.toMatch(/window\.open\(\s*["']\/display/);
  });

  it("nenhuma tela tem botão próprio para a Tela do cliente: uma ação, um lugar", () => {
    for (const screen of SCREENS) {
      const source = readFileSync(app(...screen.split("/")), "utf8");
      expect(source, screen).not.toContain("openCustomerDisplay");
      expect(source, screen).not.toContain("useCustomerDisplayWindow");
    }
  });
});
