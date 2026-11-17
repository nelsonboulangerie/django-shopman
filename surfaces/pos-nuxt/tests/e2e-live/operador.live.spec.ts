import {
  MAIN_STATION,
  capture,
  cast,
  expect,
  lockDevice,
  managerBindsStation,
  managerSignsIn,
  operatorUnlocksWithPin,
  seesTabs,
  test,
} from "./support/operator";

// J0 Entrar (WP-E12): a fumaça do harness ao vivo. Um dispositivo novo em folha;
// a Gerente (Joyce) entra com senha e vincula o "PDV principal"; trava; a Caixa
// (Fran) toca no nome, digita o PIN e vê as comandas. No celular e no balcão.
// Como rodar: README.md desta pasta.
for (const device of ["phone", "counter"] as const) {
  test.describe(`J0 Entrar · ${device === "phone" ? "375 px" : "1366 px"}`, () => {
    test.use({ device });

    test("Gerente inicia o dispositivo, trava, e a Caixa entra com PIN", async ({ freshDevice: page }, testInfo) => {
      await page.goto("/");
      await expect(page.getByRole("textbox", { name: "Usuário" })).toBeVisible({ timeout: 60_000 });
      await capture(page, testInfo, "entre-para-operar");

      await managerSignsIn(page);
      await capture(page, testInfo, "gerente-entrou");

      await managerBindsStation(page, MAIN_STATION);
      await capture(page, testInfo, "posto-vinculado");

      await lockDevice(page);
      await capture(page, testInfo, "travado");

      await operatorUnlocksWithPin(page, cast.cashier);
      await seesTabs(page);
      // Quem opera agora é a Caixa, e não a Gerente que iniciou o dispositivo.
      await expect(page.getByText(cast.cashier.name, { exact: true }).first()).toBeVisible();
      await capture(page, testInfo, "caixa-no-quadro");
    });
  });
}
