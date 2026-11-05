import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OPERATOR_KIT_SURFACES } from "./support/surfaceRegistry";

// A RECUSA DE APP É UMA SÓ, E TEM SAÍDA (beta 05/11, CEN-03, CEN-04, PDV2-15, CEN-11).
//
// Cada `app.vue` copiava um `NuxtEmpty` próprio para "Seu acesso não inclui…": quatro
// sem nenhum botão, um com "Voltar à Central", três redações e um artigo errado ("o
// Compras"). O PDV nem tinha o ramo: quem não opera o caixa via "falha de conexão" e o
// servidor recebia o mesmo 403 a cada segundo. Agora a recusa é o
// `OperatorSurfaceForbidden` do kit, e o PDV decide pelo mesmo `operatorSurfaceGate`.
const surfaces = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

const GATE_OVERRIDES: Record<string, string> = {
  "pos-nuxt": "app/components/PosOperatorShell.vue",
};
/** Apps sem recusa de app: a Central lista o que cada um abre; a Cozinha é de quem preparar. */
const WITHOUT_FORBIDDEN = new Set(["hub-nuxt", "kds-nuxt"]);

describe("a recusa de app vem do kit, com saída", () => {
  for (const app of OPERATOR_KIT_SURFACES) {
    const file = GATE_OVERRIDES[app] ?? "app/app.vue";
    it(`${app} não escreve a própria recusa`, () => {
      const source = readFileSync(resolve(surfaces, app, file), "utf8");
      expect(source, `${app}: use <OperatorSurfaceForbidden>`).not.toContain("Seu acesso não inclui");
      if (WITHOUT_FORBIDDEN.has(app)) return;
      expect(source, `${app}: a recusa é a do kit`).toContain("<OperatorSurfaceForbidden");
    });
  }

  it("o PDV decide pelo mesmo portão dos outros apps", () => {
    const shell = readFileSync(resolve(surfaces, "pos-nuxt", GATE_OVERRIDES["pos-nuxt"]!), "utf8");
    expect(shell).toContain("operatorSurfaceGate(");
    expect(shell).toContain("showForbidden");
  });
});
