// UX-G3: a Saída é a coluna Saída do Gestor. O índice das estações leva a estação de
// Saída direto para lá; a Cozinha não tem tela de Saída.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { EXIT_STATION_TYPE, gestorExitUrl, stationCountWord } from "../app/presentation/exitStation";

describe("gestorExitUrl", () => {
  it("a Saída do Gestor, só com a coluna Saída aberta", () => {
    expect(gestorExitUrl("https://gestor.boulangerie.com.br/")).toBe("https://gestor.boulangerie.com.br/?columns=expedition");
    expect(gestorExitUrl("http://127.0.0.1:3004")).toBe("http://127.0.0.1:3004/?columns=expedition");
  });

  it("sem a URL do Gestor não inventa destino", () => {
    expect(gestorExitUrl("")).toBe("");
    expect(gestorExitUrl("   ")).toBe("");
  });

  it("o selo do índice concorda com o número (auditoria D08: nunca \"1 ativos\")", () => {
    expect(stationCountWord("prep", 1)).toBe("ativo");
    expect(stationCountWord("prep", 3)).toBe("ativos");
    expect(stationCountWord("expedition", 1)).toBe("pronto");
    expect(stationCountWord("expedition", 2)).toBe("prontos");
  });

  it("o tipo da estação de Saída é o do cadastro", () => {
    expect(EXIT_STATION_TYPE).toBe("expedition");
  });

  it("o Gestor lê o mesmo parâmetro que o índice manda", () => {
    const layout = readFileSync(new URL("../../orders-nuxt/app/composables/useBoardLayout.ts", import.meta.url), "utf8");
    expect(layout).toContain('BOARD_COLUMNS_QUERY = "columns"');
  });
});

describe("a página da estação", () => {
  const page = readFileSync(new URL("../app/pages/[ref].vue", import.meta.url), "utf8");
  const config = readFileSync(new URL("../nuxt.config.ts", import.meta.url), "utf8");

  it("não tem Saída: sem redirect, sem página de aviso, sem colunas da Saída", () => {
    expect(page).not.toContain("navigateTo(");
    expect(page).not.toContain("exit-moved");
    expect(page).not.toContain("KdsExpeditionCard");
    expect(page).not.toContain("KdsExitPreparingCard");
  });

  it("não sobra legado da Saída nem da data de consulta no app (zero legado, V6)", () => {
    const board = readFileSync(new URL("../app/presentation/board.ts", import.meta.url), "utf8");
    const types = readFileSync(new URL("../app/types/kds.ts", import.meta.url), "utf8");
    const contract = readFileSync(new URL("../app/generated/kdsContract.ts", import.meta.url), "utf8");
    for (const source of [page, board, types, contract]) {
      expect(source).not.toMatch(/isExpedition|is_expedition|KDSExpeditionCard|KDSExitPreparing/);
      expect(source).not.toMatch(/serviceDate|service_date|available_dates|is_scheduled/);
    }
    const settings = readFileSync(new URL("../app/components/KdsSettingsDialog.vue", import.meta.url), "utf8");
    expect(settings).not.toContain("Data da estação");
  });

  it("os endereços antigos da Saída não redirecionam mais (decisão do dono, zero legado)", () => {
    expect(config).not.toContain('"/expedicao"');
    expect(config).not.toContain('"/estacao/expedicao"');
  });
});
