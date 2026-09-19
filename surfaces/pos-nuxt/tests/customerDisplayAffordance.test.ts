import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// A tela do cliente é função do BALCÃO, e mora no rail — alcançável de qualquer tela.
// Antes ela só existia no cabeçalho da antessala de caixa: fechada a janela sem
// querer no meio do turno, não havia caminho de volta de dentro da venda.
//
// Este é um teste de VARREDURA: ele exige que toda tela que monta o rail saiba
// responder ao item, e que ninguém ressuscite o botão duplicado no cabeçalho.
const here = dirname(fileURLToPath(import.meta.url));
const app = (...parts: string[]) => resolve(here, "..", "app", ...parts);

const RAIL = readFileSync(app("components", "PosFunctionRail.vue"), "utf8");
const SCREENS = ["pages/index.vue", "pages/session/index.vue"] as const;

describe("tela do cliente no rail do PDV", () => {
  it("o rail oferece o item e emite o evento próprio", () => {
    expect(RAIL).toContain('label="Tela do cliente"');
    expect(RAIL).toContain("emit('display')");
    expect(RAIL).toMatch(/display:\s*\[\];/);
  });

  it("toda tela que monta o rail responde ao item", () => {
    for (const screen of SCREENS) {
      const source = readFileSync(app(...screen.split("/")), "utf8");
      expect(source, screen).toContain("<PosFunctionRail");
      expect(source, screen).toContain('@display="openCustomerDisplay"');
      // A abertura é a peça compartilhada, nunca um window.open copiado por tela:
      // é ela que leva a sonda de versão junto.
      expect(source, screen).toContain("useCustomerDisplayWindow()");
      expect(source, screen).not.toMatch(/window\.open\(\s*["']\/display/);
    }
  });

  it("o botão do cabeçalho da antessala não volta: uma ação, um lugar", () => {
    const session = readFileSync(app("pages", "session", "index.vue"), "utf8");
    const header = session.slice(session.indexOf("<header"), session.indexOf("</header>"));
    expect(header).not.toContain("openCustomerDisplay");
  });
});
