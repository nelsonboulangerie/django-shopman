import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Contrato da casca: o app só abre para quem tem a permissão dele, e distingue
// erro de rede de sessão morta antes de pedir a senha.
const shell = readFileSync(new URL("../app/app.vue", import.meta.url), "utf8");
const config = readFileSync(new URL("../nuxt.config.ts", import.meta.url), "utf8");

describe("casca do kitchensink", () => {
  it("tranca na permissão do app", () => {
    expect(shell).toContain('const OPERATOR_PERM = "backstage.view_operator_kitchen_sink"');
    expect(shell).toContain("useOperatorLock(OPERATOR_PERM)");
  });

  it("não confunde erro de rede com sessão morta", () => {
    expect(shell).toContain("sessionUnavailable");
    expect(shell).toContain("OperatorLogin");
  });

  it("decide cada estado por uma fonte única e testável", () => {
    // A regra vive em operatorSurfaceGate (kit) e é coberta por teste unitário;
    // a casca só liga os booleanos. Isto impede voltar a `canIdentify` sozinho.
    expect(shell).toContain("operatorSurfaceGate(");
    for (const flag of [
      "surface.showPage",
      "surface.showForbidden",
      "surface.showChecking",
      "surface.showUnavailable",
      "surface.showLogin",
      "surface.showLock",
    ]) {
      expect(shell).toContain(flag);
    }
  });

  it("estende a layer e declara a identidade PWA certa", () => {
    expect(config).toContain('extends: ["../operator-kit"]');
    expect(config).toContain("ssr: true");
    expect(config).toContain("operatorSecurityHeaders: true");
    expect(config).toContain("operatorUpstreamFailFast: true");
    expect(config).toContain('process.env.NODE_ENV !== "production"');
    expect(config).toContain('app: "kitchensink"');
  });

  it("compõe o kitchen sink do kit sem copiar a implementação", () => {
    const page = readFileSync(new URL("../app/pages/index.vue", import.meta.url), "utf8");
    expect(page).toContain("<OperatorKitchenSink />");
    expect(page).not.toContain("NuxtCard");
    expect(shell).toContain("<OperatorAppRoot>");
    expect(shell).not.toContain("<OperatorRail");
  });
});
