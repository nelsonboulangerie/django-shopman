import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

// A tela de venda em MODO EDIÇÃO (WP-E6), lida pela fonte — nenhum teste monta
// `pages/index.vue` inteira (ela depende do terminal, da gaveta e do agente).
// O que se prende aqui é o contrato decidido pelo dono em 28/09: a edição é a
// própria venda, sai por "Salvar alterações" ou "Descartar alterações", não
// dispara cozinha, não transfere linhas, não vai ao quadro e não pede caixa aberto.

const read = (path: string) => readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), path), "utf8");
const page = read("../app/pages/index.vue");

describe("tela de venda em modo edição", () => {
  it("entra por /?edit=<ref> e não exige caixa aberto", () => {
    expect(page).toContain('const editRef = String(useRoute().query.edit || "").trim();');
    expect(page).toMatch(/pos\.value\s*\n\s*&& !editRef\s*\n\s*&& requiresOpenShiftForSale/);
    expect(page).toContain("if (editRef) void startOrderEdit(editRef);");
  });

  it("o gesto principal vira Salvar alterações, com a prévia do servidor", () => {
    expect(page).toContain(":primary-label=\"editing ? 'Salvar alterações' : undefined\"");
    expect(page).toContain('@prepare="editing ? saveOrderEdit() : prepareCheckout()"');
    expect(page).toContain("if (editing.value) saveOrderEdit();"); // F4
    expect(page).toContain("<PosOrderEditReview");
    expect(page).toContain('action="order_edit_refund"');
  });

  it("cabeçalho inequívoco e saída por Descartar alterações", () => {
    expect(page).toContain("data-order-edit-banner");
    expect(page).toContain("orderEditTitle(editOrderRef)");
    expect(page).toContain("Descartar alterações");
  });

  it("não dispara cozinha, não transfere, não vai ao quadro e não vira balcão", () => {
    expect(page).toContain('resolveAffordance(editing.value ? [] : actions.value, "fire_tab")');
    expect(page).toContain(':hide-move="editing"');
    expect(page).toContain("cart.items.length && !editing.value) fireTab();");
    expect(page).toContain("if (editing.value) return; // a edição sai por Salvar ou Descartar");
    expect(page).toContain("Na edição, a encomenda continua encomenda.");
  });
});
