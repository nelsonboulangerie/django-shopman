import { expect, test } from "@playwright/test";

// A grade no CELULAR: todo tile com a MESMA altura.
//
// ⚠️ O tile tinha `min-h-28` e o bloco de texto empurrado para baixo com `mt-auto`.
// Nome e frase quebram em uma ou duas linhas conforme o app, então cada card parava numa
// altura diferente e a grade de duas colunas ficava serrilhada — o olho perdia a coluna
// e a leitura virava um ziguezague. O teto agora é duas linhas para o nome e duas para a
// frase, o que passa disso é cortado com reticências, e a altura é fixa.
test.describe("Shopman Apps — a grade no celular", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("todos os tiles têm a mesma altura, e o texto para em duas linhas", async ({ page }) => {
    await page.goto("/");

    const tiles = page.locator("ul > li > a");
    await expect(tiles.first()).toBeVisible();

    const boxes = await tiles.evaluateAll(nodes => nodes.map((node) => {
      const title = node.querySelector("[data-tile-title]") as HTMLElement;
      const description = node.querySelector("[data-tile-description]") as HTMLElement;
      return {
        height: node.getBoundingClientRect().height,
        // `scrollHeight > clientHeight` é o texto que o `line-clamp` cortou; o que importa
        // é que a caixa DO CARD nunca transborde, e que todos terminem na mesma altura.
        titleOverflow: title.scrollHeight > title.clientHeight + 1,
        descriptionOverflow: description.scrollHeight > description.clientHeight + 1,
        contentFits: node.scrollHeight <= node.clientHeight + 1,
      };
    }));

    expect(boxes.length).toBeGreaterThan(3);
    expect(new Set(boxes.map(box => box.height)).size, "altura única para todos os tiles").toBe(1);
    for (const box of boxes) expect(box.contentFits, "o texto não vaza da caixa do tile").toBe(true);
  });
});
