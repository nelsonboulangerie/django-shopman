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
  // A casa do Marketing é a fila de decisões (decisão do dono, 03/10/2026).
  await expect(page).toHaveURL(/127\.0\.0\.1:\d+\/$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Decisões" }),
  ).toBeVisible();
}

// No celular as quatro seções moram na barra do pé da tela.
function mobileSections(page: Page) {
  return page.getByRole("navigation", {
    name: "Seções do Marketing no celular",
  });
}

test("operador entra e alcança os três postos de trabalho sem redigitação", async ({
  page,
}) => {
  await enterAsSyntheticOperator(page);

  await mobileSections(page)
    .getByRole("link", { name: "Ajustes", exact: true })
    .click();
  await expect(page).toHaveURL(/\/campaigns$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Campanhas" }),
  ).toBeVisible();
  await expect(page.getByText("Fornada artesanal 01")).toBeVisible();

  await page.getByRole("button", { name: /^Nova campanha/ }).filter({ visible: true }).first().click();
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
    page.getByRole("heading", { level: 1, name: "Plataformas" }),
  ).toBeVisible();
  await expect(
    page.getByText("Instagram", { exact: true }).first(),
  ).toBeVisible();

  await mobileSections(page)
    .getByRole("link", { name: /^Decisões/ })
    .click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Decisões" }),
  ).toBeVisible();
});

test("a fila de decisões leva cada cartão ao lugar exato da decisão", async ({
  page,
}) => {
  await enterAsSyntheticOperator(page);
  await page.context().addCookies([
    {
      name: "visual_scenario",
      value: "board-pending",
      domain: "127.0.0.1",
      path: "/",
    },
  ]);
  await page.goto("/");

  const cards = page.locator("[data-decision]");
  await expect(cards).toHaveCount(2);
  await expect(cards.first()).toContainText("Lote pronto: Pão artesanal");
  await expect(cards.nth(1)).toContainText("Falhou no Instagram · 1 postagem");
  await expect(
    page.getByText(/O sistema consultou sem reenviar: publicado/),
  ).toBeVisible();
  await expect(
    cards.first().getByRole("link", { name: /^Revisar:/ }),
  ).toHaveAttribute("href", "/announcements/41#review");

  // O sino não tem lista própria: ele é a mesma fila.
  await expect(
    page.getByRole("link", { name: "Decisões: 2 esperando você" }),
  ).toHaveAttribute("href", "/");

  await page.getByRole("link", { name: /agendado hoje/ }).click();
  await expect(page).toHaveURL(/\/scheduled$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Agendados" }),
  ).toBeVisible();
  await expect(page.getByText(/^Envia .*17:30$/)).toBeVisible();
});

test("Ajustes tem as próprias seções, uma rota por lugar", async ({
  page,
}) => {
  await enterAsSyntheticOperator(page);

  await page.goto("/offers");
  await expect(
    page.getByRole("heading", { level: 1, name: "Ofertas e cupons" }),
  ).toBeVisible();
  const settings = page.getByRole("navigation", { name: "Seções de Ajustes" });
  for (const name of ["Campanhas", "Modelos", "Ofertas e cupons", "Plataformas"]) {
    await expect(settings.getByRole("link", { name, exact: true })).toBeVisible();
  }
  await expect(
    settings.getByRole("link", { name: "Ofertas e cupons", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  // O endereço antigo do panorama não existe mais (pré-go-live: zero legado).
  const old = await page.goto("/v2");
  expect(old?.status()).toBe(404);
});

test("Plataformas usa detalhe modal e volta para a própria lista", async ({
  page,
}) => {
  await enterAsSyntheticOperator(page);

  await page.goto("/platforms");
  await expect(page).toHaveURL(/\/platforms$/);

  const google = page.locator('[data-marketing-platform="google_business"]');
  await google.click();

  const dialog = page.getByRole("dialog").last();
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("heading", { name: /Google/ })).toBeVisible();
  await dialog.getByRole("button", { name: "Fechar" }).click();

  await expect(page).toHaveURL(/\/platforms$/);
  await expect(google).toBeFocused();
  await expect(
    page.getByRole("heading", { level: 1, name: "Plataformas" }),
  ).toBeVisible();
});

test("composer usa modal amplo no desktop", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await enterAsSyntheticOperator(page);
  await page.goto("/campaigns");
  await page.getByRole("button", { name: /^Nova campanha/ }).filter({ visible: true }).first().click();

  const dialog = page.getByRole("dialog").last();
  await expect(dialog).toBeVisible();
  const box = await dialog.boundingBox();
  expect(box).not.toBeNull();
  expect(box?.width).toBeGreaterThanOrEqual(1100);
  expect(box?.height).toBeGreaterThanOrEqual(800);
});

test("a oferta abre o composer funcional com Google entre os destinos", async ({
  page,
}) => {
  await enterAsSyntheticOperator(page);
  await page.goto("/offers");
  const useOffer = page.getByRole("link", {
    name: "Criar campanha com esta oferta",
  });
  await expect(useOffer).toBeVisible();
  await useOffer.click();

  await expect(page).toHaveURL(/\/campaigns\?.*offer=hibisco-primavera/);
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

test("Campanhas liga ou desliga campanha com CAS e recuperação de conflito", async ({
  page,
}) => {
  await enterAsSyntheticOperator(page);
  await page.goto("/campaigns");

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

test("Campanhas prepara disparo idempotente e leva o receipt à revisão", async ({
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
  await page.goto("/campaigns");
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
    /\/announcements\/77\?dispatch=new#review/,
  );
  await expect(
    mobileSections(page).getByRole("link", { name: "Ajustes", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Este anúncio acabou de ser criado pelo seu disparo"),
  ).toBeVisible();
  await expect(page.getByText(/Nada foi disparado ainda/)).toBeVisible();
});
