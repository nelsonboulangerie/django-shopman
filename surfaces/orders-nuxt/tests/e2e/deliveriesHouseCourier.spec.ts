import { expect, test, type Page } from "@playwright/test";

// "Quem leva" (M3, #2526, DEV-2026-030): o operador escolhe quem leva no MESMO gesto de
// chamar. O padrão do Admin (TaOn) vem marcado; quem da casa está na escala aparece a um
// toque. Escolhida a casa, a cotação vira o valor da tabela, o botão diz para quem vai,
// a corrida sai pela porta da casa e o WhatsApp do dispositivo abre com o link pronto.
// Sem ninguém da casa (cenário padrão do mock), a tela é a de antes.
const MOCK = `http://127.0.0.1:${Number(process.env.MOCK_PORT || 8796)}`;

type HouseState = { rides: { refs: string[]; courier: string; base_revisions: Record<string, string>; ride_number?: number }[]; shift: Record<string, boolean> };

async function house(page: Page): Promise<HouseState> {
  return (await (await page.request.get(`${MOCK}/api/v1/backstage/e2e/deliveries/house/`)).json()) as HouseState;
}

test.describe("Entregas: quem leva", () => {
  test.use({ viewport: { width: 1360, height: 900 } });

  test.beforeEach(async ({ context, page, baseURL }) => {
    await context.addCookies([{ name: "e2e_crew", value: "on", url: baseURL! }]);
    await page.request.delete(`${MOCK}/api/v1/backstage/e2e/deliveries/house/`);
    // O WhatsApp não sai do teste: a aba que o toque abre cai aqui.
    await context.route("https://wa.me/**", (route) => route.fulfill({ status: 200, body: "whatsapp" }));
  });

  test("o sheet traz a TaOn marcada e Diego a um toque; escolher Diego muda cotação e botão", async ({ page }) => {
    await page.goto("/delivery");
    await page.getByRole("button", { name: "Chamar juntas", exact: true }).click();
    const sheet = page.getByRole("dialog", { name: "Chamar a corrida C" });
    const who = sheet.getByRole("radiogroup", { name: "Quem leva a corrida C" });
    await expect(who.getByRole("radio")).toHaveCount(2);
    await expect(who.getByRole("radio", { name: /TaOn/ })).toHaveAttribute("aria-checked", "true");
    // O ✔ marca o escolhido, como na cotação: só um dos dois o tem.
    await expect(who.getByText("R$ 16,50 ✔", { exact: true })).toBeVisible();
    await expect(who.getByText("Livre · R$ 15,00", { exact: true })).toBeVisible();
    await expect(sheet.getByText("Juntas: R$ 16,50 · 24 min · 5,7 km ✔", { exact: true }).first()).toBeVisible();
    const footer = page.getByText("2 pedidos em 1 corrida · R$", { exact: false }).first();
    await expect(footer).toContainText("R$ 16,50");

    await who.getByText("Diego", { exact: true }).click();
    await expect(who.getByRole("radio", { name: /Diego/ })).toHaveAttribute("aria-checked", "true");
    await expect(who.getByText("Livre · R$ 15,00 ✔", { exact: true })).toBeVisible();
    await expect(who.getByText("R$ 16,50", { exact: true })).toBeVisible();
    await expect(sheet.getByText("Valor da tabela: R$ 15,00", { exact: true })).toBeVisible();
    // O rodapé da chamada segue quem leva: o valor da tabela, nunca a cotação da TaOn.
    await expect(footer).toContainText("R$ 15,00");
    await expect(footer).not.toContainText("R$ 16,50");
    await expect(sheet.getByText(/Juntas:|Separadas/)).toHaveCount(0);
    await expect(sheet.getByRole("button", { name: "Enviar para Diego: A47 e C03", exact: true })).toBeVisible();
  });

  test("enviar para Diego manda a corrida à casa e abre o WhatsApp no mesmo toque", async ({ page, context }) => {
    await page.goto("/delivery");
    await page.getByRole("button", { name: "Chamar juntas", exact: true }).click();
    const sheet = page.getByRole("dialog", { name: "Chamar a corrida C" });
    await sheet.getByRole("radiogroup", { name: "Quem leva a corrida C" }).getByText("Diego", { exact: true }).click();
    const popup = context.waitForEvent("page");
    await sheet.getByRole("button", { name: "Enviar para Diego: A47 e C03", exact: true }).click();
    const tab = await popup;
    await expect.poll(() => tab.url()).toContain("https://wa.me/5543999990000?text=");
    expect(decodeURIComponent(tab.url())).toContain("Corrida para você: Rota C. Abra o link no seu celular: https://loja.test/rota/tok1");
    await expect(page.getByText("Rota C enviada para Diego.", { exact: true })).toBeVisible();
    const sent = (await house(page)).rides;
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatchObject({
      refs: ["WEB-20261116-0A47", "WEB-20261116-0C03"],
      courier: "diego",
      ride_number: 3,
      base_revisions: { "WEB-20261116-0A47": "r-a47", "WEB-20261116-0C03": "r-c03" },
    });
  });

  test("na corrida montada à mão, os mesmos chips; com a TaOn, a chamada de sempre", async ({ page }) => {
    await page.goto("/delivery");
    await page.getByRole("button", { name: /A47 · Ana/ }).click();
    const card = page.locator("[data-ride-quote]");
    await expect(card.getByRole("radio", { name: /TaOn/ })).toHaveAttribute("aria-checked", "true");
    await expect(card.locator("[data-ride-carrier]")).toContainText("Livre · R$ 12,00");
    await card.getByText("Diego", { exact: true }).click();
    await expect(card.getByText("Valor da tabela: R$ 12,00", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Enviar para Diego: A47", exact: true }).first()).toBeVisible();
    await card.getByText("TaOn", { exact: true }).click();
    await expect(page.getByRole("button", { name: "Chamar a corrida C", exact: true }).first()).toBeVisible();
  });

  test("a escolha sai com a corrida: Voltar e montar de novo traz a TaOn marcada", async ({ page }) => {
    await page.goto("/delivery");
    await page.getByRole("button", { name: "Chamar juntas", exact: true }).click();
    const sheet = page.getByRole("dialog", { name: "Chamar a corrida C" });
    await sheet.getByRole("radiogroup", { name: "Quem leva a corrida C" }).getByText("Diego", { exact: true }).click();
    await sheet.getByRole("button", { name: "Voltar", exact: true }).click();
    await page.getByRole("button", { name: /A47 · Ana/ }).click();
    await expect(page.locator("[data-ride-quote]").getByRole("radio", { name: /TaOn/ })).toHaveAttribute("aria-checked", "true");
  });

  test("Entregadores de hoje: um toque põe Rui na escala e ele vira opção", async ({ page }) => {
    await page.goto("/delivery");
    const bar = page.locator("[data-house-shift]");
    await expect(bar.getByText("Entregadores de hoje", { exact: true })).toBeVisible();
    await expect(bar.getByRole("button", { name: "Diego", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(bar.getByRole("button", { name: "Rui", exact: true })).toHaveAttribute("aria-pressed", "false");
    await bar.getByRole("button", { name: "Rui", exact: true }).click();
    await expect(bar.getByRole("button", { name: "Rui", exact: true })).toHaveAttribute("aria-pressed", "true");
    expect((await house(page)).shift.rui).toBe(true);
    await page.getByRole("button", { name: /A47 · Ana/ }).click();
    await expect(page.locator("[data-ride-quote]").getByRole("radio")).toHaveCount(3);
  });
});

test.describe("Entregas: sem ninguém da casa", () => {
  test.use({ viewport: { width: 1360, height: 900 } });

  test("o sheet e a corrida em edição ficam como antes, sem Quem leva nem Entregadores de hoje", async ({ page }) => {
    await page.goto("/delivery");
    await expect(page.locator("[data-house-shift]")).toHaveCount(0);
    await page.getByRole("button", { name: "Chamar juntas", exact: true }).click();
    const sheet = page.getByRole("dialog", { name: "Chamar a corrida C" });
    await expect(sheet.getByRole("button", { name: "Chamar a corrida C", exact: true })).toBeVisible();
    await expect(page.locator("[data-ride-carrier]")).toHaveCount(0);
  });
});
