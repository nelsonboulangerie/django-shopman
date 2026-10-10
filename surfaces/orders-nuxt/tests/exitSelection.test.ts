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
    // A barra é a `OperatorBulkBar` (mesa e base): o × dela tem o nome do gesto.
    const bars = read("../app/pages/index.vue").match(/<OperatorBulkBar\b[\s\S]*?\/>/g) ?? [];
    expect(bars).toHaveLength(2);
    for (const bar of bars) expect(bar).toContain(':clear-label="EXIT_SELECTION_LABEL"');
    expect(read("../app/components/BoardMenu.vue")).toContain("EXIT_SELECTION_LABEL");
  });
});
