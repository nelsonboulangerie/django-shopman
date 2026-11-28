// JORNADA J4 — a grade ouve o estoque (EXCELENCIA-PDV WP-E4, P1-2).
//
// Dois dispositivos do mesmo balcão. A Fran vende a última unidade de um pão no
// dispositivo A; o dispositivo B, sem ninguém tocar nele, mostra o tile do pão
// "Esgotado" em até 5 s. Antes do WP-E4 o PDV não assinava o estoque: o selo só
// mudava quando o próprio balcão vendia ou salvava, e o cabeçalho dizia "Ao vivo".
// O mesmo B continua vendendo o que é feito na hora (o café): esgotar o pão não
// trava a grade.
//
// Roda contra um PDV de verdade (Django semeado + pos-nuxt). Antes, deixe UMA
// unidade do pão escolhido no estoque do canal do PDV (receita no README).
import { expect, test, type Browser, type Page } from "@playwright/test";

const LAST_UNIT = process.env.PDV_LIVE_LAST_UNIT || "Baguete Gergelim";
const MADE_TO_ORDER = process.env.PDV_LIVE_MADE_TO_ORDER || "Cappuccino";
const SHOTS = process.env.PDV_LIVE_SHOTS || "";
// O roteiro do plano: "em até 5 s, sem toque".
const LIVE_BUDGET_MS = 5_000;

// Roteiro manual (README, "Jornada J4"): o login vem de PDV_LIVE_USER/PDV_LIVE_PASSWORD e a
// última unidade do pão é preparada à mão. O `run_pos_e2e_live.sh` a pega pelo nome jN-*;
// sem o preparo, ela entrava com usuário vazio e virava vermelho falso (#3295).
test.skip(
  !process.env.PDV_LIVE_USER || !process.env.PDV_LIVE_PASSWORD,
  "a J4 pede o login e a última unidade preparados à mão (README, Jornada J4)",
);

async function login(page: Page) {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  const user = page.getByPlaceholder("Usuário");
  if (await user.isVisible({ timeout: 8000 }).catch(() => false)) {
    const enter = page.getByRole("button", { name: "Entrar" });
    // Campo SSR antes da hidratação não liga o v-model: repete até o botão acordar.
    await expect(async () => {
      await user.fill(process.env.PDV_LIVE_USER || "");
      await page.getByPlaceholder("Senha").fill(process.env.PDV_LIVE_PASSWORD || "");
      await expect(enter).toBeEnabled({ timeout: 1000 });
    }).toPass({ timeout: 20_000 });
    await enter.click();
  }
  const station = page.getByRole("button", { name: /^É este balcão|^Vincular a este posto|^Vincular também a este posto/ });
  const board = page.getByRole("button", { name: /Próxima livre/ });
  await station.or(board).first().waitFor({ timeout: 30_000 });
  await expect(async () => {
    if (await station.first().isVisible().catch(() => false)) await station.first().click({ timeout: 2000 });
    await board.waitFor({ timeout: 3000 });
  }).toPass({ timeout: 40_000 });
}

async function openFreshTab(page: Page) {
  await expect(async () => {
    const back = page.getByRole("button", { name: "Voltar para comandas" });
    if (await back.isVisible().catch(() => false)) await back.click();
    await page.getByRole("button", { name: /Próxima livre/ }).click({ timeout: 3000 });
    await page.getByPlaceholder(/Buscar produto/).waitFor({ timeout: 3000 });
  }).toPass({ timeout: 30_000 });
}

function exact(text: string) {
  return new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
}

/** O tile do produto na grade, com a busca filtrando só ele. */
async function tileOf(page: Page, name: string) {
  await page.getByPlaceholder(/Buscar produto/).fill(name);
  const tile = page.locator("button[data-pos-product]").filter({ hasText: exact(name) }).first();
  await tile.waitFor({ timeout: 15_000 });
  return tile;
}

async function device(browser: Browser, label: string) {
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const page = await context.newPage();
  page.on("response", (response) => {
    if (response.status() >= 400) console.log(`  [${label} ${response.status()}] ${response.request().method()} ${response.url()}`);
  });
  await login(page);
  return page;
}

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/j4-${name}.png` });
}

test("J4: a última unidade vendida num dispositivo vira Esgotado no outro, sem toque", async ({ browser }) => {
  const a = await device(browser, "A");
  const b = await device(browser, "B");

  // O cabeçalho só diz "Ao vivo" com o push de pé: é a promessa que este WP cumpre.
  // O selo mostra só a hora da leitura; "Ao vivo" é o nome acessível dele.
  await expect(b.getByRole("status", { name: /^Ao vivo/ }).first()).toBeVisible({ timeout: 30_000 });

  await openFreshTab(b);
  const tileB = await tileOf(b, LAST_UNIT);
  await expect(tileB, `${LAST_UNIT} precisa começar com saldo (receita no README)`).toBeEnabled();
  await shot(b, "b-antes");

  // A Fran vende a última unidade no A, em dinheiro.
  await openFreshTab(a);
  await (await tileOf(a, LAST_UNIT)).click();
  await a.getByRole("button", { name: /^Pagamento/ }).first().click();
  await a.getByRole("button", { name: /^Dinheiro/ }).and(a.locator(":enabled")).first().click();
  const finish = a.getByRole("button", { name: /^Validar|^Concluir|^Finalizar/ }).and(a.locator(":enabled")).first();
  await finish.click();
  const sold = Date.now();

  // O B não é tocado. O tile vira "Esgotado" sozinho.
  await expect(tileB).toBeDisabled({ timeout: LIVE_BUDGET_MS });
  await expect(tileB).toContainText("Esgotado", { timeout: 1000 });
  const ms = Date.now() - sold;
  console.log(`B mostrou "Esgotado" ${ms} ms depois da venda no A, sem toque`);
  await shot(b, "b-depois");
  expect(ms).toBeLessThanOrEqual(LIVE_BUDGET_MS);

  // O feito na hora continua vendendo no B: esgotar o pão não trava a grade.
  const coffee = await tileOf(b, MADE_TO_ORDER);
  await expect(coffee).toBeEnabled();
  await coffee.click();
  await expect(b.getByText(exact(MADE_TO_ORDER)).first()).toBeVisible();
});
