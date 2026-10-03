// UX-G3: a Saída da Cozinha aposentada manda para a coluna Saída do Gestor, já
// como posto de saída. O quiosque com o endereço antigo nunca cai em página vazia.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { EXIT_STATION_TYPE, gestorExitUrl } from "../app/presentation/exitMoved";

describe("gestorExitUrl", () => {
  it("a Saída do Gestor, só com a coluna Saída aberta", () => {
    expect(gestorExitUrl("https://gestor.boulangerie.com.br/")).toBe("https://gestor.boulangerie.com.br/?columns=expedition");
    expect(gestorExitUrl("http://127.0.0.1:3004")).toBe("http://127.0.0.1:3004/?columns=expedition");
  });

  it("sem a URL do Gestor não inventa destino", () => {
    expect(gestorExitUrl("")).toBe("");
    expect(gestorExitUrl("   ")).toBe("");
  });

  it("o tipo da estação de Saída é o do cadastro", () => {
    expect(EXIT_STATION_TYPE).toBe("expedition");
  });
});

describe("a página da estação de Saída", () => {
  const page = readFileSync(new URL("../app/pages/[ref].vue", import.meta.url), "utf8");

  it("redireciona para o Gestor e mostra o link enquanto troca de página", () => {
    expect(page).toContain("navigateTo(exitUrl, { external: true, replace: true })");
    expect(page).toContain('data-testid="exit-moved"');
    expect(page).toContain("Abrir a Saída no Gestor");
  });

  it("não desenha mais as colunas da Saída da Cozinha", () => {
    expect(page).not.toContain("KdsExpeditionCard");
    expect(page).not.toContain("KdsExitPreparingCard");
  });

  it("o Gestor lê o mesmo parâmetro que a Cozinha manda", () => {
    const layout = readFileSync(new URL("../../orders-nuxt/app/composables/useBoardLayout.ts", import.meta.url), "utf8");
    expect(layout).toContain('BOARD_COLUMNS_QUERY = "columns"');
    expect(gestorExitUrl("http://x")).toContain("columns=expedition");
  });
});
