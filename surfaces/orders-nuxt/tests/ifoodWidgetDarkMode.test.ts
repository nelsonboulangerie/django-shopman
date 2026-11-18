import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

// O iframe do widget do iFood cobre a tela inteira. Se o esquema de cor dele não
// for o mesmo da página do iFood, o navegador o pinta opaco e o Gestor some no
// modo escuro (dono, 18/11/2026).
describe("widget do iFood no modo escuro", () => {
  it("o iframe do widget fica em color-scheme normal", () => {
    const css = readFileSync(new URL("../app/assets/css/tailwind.css", import.meta.url), "utf8");
    expect(css).toMatch(/iframe\.embeddables-iframe\s*\{\s*color-scheme:\s*normal;/);
    expect(css).toContain(".embeddables-focus-wrapper iframe");
  });
});
