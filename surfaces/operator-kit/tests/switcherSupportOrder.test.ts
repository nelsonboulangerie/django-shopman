import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Prévia de 17/11/2026: no celular, o Suporte no fim do trocador (abaixo de "Outros apps"
// e de "Trocar ou bloquear") só aparecia rolando a 844 px. Ele vem logo depois das seções.
const here = dirname(fileURLToPath(import.meta.url));
const switcher = readFileSync(resolve(here, "../app/components/OperatorSwitcher.vue"), "utf8");

describe("trocador: Suporte visível sem rolar", () => {
  it("o Suporte vem antes de Outros apps e de Quem opera", () => {
    const support = switcher.indexOf("data-switcher-support");
    const otherApps = switcher.indexOf('aria-label="Outros apps"');
    const operator = switcher.indexOf('aria-label="Quem opera"');
    expect(support).toBeGreaterThan(0);
    expect(otherApps).toBeGreaterThan(support);
    expect(operator).toBeGreaterThan(support);
  });
});
