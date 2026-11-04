import { expect, test } from "@playwright/test";

// Os apps no CELULAR: grade de duas colunas, ícone grande e o nome embaixo, que quebra e
// nunca corta (fase 2, D6). O número fica dentro do canto do ícone. E a carga direta a
// 390 px hidrata a mesma árvore que o servidor mandou.
test.describe("Central — os apps no celular", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("duas colunas, nome inteiro, sem estourar a largura", async ({ page }) => {
    const hydration: string[] = [];
    page.on("console", (message) => {
      if (/hydration/i.test(message.text())) hydration.push(message.text());
    });
    await page.goto("/");

    const apps = page.locator("[data-hub-app-link]");
    await expect(apps.first()).toBeVisible();
    const boxes = await apps.evaluateAll((nodes) =>
      nodes.map((node) => {
        const rect = node.getBoundingClientRect();
        const title = node.querySelector<HTMLElement>("[data-tile-title]")!;
        return { left: Math.round(rect.left), height: rect.height, clipped: title.scrollWidth > title.clientWidth + 1 };
      }),
    );
    expect(boxes.length).toBeGreaterThan(3);
    expect(new Set(boxes.map((box) => box.left)).size).toBe(2);
    for (const box of boxes) {
      expect(box.height).toBeGreaterThanOrEqual(44);
      expect(box.clipped, "nenhum nome cortado").toBe(false);
    }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    expect(hydration).toEqual([]);
  });
});
