import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Copy da Cozinha corrigida no beta de 05/11/2026 (KDS-18): textos curtos que não
// fechavam entre telas. Lê o SFC, porque são frases fixas de template.
const app = resolve(dirname(fileURLToPath(import.meta.url)), "..", "app");
const read = (path: string) => readFileSync(resolve(app, path), "utf8");

describe("copy da Cozinha (beta 05/11, KDS-18)", () => {
  it("Ajustes diz o escopo UMA vez (a descrição não repete a linha da estação)", () => {
    const settings = read("components/KdsSettingsDialog.vue");
    expect(settings).toContain("vale para todas as telas desta estação");
    expect(settings).not.toContain("gravados para todas as telas dela");
  });

  it("o índice diz 'Estação deste dispositivo', não a frase pela metade", () => {
    const index = read("pages/index.vue");
    expect(index).toContain(">Estação deste dispositivo<");
    expect(index).not.toContain(">a deste dispositivo<");
  });
});
