// WP-F04 · Letreiro a dois metros (J-P8): a estação abre o Letreiro numa TV de
// 1920 × 1080 e num tablet de 1024; a linha se lê de longe, a massa aparece em
// quilo e, sem conexão, o aviso com a hora da leitura é a maior coisa da tela.
import { expect, test, type Page } from "@playwright/test";

const SCREENS: Record<string, { minRowPx: number }> = {
  // 5vh numa TV de 1080 = 54 px; a largura dos nomes do dia pode segurar um pouco.
  "chromium-tv-full-hd": { minRowPx: 40 },
  "chromium-tablet-landscape": { minRowPx: 20 },
};

const cookie = (name: string, value: string) => ({
  name,
  value,
  domain: "127.0.0.1",
  path: "/",
});

async function rowFontPx(page: Page): Promise<number> {
  return page
    .locator("[data-board-row]")
    .first()
    .evaluate((row) => {
      const flap = row.querySelector(".flap-word") as HTMLElement;
      return Number.parseFloat(getComputedStyle(flap).fontSize);
    });
}

test.beforeEach(({}, testInfo) => {
  test.skip(!(testInfo.project.name in SCREENS), "Letreiro: TV de 1080 e tablet de 1024");
});

test("lê produto, quantidade com a unidade certa, hora e situação", async ({
  context,
  page,
}, testInfo) => {
  await context.addCookies([
    cookie("e2e_session", "authed"),
    cookie("e2e_scenario", "populated"),
  ]);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/board");
  await expect(page.getByRole("heading", { name: "Letreiro" })).toBeVisible();

  const dough = page.getByRole("article", {
    name: "Massa de croissant: 18,5 kg às 6h, Atrasado",
  });
  await expect(dough).toBeVisible();
  await expect(dough.locator('.flap-word[aria-label="18,5 KG"]')).toHaveCount(1);
  await expect(
    page.getByRole("article", { name: "Croissant Manteiga: 120 unidades às 7h, Previsto" }),
  ).toBeVisible();

  const { minRowPx } = SCREENS[testInfo.project.name]!;
  expect(await rowFontPx(page)).toBeGreaterThanOrEqual(minRowPx);

  // A linha cabe na largura: nada vaza para fora da tela.
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);

  await testInfo.attach(`letreiro-${testInfo.project.name}`, {
    body: await page.screenshot(),
    contentType: "image/png",
  });
});

test("sem conexão, o quadro fica e o aviso diz de quando é", async ({
  context,
  page,
}, testInfo) => {
  await context.addCookies([
    cookie("e2e_session", "authed"),
    cookie("e2e_scenario", "populated"),
  ]);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.clock.install({ time: new Date("2026-11-23T06:45:00-03:00") });
  await page.goto("/board");
  await expect(page.locator("[data-board-row]").first()).toBeVisible();

  await context.addCookies([cookie("e2e_forecast", "down")]);
  await page.clock.runFor(40_000);

  const notice = page.locator("[data-board-stale]");
  await expect(notice.locator("[data-board-stale-text]")).toHaveText(
    "Sem conexão. Lido às 6h42",
  );
  await expect(page.locator("[data-board-row]").first()).toBeVisible();

  const noticePx = await notice.evaluate((el) =>
    Number.parseFloat(getComputedStyle(el).fontSize),
  );
  expect(noticePx).toBeGreaterThan(await rowFontPx(page));

  await testInfo.attach(`letreiro-sem-conexao-${testInfo.project.name}`, {
    body: await page.screenshot(),
    contentType: "image/png",
  });
});

test("o aviso de conexão fecha no X e volta enquanto a conexão seguir caída", async ({
  context,
  page,
}) => {
  await context.addCookies([
    cookie("e2e_session", "authed"),
    cookie("e2e_scenario", "populated"),
  ]);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.clock.install({ time: new Date("2026-11-23T06:45:00-03:00") });
  await page.goto("/board");
  await expect(page.locator("[data-board-row]").first()).toBeVisible();

  await context.addCookies([cookie("e2e_forecast", "down")]);
  await page.clock.runFor(40_000);
  const notice = page.locator("[data-board-stale]");
  await expect(notice).toBeVisible();

  await notice.getByRole("button", { name: "Fechar aviso" }).click();
  await expect(notice).toHaveCount(0);
  // O quadro lido continua; o aviso volta na próxima leitura que falha (ou em 1 min).
  await expect(page.locator("[data-board-row]").first()).toBeVisible();
  await page.clock.runFor(75_000);
  await expect(notice).toBeVisible();

  // A conexão voltou: o aviso some sozinho.
  await context.clearCookies({ name: "e2e_forecast" });
  await page.clock.runFor(150_000);
  await expect(notice).toHaveCount(0);
});
