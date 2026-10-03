import { test, expect } from "@playwright/test";

// UX-G3: a Saída da Cozinha virou a coluna Saída do Gestor. O quiosque que guardou o
// endereço da estação de Saída (inclusive os antigos, que o routeRules leva a /saida)
// vai para o Gestor já na visão Saída, nunca para uma página vazia. O Gestor do teste
// não existe (porta 3199): basta conferir o destino pedido.

const authed = { name: "e2e_session", value: "authed", domain: "127.0.0.1", path: "/" };
const GESTOR_EXIT = "http://127.0.0.1:3199/?columns=expedition";

test.describe("KDS: a Saída mora no Gestor", () => {
  for (const path of ["/saida", "/expedicao", "/estacao/expedicao"]) {
    test(`${path} manda para a coluna Saída do Gestor`, async ({ page, context }) => {
      await context.addCookies([authed]);
      const going = page.waitForRequest((request) => request.url() === GESTOR_EXIT);
      await page.goto(path);
      expect((await going).url()).toBe(GESTOR_EXIT);
    });
  }

  test("estação de preparo continua aqui", async ({ page, context }) => {
    await context.addCookies([authed]);
    await page.goto("/bancada");
    await expect(page.getByText("A Saída agora fica no Gestor")).toHaveCount(0);
    expect(new URL(page.url()).pathname).toBe("/bancada");
  });
});
