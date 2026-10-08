import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Grade da Saída larga (posto Saída): cada cartão tem a altura do que tem. Esticado
// até o mais alto da linha, o cartão curto ganhava uma faixa vazia acima do rodapé
// (dono, 08/10/2026).
describe("Saída larga", () => {
  it("a grade não estica os cartões até o mais alto da linha", () => {
    const column = readFileSync(new URL("../app/components/OrderBoardColumn.vue", import.meta.url), "utf8");
    const grid = column.slice(column.indexOf('v-else-if="wide"'), column.indexOf("data-zone-cards"));
    expect(grid).toMatch(/class="grid [^"]*\bitems-start\b/);
    // E o cartão não se estica sozinho: `h-full` preenchia a linha da grade.
    const card = readFileSync(new URL("../app/components/OrderCard.vue", import.meta.url), "utf8");
    const root = card.slice(card.indexOf("<NuxtCard"), card.indexOf(">", card.indexOf("<NuxtCard")));
    expect(root).not.toMatch(/\bh-full\b/);
  });
});
