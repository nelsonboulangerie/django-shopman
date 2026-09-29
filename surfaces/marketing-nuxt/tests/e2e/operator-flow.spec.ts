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
  await expect(page).toHaveURL(/\/v2\?area=today/);
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "Uma campanha, consequências honestas em cada destino",
    }),
  ).toBeVisible();
}

test("operador entra e alcança os três postos de trabalho sem redigitação", async ({
  page,
}) => {
  await enterAsSyntheticOperator(page);

  await page
    .getByRole("link", { name: "Campanhas", exact: true })
    .first()
    .click();
  await expect(page).toHaveURL(/\/v2\?area=campaigns/);
  await expect(
    page.getByRole("heading", {
      level: 2,
      name: "Planeje uma vez, adapte por destino",
    }),
  ).toBeVisible();
  await expect(page.getByText("Fornada artesanal 01")).toBeVisible();

  await page.getByRole("link", { name: "Nova campanha" }).click();
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

  await page
    .getByRole("link", { name: "Plataformas", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("heading", {
      level: 2,
      name: "Plataformas possíveis e situação real",
    }),
  ).toBeVisible();
  await expect(
    page.getByText("Instagram", { exact: true }).first(),
  ).toBeVisible();

  await page.getByRole("link", { name: "Hoje", exact: true }).click();
  await expect(
    page.getByRole("heading", { level: 2, name: "O que pede sua atenção" }),
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
    page.getByRole("heading", {
      level: 1,
      name: "Uma campanha, consequências honestas em cada destino",
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Campanhas", exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Plataformas", exact: true }).first(),
  ).toBeVisible();
  const v2Navigation = page.getByRole("navigation", {
    name: "Seções do Marketing",
  });
  await expect(
    v2Navigation.getByRole("link", { name: "Hoje", exact: true }),
  ).toBeVisible();
  await expect(
    v2Navigation.getByRole("link", {
      name: "Ofertas e cupons",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Áreas do Marketing V2" }),
  ).toHaveCount(0);
});

test("Plataformas usa detalhe modal e volta para a área canônica", async ({
  page,
}) => {
  await enterAsSyntheticOperator(page);

  await page.goto("/platforms");
  await expect(page).toHaveURL(/\/v2\?area=platforms/);

  const googleCard = page.locator("li").filter({ hasText: "Google" }).first();
  await googleCard
    .getByRole("link", { name: "Ver conexão e configuração" })
    .click();

  await expect(page).toHaveURL(/\/platforms\?.*platform=google_business/);
  const dialog = page.getByRole("dialog").last();
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("heading", { name: "Google" })).toBeVisible();
  await dialog.getByRole("button", { name: "Fechar" }).click();

  await expect(page).toHaveURL(/\/v2\?area=platforms/);
  await expect(
    page.locator('[data-marketing-platform="google_business"]'),
  ).toBeFocused();
  await expect(
    page.getByRole("heading", {
      level: 2,
      name: "Plataformas possíveis e situação real",
    }),
  ).toBeVisible();
});

test("composer usa modal amplo no desktop", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await enterAsSyntheticOperator(page);
  await page.goto("/v2?area=campaigns");
  await page.getByRole("link", { name: "Nova campanha" }).click();

  const dialog = page.getByRole("dialog").last();
  await expect(dialog).toBeVisible();
  const box = await dialog.boundingBox();
  expect(box).not.toBeNull();
  expect(box?.width).toBeGreaterThanOrEqual(1100);
  expect(box?.height).toBeGreaterThanOrEqual(800);
});

test("V2 mostra Google e abre o composer funcional com a oferta escolhida", async ({
  page,
}) => {
  await enterAsSyntheticOperator(page);
  await page.goto("/v2?area=campaigns");

  await expect(page.getByText("Google", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Atualização · Evento · Oferta")).toBeVisible();

  await page.goto("/v2?area=offers");
  const useOffer = page.getByRole("link", {
    name: "Criar campanha com esta oferta",
  });
  await expect(useOffer).toBeVisible();
  await useOffer.click();

  await expect(page).toHaveURL(/\/campaigns\?.*experience=v2/);
  const editor = page.getByRole("dialog").last();
  await expect(editor).toBeVisible();
  await editor.getByLabel("Nome da campanha").fill("Primavera · Hibisco");
  await editor.getByRole("button", { name: "2. Destinos" }).click();
  const google = editor.getByRole("checkbox", { name: /Google/ });
  await expect(google).toBeVisible();
  await google.click();
  await editor.getByRole("button", { name: "3. Conteúdo" }).click();
  await expect(editor.getByLabel("Anunciar a oferta")).toHaveValue(
    "hibisco-primavera",
  );
});

test("entrada V2 liga ou desliga campanha com CAS e recuperação de conflito", async ({
  page,
}) => {
  await enterAsSyntheticOperator(page);
  await page.goto("/v2");
  await page
    .getByRole("link", { name: "Campanhas", exact: true })
    .first()
    .click();
  await page.getByRole("link", { name: "Gerenciar todas" }).click();

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
  await page
    .getByRole("link", { name: "Campanhas", exact: true })
    .first()
    .click();
  await page.getByRole("link", { name: "Gerenciar todas" }).click();
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

  await expect(page).toHaveURL(
    /\/announcements\/77\?dispatch=new&experience=v2#review/,
  );
  await expect(
    page
      .getByRole("navigation", { name: "Seções do Marketing" })
      .getByRole("link", { name: "Ofertas e cupons", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Este anúncio acabou de ser criado pelo seu disparo"),
  ).toBeVisible();
  await expect(page.getByText(/Nada foi disparado ainda/)).toBeVisible();
});
