import { expect, test, type Page } from "@playwright/test";

// Retrato opcional para auditar à mão: `POS_CAPTURE_DIR=<pasta> npx playwright test ...`.
async function capture(page: Page, name: string) {
  if (process.env.POS_CAPTURE_DIR) await page.screenshot({ path: `${process.env.POS_CAPTURE_DIR}/${name}` });
}

// O diálogo Cliente com um cadastro escolhido (#2885): no celular (375 px) o corpo
// transbordava 90 px à direita (`scrollWidth` 433 para `clientWidth` 343), e a busca, o
// "Remover cliente", o selo de aniversário e os campos ficavam cortados. A trava mede a
// geometria, não o pixel: o corpo não rola para o lado e nenhum elemento à vista passa da
// borda direita do diálogo. A cliente do mock (`MOCK_CUSTOMER=1`) traz tudo o que o
// diálogo mostra: 29 pedidos, Favorito, Último pedido e o aniversário de hoje com a promoção.
for (const size of [{ width: 375, height: 812 }, { width: 1366, height: 768 }] as const) {
  test(`diálogo Cliente sem transbordo lateral em ${size.width}`, async ({ page }) => {
    await page.setViewportSize(size);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await page.getByRole("button", { name: /#13/ }).first().click();
    await expect(page.getByPlaceholder(/Buscar produto/).first()).toBeVisible();
    // F6 é o atalho do Cliente na venda, em qualquer largura.
    await page.keyboard.press("F6");
    const dialog = page.getByRole("dialog").filter({ has: page.getByRole("combobox", { name: "Buscar cliente" }) }).first();
    const search = dialog.getByRole("combobox", { name: "Buscar cliente" });
    await expect(search).toBeVisible();
    await search.fill("Maria");
    await dialog.getByRole("option", { name: /Maria Santos/ }).first().click();
    await expect(dialog.getByText("Cadastro existente · Maria Santos")).toBeVisible();
    await expect(dialog.getByText(/Aniversário hoje/)).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Remover cliente" })).toBeVisible();
    // O convite da busca cabe no campo: a frase curta no celular, a inteira no balcão.
    await expect(search).toHaveAttribute("placeholder", size.width < 640 ? "Nome, telefone, CPF ou e-mail" : "Buscar por nome, telefone, CPF ou e-mail");

    const geometry = await dialog.evaluate((root) => {
      const content = root.closest("[role='dialog']") ?? root;
      const body = content.querySelector<HTMLElement>("[data-slot='body']");
      if (!body) return { found: false, scrollWidth: 0, clientWidth: 0, right: 0, outside: [] as string[] };
      const right = content.getBoundingClientRect().right;
      const outside: string[] = [];
      for (const el of body.querySelectorAll<HTMLElement>("*")) {
        const box = el.getBoundingClientRect();
        if (box.width < 2 || box.height < 2) continue;
        const style = getComputedStyle(el);
        if (style.visibility === "hidden" || style.display === "none") continue;
        if (box.right > right + 0.5) {
          const label = (el.getAttribute("aria-label") || el.getAttribute("placeholder") || el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 50);
          outside.push(`${el.tagName.toLowerCase()} "${label}" right=${Math.round(box.right)} > ${Math.round(right)}`);
        }
      }
      // O convite da busca inteiro dentro do campo (o campo não rola o texto: mede-se a frase).
      const input = body.querySelector<HTMLInputElement>("input[aria-label='Buscar cliente']");
      if (input) {
        const style = getComputedStyle(input);
        const ctx = document.createElement("canvas").getContext("2d")!;
        ctx.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
        const room = input.clientWidth - Number.parseFloat(style.paddingLeft) - Number.parseFloat(style.paddingRight);
        const need = ctx.measureText(input.placeholder).width;
        if (need > room) outside.push(`placeholder "${input.placeholder}" precisa de ${Math.ceil(need)} px, o campo tem ${Math.floor(room)}`);
      }
      return { found: true, scrollWidth: body.scrollWidth, clientWidth: body.clientWidth, right, outside };
    });
    await capture(page, `dialogo-cliente-${size.width}.png`);
    expect(geometry.found, "o corpo do diálogo (data-slot=body)").toBe(true);
    expect(geometry.scrollWidth, "o corpo do diálogo não rola para o lado").toBeLessThanOrEqual(geometry.clientWidth);
    expect(geometry.outside, "nada passa da borda direita do diálogo").toEqual([]);
  });
}
