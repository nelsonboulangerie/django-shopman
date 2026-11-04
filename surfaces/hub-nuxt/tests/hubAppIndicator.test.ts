import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { serverClockOffset, tileAriaLabel, tileAttentionCount } from "../app/presentation/hub";
import type { HubTileProjection } from "../app/types/hub";

// A lista de apps simples (dono, 04/11/2026: "Simplifique! Só algum indicador mais
// simples"): cada app é o ícone e o nome, e no máximo UM indicador, o número no canto
// superior direito do ícone, só quando algo pede alguém. O detalhe mora dentro do app.

const tile = (over: Partial<HubTileProjection> = {}): HubTileProjection => ({
  ref: "gestor",
  label: "Gestor de Pedidos",
  description: "Fila e acompanhamento",
  icon: "square-kanban",
  url: "https://gestor.example.test/",
  kind: "launch",
  status_attention: "",
  attention_count: 0,
  status_summary: "",
  status_positive: "",
  next_item: null,
  ...over,
});

const app = readFileSync(new URL("../app/app.vue", import.meta.url), "utf8");
const template = app.slice(app.indexOf("<template>"));

describe("o indicador do app", () => {
  it("é o número do que pede alguém; em dia, nada", () => {
    expect(tileAttentionCount(tile({ attention_count: 3 }))).toBe(3);
    expect(tileAttentionCount(tile())).toBe(0);
    expect(tileAttentionCount(tile({ attention_count: -1 }))).toBe(0);
  });

  it("tem nome falado: o app e o que o número conta, por extenso", () => {
    expect(tileAriaLabel(tile({ status_attention: "1 para aceitar", attention_count: 1 }))).toBe(
      "Gestor de Pedidos, 1 para aceitar",
    );
    expect(tileAriaLabel(tile({ status_attention: "1 para aceitar · 2 avisos", attention_count: 3 }))).toBe(
      "Gestor de Pedidos, 1 para aceitar, 2 avisos",
    );
    // Em dia, só o nome: o estado calmo ("11 ativos") mora dentro do app.
    expect(tileAriaLabel(tile({ status_summary: "11 ativos", status_positive: "Caixa aberto" }))).toBe("Gestor de Pedidos");
    expect(tileAriaLabel(tile({ label: "Loja online", kind: "external" }))).toBe("Loja online. Abre em outra janela");
  });

  it("conta pela hora do servidor: o relógio errado do dispositivo não muda o dia", () => {
    const now = Date.parse("2026-10-03T10:00:00-03:00");
    expect(serverClockOffset(new Date(now).toISOString(), now - 90_000)).toBe(90_000);
    expect(serverClockOffset("", now)).toBe(0);
  });
});

describe("a grade de apps", () => {
  it("um desenho só para toda largura: ícone, nome e o chip no canto do ícone", () => {
    expect(template.match(/data-hub-apps\b/g)?.length).toBe(1);
    expect(template).toContain("<NuxtChip");
    expect(template).toContain('position="top-right"');
    expect(template).toContain("countChipProps(");
  });

  it("nada do que saiu volta: linha de estado, ponto, pendência, contador de apps, nota", () => {
    expect(template).not.toMatch(/data-tile-status|data-tile-tone|data-hub-app-next|next_item|status_summary/);
    expect(template).not.toContain("<OperatorCountChip");
    expect(template).not.toContain("<NuxtPageCard");
    expect(app).not.toContain("APPS_HINT_COPY");
  });

  it("a ordem é a do registro: o ícone não troca de lugar quando a pendência muda", () => {
    expect(template).toMatch(/v-for="tile in tiles"/);
  });

  it("o texto da casa quebra, nunca corta", () => {
    expect(app).not.toMatch(/\btruncate\b|line-clamp-\d|text-ellipsis/);
    expect(app).toContain("<MoreBelow");
  });
});
