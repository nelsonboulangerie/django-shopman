import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { EXIT_SELECTION_LABEL } from "../app/presentation/board";

// Sair do modo de seleção tem um nome só, no ⋯ do quadro e na barra de lote. A barra
// dizia "Concluir", que no mesmo app é concluir o pedido entregue: quem tocava achava
// que tinha concluído os pedidos marcados.
const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");

describe("sair da seleção", () => {
  it("tem o nome do gesto, não o de concluir pedido", () => {
    expect(EXIT_SELECTION_LABEL).toBe("Sair da seleção");
  });

  it("a barra de lote e o ⋯ do quadro usam o mesmo rótulo", () => {
    const bulkBar = read("../app/pages/index.vue").match(
      /<NuxtButton[^>]*?data-bulk-done[^>]*?>|<NuxtButton(?:(?!<NuxtButton)[\s\S])*?data-bulk-done/,
    )?.[0];
    expect(bulkBar).toContain(':label="EXIT_SELECTION_LABEL"');
    expect(read("../app/components/BoardMenu.vue")).toContain("EXIT_SELECTION_LABEL");
  });
});
