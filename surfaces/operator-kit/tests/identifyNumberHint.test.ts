import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

// Beta 05/11/2026 (PDV-24): no celular a trava dizia "Digite o número para escolher",
// e o número não é gesto num dispositivo sem teclado.
const source = readFileSync(fileURLToPath(new URL("../app/components/OperatorIdentify.vue", import.meta.url)), "utf8");

describe("OperatorIdentify: a escolha pelo número só onde há teclado", () => {
  it("a frase e a tecla somem com ponteiro grosso (toque)", () => {
    expect(source).toMatch(/class="hidden [^"]*pointer-fine:block" data-identify-number-hint/);
    expect(source).toContain('class="pointer-coarse:hidden"');
  });
});
