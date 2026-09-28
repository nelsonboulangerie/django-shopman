import { expect, test, type Page } from "@playwright/test";

async function enterAsSyntheticOperator(page: Page) {
  await page.context().addCookies([
    {
      name: "visual_scenario",
      value: "login-anonymous",
      domain: "127.0.0.1",
      path: "/",
    },
  ]);
  await page.goto("/");
  const username = page.getByLabel("Usuário");
  await expect(username).toBeFocused();
  await username.fill("operadora-e2e");
  await page.getByLabel("Senha").fill("senha-sintética");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Painel" }),
  ).toBeVisible();
}

test("operador entra e alcança os três postos de trabalho sem redigitação", async ({
  page,
}) => {
  await enterAsSyntheticOperator(page);

  await page.getByRole("link", { name: "Campanhas", exact: true }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Campanhas" }),
  ).toBeVisible();
  await expect(page.getByText("Fornada artesanal 01")).toBeVisible();

  await page.getByRole("button", { name: "Nova campanha" }).click();
  const editor = page.getByRole("dialog").last();
  await expect(editor).toBeVisible();
  await expect(editor.getByLabel("Nome da campanha")).toBeVisible();
  await editor.getByLabel("Nome da campanha").fill("Campanha E2E");
  await editor.getByRole("button", { name: "2. Destinos" }).click();
  await editor.getByRole("checkbox", { name: /Instagram/ }).click();
  await editor.getByRole("button", { name: "3. Conteúdo" }).click();
  await expect(editor.getByLabel("Usar o modelo")).toBeVisible();
  await editor.getByRole("button", { name: "4. Público e momento" }).click();
  await expect(editor.getByText("Revisar antes de publicar")).toBeVisible();
  await editor.getByRole("button", { name: "5. Revisar" }).click();
  await expect(
    editor.getByTestId("campaign-compositions").locator("li"),
  ).toHaveCount(1);
  await expect(
    editor.getByRole("button", { name: "Criar campanha" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(editor).toBeHidden();

  await page.getByRole("link", { name: "Plataformas", exact: true }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Plataformas" }),
  ).toBeVisible();
  await expect(
    page.getByText("Instagram", { exact: true }).first(),
  ).toBeVisible();

  await page.getByRole("link", { name: "Painel", exact: true }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Painel" }),
  ).toBeVisible();
});

test("entrada V2 preserva o painel operacional autenticado", async ({
  page,
}) => {
  await enterAsSyntheticOperator(page);

  await page.goto("/v2");

  await expect(page).toHaveURL(/\/v2$/);
  await expect(page.locator('[data-marketing-experience="v2"]')).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 1, name: "Painel" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Campanhas", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Plataformas", exact: true }),
  ).toBeVisible();
});

test("entrada V2 liga ou desliga campanha com CAS e recuperação de conflito", async ({
  page,
}) => {
  await enterAsSyntheticOperator(page);
  await page.goto("/v2");
  await page.getByRole("link", { name: "Campanhas", exact: true }).click();

  const activation = page.getByRole("switch", {
    name: "Desligar a campanha Fornada artesanal 01",
  });
  await expect(activation).toBeEnabled();
  const conflict = page.getByText(/mudou em outra sessão/);
  await expect(async () => {
    await activation.click();
    await expect(conflict).toBeVisible({ timeout: 1_000 });
  }).toPass({ timeout: 15_000, intervals: [250, 500, 1_000] });
  await expect(activation).toHaveAttribute("aria-checked", "true");
});

test("entrada V2 prepara disparo idempotente e leva o receipt à revisão", async ({
  page,
}) => {
  await enterAsSyntheticOperator(page);
  await page.context().addCookies([
    {
      name: "visual_scenario",
      value: "fire-accepted",
      domain: "127.0.0.1",
      path: "/",
    },
  ]);
  await page.goto("/v2");
  await page.getByRole("link", { name: "Campanhas", exact: true }).click();
  const prepare = page.getByRole("button", {
    name: /Preparar o disparo da campanha Fornada artesanal 01/,
  });
  const fireDialog = page.getByRole("dialog");
  // Em runner carregado, o HTML SSR pode ficar acionável um instante antes de o
  // Vue anexar o handler. Retry exige a consequência do gesto e não mascara um
  // botão quebrado: sem diálogo depois da hidratação, a asserção continua falhando.
  await expect(async () => {
    await prepare.click();
    await expect(fireDialog).toBeVisible({ timeout: 1_000 });
  }).toPass({ timeout: 15_000, intervals: [250, 500, 1_000] });
  await expect(page.getByText("Contando…")).toHaveCount(0);
  const review = page.getByRole("button", { name: "Revisar anúncio" });
  await expect(review).toBeEnabled();
  await review.click();

  await expect(page).toHaveURL(/\/announcements\/77\?dispatch=new#review/);
  await expect(
    page.getByText("Este anúncio acabou de ser criado pelo seu disparo"),
  ).toBeVisible();
  await expect(page.getByText(/Nada foi disparado ainda/)).toBeVisible();
});
