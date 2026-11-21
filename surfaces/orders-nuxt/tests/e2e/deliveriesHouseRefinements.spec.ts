import { expect, test, type Page } from "@playwright/test";

// Quem leva, refinamentos (M3c, #2899, DEV-2026-030): "Outro da casa" com mais de 3 na
// escala, a hora da volta de quem está na rua, a observação para o entregador e a página
// que funciona só com a casa (TaOn desligada).
const MOCK = `http://127.0.0.1:${Number(process.env.MOCK_PORT || 8796)}`;

type HouseState = { rides: { refs: string[]; courier: string; note?: string }[] };

async function house(page: Page): Promise<HouseState> {
  return (await (await page.request.get(`${MOCK}/api/v1/backstage/e2e/deliveries/house/`)).json()) as HouseState;
}

async function crew(page: Page, baseURL: string, mode: string) {
  await page.context().addCookies([{ name: "e2e_crew", value: mode, url: baseURL }, { name: "e2e_ns", value: "house-refinements", url: baseURL }]);
  await page.request.delete(`${MOCK}/api/v1/backstage/e2e/deliveries/house/`);
  await page.context().route("https://wa.me/**", (route) => route.fulfill({ status: 200, body: "whatsapp" }));
}

test.describe("Entregas: Quem leva, refinamentos", () => {
  test.use({ viewport: { width: 1360, height: 900 } });

  test("com 5 na escala, o último chip vira Outro da casa e a lista escolhe", async ({ page, baseURL }) => {
    await crew(page, baseURL!, "many");
    await page.goto("/delivery");
    await page.getByRole("button", { name: "Chamar juntas", exact: true }).click();
    const sheet = page.getByRole("dialog", { name: "Chamar a corrida C" });
    const who = sheet.getByRole("radiogroup", { name: "Quem leva a corrida C" });
    await expect(who.getByRole("radio")).toHaveCount(4);
    await expect(who.getByText("Mais 3 na escala", { exact: true })).toBeVisible();
    await who.getByText("Outro da casa", { exact: true }).click();
    await expect(who.getByText("Diego · R$ 15,00 ✔", { exact: true })).toBeVisible();
    await expect(sheet.getByRole("button", { name: "Enviar para Diego: A47 e C03", exact: true })).toBeVisible();

    await sheet.locator("[data-ride-carrier-other]").click();
    // Quem está na rua diz quando volta.
    await expect(page.getByRole("option", { name: "Caio · Volta 12h50 · R$ 16,00" })).toBeVisible();
    await page.getByRole("option", { name: "Eva · Livre · R$ 15,50" }).click();
    await expect(who.getByText("Eva · R$ 15,50 ✔", { exact: true })).toBeVisible();
    await expect(sheet.getByRole("button", { name: "Enviar para Eva: A47 e C03", exact: true })).toBeVisible();
  });

  test("a observação para o entregador vai junto com a corrida", async ({ page, baseURL }) => {
    await crew(page, baseURL!, "on");
    await page.goto("/delivery");
    await page.getByRole("button", { name: "Chamar juntas", exact: true }).click();
    const sheet = page.getByRole("dialog", { name: "Chamar a corrida C" });
    await expect(sheet.locator("[data-ride-carrier-note]")).toHaveCount(0); // com a TaOn, não há
    await sheet.getByRole("radiogroup", { name: "Quem leva a corrida C" }).getByText("Diego", { exact: true }).click();
    const note = sheet.getByRole("textbox", { name: "Observação para Diego (opcional)" });
    await note.fill("Interfone quebrado, ligue ao chegar.");
    const popup = page.context().waitForEvent("page");
    await sheet.getByRole("button", { name: "Enviar para Diego: A47 e C03", exact: true }).click();
    await popup;
    await expect.poll(async () => (await house(page)).rides.at(-1)?.note ?? "").toBe("Interfone quebrado, ligue ao chegar.");
  });

  test("só com a casa (TaOn desligada): a página funciona e o primeiro livre vem marcado", async ({ page, baseURL }) => {
    await crew(page, baseURL!, "alone");
    await page.goto("/delivery");
    await expect(page.locator("[data-deliveries-off]")).toHaveCount(0);
    await page.getByRole("button", { name: /A47 · Ana/ }).click();
    const card = page.locator("[data-ride-quote]");
    await expect(card.getByRole("radio", { name: /TaOn/ })).toHaveCount(0);
    await expect(card.getByRole("radio", { name: /Diego/ })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("button", { name: "Enviar para Diego: A47", exact: true }).first()).toBeVisible();
  });

  test("sem TaOn e sem casa: a página informa e leva aos serviços de entrega", async ({ page, baseURL }) => {
    await crew(page, baseURL!, "nobody");
    await page.goto("/delivery");
    const off = page.locator("[data-deliveries-off]");
    await expect(off.getByText("Nenhum serviço de entrega está ligado.", { exact: true })).toBeVisible();
    await expect(off.getByRole("link", { name: "Abrir os serviços de entrega" })).toHaveAttribute("href", /\/admin\/shop\/deliveryservice\/$/);
  });
});
