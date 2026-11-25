import { expect, test, type Page } from "@playwright/test";

// #2500: a TaOn retomou a corrida que constava como encerrada, e o troco e a
// maquininha tinham voltado para a casa. No Painel do pedido, o aviso diz o que
// voltou e o "Separar de novo" registra os dois pela MESMA rota da casa
// (`courier-custody`). O cenário mora no mock (cookie `e2e_custody=on`).
const MOCK = `http://127.0.0.1:${Number(process.env.MOCK_PORT || 8796)}`;
// O estado da custódia no mock é um por teste (`e2e_ns`): o `beforeEach` de um teste
// não limpa o que outro, rodando ao mesmo tempo, acabou de gravar (#3623).
let COOKIE = { cookie: "e2e_custody=on" };

/**
 * Abre o pedido e espera o Vue montar. O HTML do servidor já mostra o aviso e o botão
 * "Separar de novo", mas o clique dado antes da hidratação se perde: o formulário não
 * abre e o teste caía em 9 de 20 rodadas (#3623, derrubou a fila duas vezes em
 * 25/11/2026). O `#__nuxt` só ganha o `__vue_app__` quando a montagem termina.
 */
async function openOrder(page: Page) {
  await page.goto("/WEB-261116-R05");
  await page.waitForFunction(
    () => Boolean((document.querySelector("#__nuxt") as { __vue_app__?: unknown } | null)?.__vue_app__),
  );
}

test.beforeEach(async ({ context, page, baseURL }, testInfo) => {
  const ns = `custody-${testInfo.testId}-${testInfo.repeatEachIndex}-${testInfo.retry}`.replace(/[^\w-]/g, "-");
  COOKIE = { cookie: `e2e_custody=on; e2e_ns=${ns}` };
  await context.addCookies([
    { name: "e2e_custody", value: "on", url: baseURL! },
    { name: "e2e_ns", value: ns, url: baseURL! },
  ]);
  await page.request.delete(`${MOCK}/api/v1/backstage/e2e/custody/`, { headers: COOKIE });
});

test("Separar de novo: o aviso diz o que voltou e o gesto manda o troco e a maquininha", async ({ page }) => {
  await openOrder(page);
  const notice = page.locator("[data-courier-custody-missing]");
  await expect(notice).toContainText("O troco e a maquininha voltaram para a casa");
  await expect(notice).toContainText("A TaOn retomou a corrida. Separe de novo antes de entregar a sacola.");
  await notice.locator("[data-courier-separate]").click();
  const form = page.locator("[data-courier-separate-form]");
  await expect(form).toBeVisible();
  const go = form.locator("[data-courier-separate-go]");
  await expect(go).toHaveText("Separar R$ 26,00 e a maquininha Azul");
  // A caixa do botão pode estar zerada no instante em que o texto confere (a tela
  // ainda monta ou relê o pedido): ler a altura uma vez só derrubou a fila duas vezes
  // em 25/11/2026 (#3623). Espera o botão visível e habilitado, e a altura assentar.
  await expect(go).toBeVisible();
  await expect(go).toBeEnabled();
  await expect
    .poll(async () => (await go.boundingBox())?.height ?? 0, { timeout: 5_000 })
    .toBeGreaterThanOrEqual(44);
  await go.click();
  await expect(notice).toHaveCount(0);
  const recorded = await (await page.request.get(`${MOCK}/api/v1/backstage/e2e/custody/`, { headers: COOKIE })).json();
  expect(recorded.body).toEqual({ change_out: "26,00", equipment: ["card_machine:3"] });
});

test("Agora não fecha o formulário sem registrar nada", async ({ page }) => {
  await openOrder(page);
  await page.locator("[data-courier-separate]").click();
  await page.locator("[data-courier-separate-keep]").click();
  await expect(page.locator("[data-courier-separate-form]")).toHaveCount(0);
  const recorded = await (await page.request.get(`${MOCK}/api/v1/backstage/e2e/custody/`, { headers: COOKIE })).json();
  expect(recorded.body).toBeNull();
});
