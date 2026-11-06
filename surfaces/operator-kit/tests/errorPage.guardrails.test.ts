import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OPERATOR_KIT_SURFACES } from "./support/surfaceRegistry";

// Beta 06/11 (F11): uma rota inexistente no Gestor mostrava a página de erro
// padrão do Nuxt, em inglês. A layer agora
// tem a página de erro em português, e todo app que estende o kit a herda; quem
// precisa de copy própria (o Marketing) mantém o seu `app/error.vue`.

const kitDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const surfacesDir = resolve(kitDir, "..");
const kitErrorPage = resolve(kitDir, "app", "error.vue");

describe("página de erro dos apps de operador", () => {
  it("a layer tem a página de erro, em português", () => {
    expect(existsSync(kitErrorPage)).toBe(true);
    const source = readFileSync(kitErrorPage, "utf8");
    expect(source).toContain("Esta página não existe");
    expect(source).toContain("Voltar ao início");
    expect(source).not.toMatch(/Page not found|Go back home/);
    expect(source).not.toContain("—");
  });

  it.each(OPERATOR_KIT_SURFACES)("%s cai numa página de erro em português", (dir) => {
    const own = resolve(surfacesDir, dir, "app", "error.vue");
    const page = existsSync(own) ? own : kitErrorPage;
    const config = readFileSync(resolve(surfacesDir, dir, "nuxt.config.ts"), "utf8");
    if (!existsSync(own)) expect(config).toContain("operator-kit");
    expect(readFileSync(page, "utf8")).toContain("Esta página não existe");
  });
});
