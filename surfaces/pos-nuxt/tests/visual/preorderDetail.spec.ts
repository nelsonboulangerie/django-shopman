import { expect, test } from "@playwright/test";
import { scanOperatorGeometry } from "../../../operator-kit/visual/scanner";

// S5 do redesenho das Encomendas: o painel do Balcão nos cinco tamanhos do WP
// (375, 390, 768, 1024, 1440). Sem retrato: o que se prova é a geometria, que
// não depende da versão do navegador. Em tela larga o painel fica à direita e
// FIXO (o saldo à vista enquanto se conferem os itens); em tela estreita ele vem
// antes do detalhe. Em nenhum tamanho a página rola para o lado.
const SIZES = [
  { width: 375, height: 667, wide: false },
  { width: 390, height: 844, wide: false },
  { width: 768, height: 1024, wide: false },
  { width: 1024, height: 768, wide: true },
  { width: 1440, height: 900, wide: true },
] as const;

for (const size of SIZES) {
  test(`detalhe da encomenda em ${size.width}x${size.height}`, async ({ page }) => {
    await page.setViewportSize({ width: size.width, height: size.height });
    await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "light" });
    await page.goto("/preorders/NB-1042");
    const panel = page.locator("[data-preorder-counter-panel]");
    const detail = page.locator("[data-order-detail]");
    await expect(panel).toBeVisible();
    await expect(detail).toBeVisible();

    const geometry = await scanOperatorGeometry(page, { touch: size.width < 1024 });
    expect(geometry.filter(({ kind }) => kind === "horizontal-overflow")).toEqual([]);
    // Nada do painel passa da borda dele (nome, saldo e botões cabem).
    const overflow = await panel.evaluate((el) => [...el.querySelectorAll("*")].some((child) => {
      const box = child.getBoundingClientRect();
      const frame = el.getBoundingClientRect();
      return box.width > 0 && (box.left < frame.left - 1 || box.right > frame.right + 1);
    }));
    expect(overflow).toBe(false);
    // Alvo de toque: todo botão do painel tem pelo menos 44 px de altura, e
    // nenhum rótulo passa da borda do próprio botão.
    const buttons = await panel.locator("button").evaluateAll((els) => els.map((el) => ({
      height: el.getBoundingClientRect().height,
      fits: el.scrollWidth <= el.clientWidth,
    })));
    for (const button of buttons) {
      expect(button.height).toBeGreaterThanOrEqual(44);
      expect(button.fits).toBe(true);
    }

    const panelBox = (await panel.boundingBox())!;
    const detailBox = (await detail.boundingBox())!;
    if (size.wide) {
      expect(panelBox.x).toBeGreaterThanOrEqual(detailBox.x + detailBox.width);
      // Rolar até o fim do detalhe não tira o saldo nem o gesto de vista.
      await page.locator("[data-order-timeline]").scrollIntoViewIfNeeded();
      await expect(page.locator("[data-preorder-money]")).toBeInViewport();
      await expect(page.locator("[data-preorder-hand-over]")).toBeInViewport();
    } else {
      expect(panelBox.y + panelBox.height).toBeLessThanOrEqual(detailBox.y);
      // Tela estreita: o saldo e o gesto principal são a primeira coisa da tela.
      await expect(page.locator("[data-preorder-money]")).toBeInViewport();
      await expect(page.locator("[data-preorder-hand-over]")).toBeInViewport();
    }
  });
}
