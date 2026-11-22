import { expect, test } from "@playwright/test";

// #2500: a TaOn retomou a corrida que constava como encerrada, e o troco e a
// maquininha tinham voltado para a casa. No Painel do pedido, o aviso diz o que
// voltou e o "Separar de novo" registra os dois pela MESMA rota da casa
// (`courier-custody`). O cenário mora no mock (cookie `e2e_custody=on`).
const MOCK = `http://127.0.0.1:${Number(process.env.MOCK_PORT || 8796)}`;
const COOKIE = { cookie: "e2e_custody=on" };

test.beforeEach(async ({ context, page, baseURL }) => {
  await context.addCookies([{ name: "e2e_custody", value: "on", url: baseURL! }]);
  await page.request.delete(`${MOCK}/api/v1/backstage/e2e/custody/`, { headers: COOKIE });
});

test("Separar de novo: o aviso diz o que voltou e o gesto manda o troco e a maquininha", async ({ page }) => {
  await page.goto("/WEB-261116-R05");
  const notice = page.locator("[data-courier-custody-missing]");
  await expect(notice).toContainText("O troco e a maquininha voltaram para a casa");
  await expect(notice).toContainText("A TaOn retomou a corrida. Separe de novo antes de entregar a sacola.");
  await notice.locator("[data-courier-separate]").click();
  const form = page.locator("[data-courier-separate-form]");
  await expect(form).toBeVisible();
  const go = form.locator("[data-courier-separate-go]");
  await expect(go).toHaveText("Separar com a maquininha Azul");
  expect((await go.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
  await go.click();
  await expect(notice).toHaveCount(0);
  const recorded = await (await page.request.get(`${MOCK}/api/v1/backstage/e2e/custody/`, { headers: COOKIE })).json();
  expect(recorded.body).toEqual({ change_out: "26,00", equipment: ["card_machine:3"] });
});

test("Agora não fecha o formulário sem registrar nada", async ({ page }) => {
  await page.goto("/WEB-261116-R05");
  await page.locator("[data-courier-separate]").click();
  await page.locator("[data-courier-separate-keep]").click();
  await expect(page.locator("[data-courier-separate-form]")).toHaveCount(0);
  const recorded = await (await page.request.get(`${MOCK}/api/v1/backstage/e2e/custody/`, { headers: COOKIE })).json();
  expect(recorded.body).toBeNull();
});
