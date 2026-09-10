import { test, expect } from "@playwright/test";

// Browser transport + actual display page; no gateway, hardware or real sale.
test("Tela do Cliente recebe atualização em uma segunda janela do navegador", async ({ page, context }) => {
  await page.goto("/");
  await page.evaluate(() => {
    const channel = new BroadcastChannel("pos-customer-display");
    Object.assign(window, { displayTestChannel: channel });
    channel.onmessage = (event) => {
      if (event.data?.kind === "hello") channel.postMessage({ kind: "snapshot", snapshot: {
        phase: "sale", shopName: "Balcão de teste", items: [{ name: "Croissant", qty: 2, unitDisplay: "R$ 18,50", totalDisplay: "R$ 37,00", discountLabel: "" }],
        itemCount: 2, totalDisplay: "R$ 37,00", discountDisplay: "", pix: null, changeDisplay: "", customerFirstName: "", orderRef: "", publishedAtMs: Date.now(),
      } });
    };
  });
  const display = await context.newPage();
  await display.goto("/display");
  await expect(display.getByText("Croissant", { exact: true })).toBeVisible();
  await expect(display.getByText("R$ 37,00").last()).toBeVisible();
  await expect(display.getByLabel("Senha")).toHaveCount(0);
  await page.evaluate(() => {
    const channel = (window as unknown as { displayTestChannel: BroadcastChannel }).displayTestChannel;
    channel.postMessage({ kind: "snapshot", snapshot: {
      phase: "result", shopName: "Balcão de teste", items: [], itemCount: 0, totalDisplay: "R$ 37,00", discountDisplay: "", pix: null,
      changeDisplay: "R$ 13,00", customerFirstName: "", orderRef: "TEST", publishedAtMs: Date.now(),
    } });
  });
  await expect(display.getByText("Seu troco")).toBeVisible();
  await expect(display.getByText("R$ 13,00")).toBeVisible();
  await display.screenshot({ path: "test-results/customer-display.png" });
});
