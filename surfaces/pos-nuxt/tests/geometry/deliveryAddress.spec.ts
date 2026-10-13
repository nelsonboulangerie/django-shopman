import { expect, test, type Page } from "@playwright/test";

// O ENDEREÇO DE ENTREGA DO RECEBIMENTO, na grade da loja online (decisão do dono,
// 13/10): busca; rua; número e complemento; bairro e CEP; cidade e UF; instruções.
// Do mesa ao celular, sem rolagem lateral, cada linha de campos borda a borda com a
// rua (D4) e os campos irmãos da mesma altura (D5); o erro da validação cabe numa
// linha sob a linha de campos. A comanda 12 do mock abre como encomenda com entrega
// (`MOCK_ADDRESS=1`), e o ViaCEP é respondido pelo teste.
const SIZES = [
  { width: 1366, height: 768 },
  { width: 390, height: 844 },
] as const;

async function openAddress(page: Page, size: { width: number; height: number }, scheme: "light" | "dark") {
  await page.setViewportSize(size);
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: scheme });
  await page.addInitScript((mode) => window.localStorage.setItem("pos-nuxt-color-mode", mode), scheme);
  await page.route("https://viacep.com.br/**", (route) => route.fulfill({
    json: { cep: "86010-000", logradouro: "Rua Pará", bairro: "Centro", localidade: "Londrina", uf: "PR" },
  }));
  await page.goto("/");
  await page.getByRole("button", { name: /#12/ }).first().click();
  // A comanda carregada (as três linhas da 12) antes da tecla: no primeiro teste o
  // `nuxt dev` ainda recarrega a página depois de otimizar as dependências.
  await expect(page.locator("[data-pos-ticket-column] [data-item-select]")).toHaveCount(3);
  await page.keyboard.press("F7");
  const search = page.locator('[data-focus-target="delivery-search"] input');
  await expect(search).toBeFocused();
  await search.fill("86010-000");
  await page.keyboard.press("Enter");
  await expect(page.locator('[data-focus-target="delivery-number"] input')).toBeFocused();
}

/** Bordas e alturas dos campos do endereço, para conferir a grade. */
async function fieldBoxes(page: Page) {
  return page.evaluate(() => {
    const keys = ["search", "route", "number", "complement", "neighborhood", "postal_code", "city", "state", "instructions"];
    const out: Record<string, { left: number; right: number; height: number; top: number }> = {};
    for (const key of keys) {
      const block = document.querySelector(`[data-focus-target="delivery-${key}"]`);
      const control = block?.querySelector("input, button");
      if (!control) continue;
      const r = control.getBoundingClientRect();
      out[key] = { left: r.left, right: r.right, height: r.height, top: r.top };
    }
    return out;
  });
}

for (const scheme of ["light", "dark"] as const) {
  for (const size of SIZES) {
    test(`endereço da entrega ${size.width}x${size.height} (${scheme}): a grade da loja, borda a borda, sem rolagem lateral`, async ({ page }) => {
      await openAddress(page, size, scheme);
      const boxes = await fieldBoxes(page);
      const rua = boxes.route!;
      // Cada linha começa e termina nas bordas da rua (D4).
      for (const [first, last] of [["number", "complement"], ["neighborhood", "postal_code"], ["city", "state"]] as const) {
        expect(Math.abs(boxes[first]!.left - rua.left), `${first} começa na borda da rua`).toBeLessThanOrEqual(1);
        expect(Math.abs(boxes[last]!.right - rua.right), `${last} termina na borda da rua`).toBeLessThanOrEqual(1);
        // Irmãos da mesma linha: mesma altura e mesmo topo (D5).
        expect(Math.abs(boxes[first]!.height - boxes[last]!.height)).toBeLessThanOrEqual(1);
        expect(Math.abs(boxes[first]!.top - boxes[last]!.top)).toBeLessThanOrEqual(1);
      }
      for (const key of ["search", "instructions"] as const) {
        expect(Math.abs(boxes[key]!.left - rua.left)).toBeLessThanOrEqual(1);
        expect(Math.abs(boxes[key]!.right - rua.right)).toBeLessThanOrEqual(1);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

      // Sem o número, a confirmação aponta o campo, e a frase cabe numa linha só.
      await page.locator("[data-pos-fulfillment-confirm]").click();
      const message = page.locator("[data-pos-address-row-error]");
      await expect(message).toHaveText('Informe o número (ou "s/n").');
      const lines = await message.evaluate((el) => {
        const lineHeight = parseFloat(getComputedStyle(el).lineHeight);
        return Math.round(el.getBoundingClientRect().height / lineHeight);
      });
      expect(lines).toBe(1);
      await expect(page.locator('[data-focus-target="delivery-number"] input')).toBeFocused();
    });
  }
}
