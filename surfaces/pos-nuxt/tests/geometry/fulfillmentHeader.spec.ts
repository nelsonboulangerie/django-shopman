import { expect, test, type Page } from "@playwright/test";

// O DIÁLOGO RECEBIMENTO, NA ABERTURA (#2806): o X não cobre o título nem a frase,
// do celular à mesa; o cartão escolhido (Retirada ou Entrega) tem o estado no papel
// e o rádio cheio; e o resumo do endereço escolhido diz o endereço com o mesmo " · "
// da lista. A comanda 12 do mock abre como encomenda com entrega (`MOCK_ADDRESS=1`).
// Era o X em cima da palavra "definem", a 375 px: o tema oficial posiciona o fechar
// por cima do cabeçalho sem reservar o lugar dele.
const SIZES = [
  { width: 375, height: 812 },
  { width: 390, height: 844 },
  { width: 1366, height: 768 },
] as const;

async function openFulfillment(page: Page, size: { width: number; height: number }) {
  await page.setViewportSize(size);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("https://viacep.com.br/**", (route) => route.fulfill({
    json: { cep: "86010-000", logradouro: "Rua Pará", bairro: "Centro", localidade: "Londrina", uf: "PR" },
  }));
  await page.goto("/");
  await page.getByRole("button", { name: /#12/ }).first().click();
  const dialog = page.locator('[role="dialog"]').filter({ has: page.locator("[data-pos-fulfillment-options]") });
  await expect(async () => {
    if (!(await dialog.isVisible())) await page.keyboard.press("F8");
    await expect(dialog).toBeVisible({ timeout: 3_000 });
  }).toPass({ timeout: 60_000 });
  return dialog;
}

/** As caixas de cada linha do texto do título e da frase, e a do X. */
async function headerBoxes(page: Page) {
  return page.evaluate(() => {
    const dialog = Array.from(document.querySelectorAll('[role="dialog"]'))
      .find((el) => el.querySelector("[data-pos-fulfillment-options]"))!;
    const box = (r: DOMRect) => ({ left: r.left, right: r.right, top: r.top, bottom: r.bottom });
    const lines = (selector: string) => {
      const el = dialog.querySelector(selector)!;
      const range = document.createRange();
      range.selectNodeContents(el);
      return Array.from(range.getClientRects()).filter((r) => r.width > 0).map(box);
    };
    return {
      close: box(dialog.querySelector('[data-slot="close"]')!.getBoundingClientRect()),
      title: lines('[data-slot="title"]'),
      description: lines('[data-slot="description"]'),
      dialog: box(dialog.getBoundingClientRect()),
    };
  });
}

type Box = { left: number; right: number; top: number; bottom: number };
const overlaps = (a: Box, b: Box) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;

for (const size of SIZES) {
  test(`Recebimento ${size.width}x${size.height}: o X fora do título e da frase, a escolha no papel e o endereço com " · "`, async ({ page }) => {
    const dialog = await openFulfillment(page, size);
    await expect(dialog.locator('[data-slot="description"]')).toHaveText("Escolha como o cliente recebe o pedido.");

    const boxes = await headerBoxes(page);
    expect(boxes.title.length).toBeGreaterThan(0);
    expect(boxes.description.length).toBeGreaterThan(0);
    for (const [name, line] of [...boxes.title.map((l) => ["título", l] as const), ...boxes.description.map((l) => ["frase", l] as const)]) {
      expect(overlaps(boxes.close, line), `o X cobre o texto do ${name}`).toBe(false);
      // O texto não passa da borda do diálogo.
      expect(line.right).toBeLessThanOrEqual(boxes.dialog.right);
    }
    // O X continua no canto: 16 px do topo e da borda direita do diálogo.
    expect(Math.round(boxes.close.top - boxes.dialog.top)).toBe(16);
    expect(Math.round(boxes.dialog.right - boxes.close.right)).toBe(16);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

    // A escolha está no papel: Entrega marcada (a comanda 12 é de entrega), Retirada não.
    const radio = (label: string) => dialog.locator('[data-pos-fulfillment-options] [data-slot="item"]', { hasText: label }).locator('[role="radio"]');
    await expect(radio("Entrega")).toHaveAttribute("aria-checked", "true");
    await expect(radio("Retirada")).toHaveAttribute("aria-checked", "false");
    // O cartão escolhido se distingue do outro pela borda, e não só pelo fundo.
    const borders = await dialog.locator('[data-pos-fulfillment-options] [data-slot="item"]').evaluateAll((cards) =>
      cards.map((card) => getComputedStyle(card).borderTopColor));
    expect(new Set(borders).size).toBe(2);

    // O endereço escolhido, com o mesmo separador da lista dos endereços do cliente.
    const search = dialog.locator('[data-focus-target="delivery-search"] input');
    await search.fill("86010-000");
    await page.keyboard.press("Enter");
    await expect(dialog.locator("[data-pos-address-summary] p")).toHaveText("Rua Pará · Centro · Londrina/PR");

    // Trocar para Retirada passa a escolha para o outro cartão.
    await dialog.locator('[data-pos-fulfillment-options] [data-slot="item"]', { hasText: "Retirada" }).click();
    await expect(radio("Retirada")).toHaveAttribute("aria-checked", "true");
    await expect(radio("Entrega")).toHaveAttribute("aria-checked", "false");
  });
}
