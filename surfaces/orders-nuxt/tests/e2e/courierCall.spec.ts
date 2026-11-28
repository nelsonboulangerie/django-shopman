import { expect, test } from "@playwright/test";

// #2876 (decisão 4 = A do dono): o Painel do pedido e o detalhe abrem o MESMO sheet
// de chamar das Entregas. O cartão Pronto de entrega ganha "Chamar entregador" (o
// gesto cai de 3 para 2: tocar e chamar), e a faixa "Aguardando entregador" abre a
// parte "A coletar" da Saída e leva às Entregas. Cookie `e2e_call=on` no mock.
const MOCK = `http://127.0.0.1:${Number(process.env.MOCK_PORT || 8796)}`;
const A47 = "WEB-20261116-0A47";
const C03 = "WEB-20261116-0C03";
type Ride = { refs: string[]; ride_number: number };
async function rides(page: import("@playwright/test").Page): Promise<Ride[]> {
  return ((await (await page.request.get(`${MOCK}/api/v1/backstage/e2e/call/`)).json()) as { rides: Ride[] }).rides;
}

test.describe("Chamar entregador do Painel e do detalhe", () => {
  // O mock guarda as chamadas num estado só, e o beforeEach o zera: em paralelo, o
  // zerar de um teste apagava o que o outro estava contando. Um de cada vez.
  test.describe.configure({ mode: "serial" });
  test.use({ viewport: { width: 1366, height: 900 } });
  test.beforeEach(async ({ context, baseURL, page }) => {
    await context.addCookies([{ name: "e2e_call", value: "on", url: baseURL! }]);
    await page.request.delete(`${MOCK}/api/v1/backstage/e2e/call/`);
  });

  test("a faixa da Saída abre A coletar e leva às Entregas", async ({ page }) => {
    await page.goto("/?view=board&columns=all");
    const band = page.locator("[data-exit-waiting-band]");
    await expect(band).toBeVisible();
    await expect(band.getByText("A coletar", { exact: true })).toBeVisible();
    await expect(band.getByText("Aguardando entregador: 3", { exact: true })).toBeVisible();
    const go = band.getByRole("link", { name: "Montar corridas (1 sugerida)", exact: true });
    await expect(go).toHaveAttribute("href", "/delivery");
    // O rótulo "A coletar" não se repete no primeiro cartão.
    await expect(page.locator('[data-zone="expedition"] [data-exit-part]').filter({ hasText: "A coletar" })).toHaveCount(1);
  });

  test("o cartão Pronto chama em dois toques, com o companheiro da sugestão marcado", async ({ page }) => {
    await page.goto("/?view=board&columns=all");
    const before = await rides(page);
    const card = page.locator("article").filter({ hasText: "A47" }).first();
    await card.getByRole("button", { name: "Chamar entregador", exact: true }).click();
    const sheet = page.getByRole("dialog", { name: "Chamar entregador para A47" });
    await expect(sheet).toBeVisible();
    await expect(sheet.getByText("Vai junto nesta corrida?", { exact: true })).toBeVisible();
    await expect(sheet.getByRole("checkbox", { name: "Levar C03 junto" })).toBeChecked();
    await expect(sheet.getByText("Sugestão da casa", { exact: true })).toBeVisible();
    await expect(sheet.getByText("Juntas: R$ 16,50 · 24 min · 5,7 km ✔", { exact: true })).toBeVisible();
    await expect(sheet.getByText("Separadas sairiam R$ 25,00", { exact: true })).toBeVisible();
    await expect(sheet.getByRole("textbox", { name: "Troco para C03", exact: true })).toHaveValue("20,00");
    await expect(sheet.getByText("Sai da gaveta: R$ 20,00 de troco.", { exact: true })).toBeVisible();
    await sheet.getByRole("button", { name: "Chamar corrida com A47 e C03", exact: true }).click();
    await expect(sheet).toBeHidden();
    // As corridas em grupo do mock são de todas as specs: vale a que nasceu depois do toque.
    await expect.poll(async () => (await rides(page)).slice(before.length).at(-1) ?? null).toMatchObject({ refs: [A47, C03], ride_number: 3 });
  });

  test("o detalhe do pedido abre o mesmo sheet; Chamar só A47 chama um pedido", async ({ page }) => {
    await page.goto(`/${A47}`);
    await page.locator("[data-courier-call]").click();
    const sheet = page.getByRole("dialog", { name: "Chamar entregador para A47" });
    await expect(sheet).toBeVisible();
    await expect(sheet.locator("[data-call-sheet-map]")).toBeVisible();
    await sheet.getByRole("button", { name: "Chamar só A47", exact: true }).click();
    await expect(sheet).toBeHidden();
    await expect
      .poll(async () => ((await (await page.request.get(`${MOCK}/api/v1/backstage/e2e/call/`)).json()) as { calls: { ref: string; ride_number: number }[] }).calls.at(-1) ?? null)
      .toMatchObject({ ref: A47, ride_number: 3 });
  });

  test("vindo do lembrete do cartão (#courier-call), o detalhe abre já com o sheet", async ({ page }) => {
    await page.goto(`/${A47}#courier-call`);
    await expect(page.getByRole("dialog", { name: "Chamar entregador para A47" })).toBeVisible();
  });

  test("Voltar fecha sem chamar nada", async ({ page }) => {
    await page.goto("/?view=board&columns=all");
    const callsOfC03 = async () =>
      ((await (await page.request.get(`${MOCK}/api/v1/backstage/e2e/call/`)).json()) as { calls: { ref: string }[] }).calls
        .filter((call) => call.ref === C03).length;
    const callsBefore = await callsOfC03();
    const before = (await rides(page)).filter((ride) => ride.refs.includes(C03)).length;
    await page.locator("article").filter({ hasText: "C03" }).first().getByRole("button", { name: "Chamar entregador", exact: true }).click();
    const sheet = page.getByRole("dialog", { name: "Chamar entregador para C03" });
    await sheet.getByRole("button", { name: "Voltar", exact: true }).click();
    await expect(sheet).toBeHidden();
    expect(await callsOfC03()).toBe(callsBefore);
    expect((await rides(page)).filter((ride) => ride.refs.includes(C03))).toHaveLength(before);
  });
});
