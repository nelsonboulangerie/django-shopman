import { expect, test } from "@playwright/test";

// Os apps no CELULAR: linhas de 62 px em que o nome e a linha de estado quebram, nunca
// cortam (fase 2, D6: "texto da casa cortado" era defeito medido na Central). E a carga
// direta a 390 px hidrata a mesma árvore que o servidor mandou.
test.describe("Central — os apps no celular", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("cada linha mostra o texto inteiro, sem estourar a largura", async ({ page }) => {
    const hydration: string[] = [];
    page.on("console", (message) => {
      if (/hydration/i.test(message.text())) hydration.push(message.text());
    });
    await page.goto("/");

    const rows = page.locator("[data-hub-app-row]");
    await expect(rows.first()).toBeVisible();
    const boxes = await rows.evaluateAll((nodes) =>
      nodes.map((node) => {
        const clipped = [...node.querySelectorAll<HTMLElement>("[data-tile-title], [data-tile-status]")].some(
          (element) => element.scrollWidth > element.clientWidth + 1,
        );
        return { height: node.getBoundingClientRect().height, clipped };
      }),
    );
    expect(boxes.length).toBeGreaterThan(3);
    for (const box of boxes) {
      expect(box.height).toBeGreaterThanOrEqual(62);
      expect(box.clipped, "nenhum texto cortado na linha do app").toBe(false);
    }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    expect(hydration).toEqual([]);
  });
});
