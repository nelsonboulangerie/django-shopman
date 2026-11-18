// JORNADA J5 — encomenda de outro dia acima do plano (EXCELENCIA-PDV WP-E2, D-041).
//
// A Caixa (Fran) monta uma encomenda de 200 Baguette de Tradition para amanhã, com
// 22 planejadas no seed. A linha mostra a fornada da data; o Validar fica travado com
// os dois números e pede o gerente; sem a assinatura nada fecha; a Gerente (Joyce),
// escolhida da lista, vê os dois números no diálogo e assina com o próprio PIN; "Na
// retirada" não aparece para outro dia. Tudo pela tela, no celular (375 px) e no
// balcão (1366 px). Como rodar: README.md desta pasta.
//
// O seed planeja 22 Baguette de Tradition para amanhã. Cada execução consome parte do
// livre da data (a encomenda fecha), e o teste lê o plano na tela, sem supor o livre:
// a frase da linha e a do Validar trazem "22 planejadas" enquanto o seed for o mesmo.
import { capture, cast, expect, settled, test, type Page } from "./support/operator";

const PRODUCT = process.env.PDV_LIVE_OVER_PLAN_PRODUCT || "Baguette de Tradition";
const PLANNED = process.env.PDV_LIVE_OVER_PLAN_PLANNED || "22";
const CUSTOMER = process.env.PDV_LIVE_OVER_PLAN_CUSTOMER || "Ana Ferreira";
const CUSTOMER_PHONE = process.env.PDV_LIVE_OVER_PLAN_PHONE || "43995555555";
const QTY = "200";

function exact(text: string) {
  return new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
}

/** Amanhã no relógio da loja (o navegador roda em America/Sao_Paulo): `19/11`. */
function tomorrow(): string {
  const now = new Date(new Date().toLocaleString("en-US", { timeZone: "America/Sao_Paulo" }));
  now.setDate(now.getDate() + 1);
  return `${String(now.getDate()).padStart(2, "0")}/${String(now.getMonth() + 1).padStart(2, "0")}`;
}

async function opensOrder(page: Page) {
  // A porta da encomenda é a seção Encomendas (rail no balcão, barra de baixo no
  // celular), e de lá "Nova encomenda".
  await page.getByRole("link", { name: /^Encomendas/ }).locator("visible=true").first().click();
  await settled(page);
  await page.getByRole("button", { name: /^Nova( encomenda)?$/ }).locator("visible=true").first().click({ timeout: 30_000 });
  // "Iniciar nova encomenda?": a próxima comanda livre fica em uso para montá-la.
  const start = page.getByRole("dialog", { name: "Iniciar nova encomenda?" });
  const heading = page.getByRole("heading", { name: /Nova encomenda|Preparar encomenda/ });
  await expect(async () => {
    if (await start.isVisible().catch(() => false)) {
      await start.getByRole("button", { name: "Iniciar encomenda", exact: true }).click({ timeout: 2000 });
    }
    await expect(heading).toBeVisible({ timeout: 2000 });
  }).toPass({ timeout: 60_000 });
}

async function identifiesCustomer(page: Page) {
  await page.getByRole("button", { name: "Identificar cliente" }).locator("visible=true").first().click();
  const search = page.getByPlaceholder("Buscar por nome, telefone, CPF ou e-mail").locator("visible=true").first();
  await search.click();
  await search.pressSequentially(CUSTOMER_PHONE);
  const dialog = page.getByRole("dialog").filter({ has: page.getByPlaceholder("Buscar por nome, telefone, CPF ou e-mail") });
  await dialog.getByRole("option", { name: exact(CUSTOMER) }).first().click({ timeout: 30_000 });
  // Escolher o cadastro pode fechar o diálogo sozinho; se não fechar, "Concluir".
  const done = dialog.getByRole("button", { name: "Concluir", exact: true });
  await expect(async () => {
    if (await done.isVisible().catch(() => false)) await done.click({ timeout: 2000 });
    await expect(dialog).toBeHidden({ timeout: 2000 });
  }).toPass({ timeout: 30_000 });
}

async function schedulesTomorrowPickup(page: Page) {
  await page.locator('[data-order-fulfillment="pickup"]').locator("visible=true").first().click();
  await page.getByRole("radio", { name: /^Amanhã/ }).locator("visible=true").first().click();
  const slot = page
    .locator('[data-order-step="schedule"]')
    .getByRole("button")
    .filter({ hasText: /\d{1,2}h|\d{2}:\d{2}/ })
    .and(page.locator(":enabled"))
    .first();
  await slot.click({ timeout: 30_000 });
  await page.getByRole("button", { name: /Montar encomenda/ }).click();
  await expect(page.getByPlaceholder(/Buscar produto/).locator("visible=true").first()).toBeVisible({ timeout: 30_000 });
}

/** Lança o produto e digita a quantidade no editor da linha. */
async function ordersQuantity(page: Page) {
  const search = page.getByPlaceholder(/Buscar produto/).locator("visible=true").first();
  await search.click();
  await search.pressSequentially(PRODUCT);
  await page.locator("button[data-pos-product]").filter({ hasText: exact(PRODUCT) }).first().click({ timeout: 30_000 });
  // A baguete fica pronta mais tarde que o turno escolhido: a tela oferece o turno
  // dela, e a Fran aceita (é o que o cliente ouviria).
  const later = page.getByRole("button", { name: /^Mudar para/ }).locator("visible=true").first();
  if (await later.waitFor({ timeout: 5000 }).then(() => true, () => false)) await later.click();
  // No celular a comanda é a folha de baixo: abre para ver a linha.
  const sheet = page.getByRole("button", { name: "Ver a comanda" }).locator("visible=true").first();
  if (await sheet.isVisible().catch(() => false)) await sheet.click();
  await page.locator("[data-item-select]").locator("visible=true").first().click();
  const touch = page.locator("[data-pos-touch-editor]").locator("visible=true").first();
  if (await touch.waitFor({ timeout: 3000 }).then(() => true, () => false)) {
    // Toque: o numérico da linha escreve a quantidade, e "Pronto" fecha.
    const editor = page.locator("[data-pos-line-editor]").locator("visible=true").first();
    for (const digit of QTY) await editor.getByRole("button", { name: `Dígito ${digit}`, exact: true }).click();
    await editor.locator("[data-pos-line-editor-close]").click();
  } else {
    // Balcão: o teclado físico digita a quantidade da linha aberta.
    await page.keyboard.type(QTY);
    await page.keyboard.press("Enter");
  }
}

test.describe.configure({ mode: "serial" });

for (const device of ["phone", "counter"] as const) {
  test.describe(`J5 Encomenda acima do plano · ${device === "phone" ? "375 px" : "1366 px"}`, () => {
    test.use({ device });

    test("200 baguetes para amanhã contra 22 planejadas: só o gerente libera", async ({ cashierAtCounter: page }, testInfo) => {
      test.setTimeout(8 * 60_000);
      const day = tomorrow();

      await opensOrder(page);
      await identifiesCustomer(page);
      await schedulesTomorrowPickup(page);
      await capture(page, testInfo, "encomenda-para-amanha");

      await ordersQuantity(page);
      // 1 · A linha mostra a fornada da data e que o pedido passa dela.
      const fact = page.locator('[data-pos-line-plan="over"]').locator("visible=true").first();
      await expect(fact).toContainText(`Passa do plano: ${PLANNED} planejadas para ${day}`, { timeout: 30_000 });
      await capture(page, testInfo, "linha-passa-do-plano");

      // 2 · No Pagamento: o aviso que trava diz os dois números; "Na retirada" não existe.
      // O Pagamento de sempre (no celular, "Outras formas" da folha da comanda).
      await page.getByRole("button", { name: /^Pagamento|^Outras formas/ }).locator("visible=true").first().click();
      await expect(page.getByRole("button", { name: /^Dinheiro/ }).locator("visible=true").first()).toBeVisible({ timeout: 30_000 });
      await expect(page.getByRole("button", { name: "Na retirada" })).toHaveCount(0);
      await page.getByRole("button", { name: /^Dinheiro/ }).and(page.locator(":enabled")).locator("visible=true").first().click();
      // Escolhida a forma, o que segura o botão é o plano, com os dois números.
      const block = page.getByText("A encomenda passa do plano. Só o gerente libera.").locator("visible=true").first();
      await expect(block).toBeVisible({ timeout: 30_000 });
      await expect(page.getByText(`${PRODUCT}: ${QTY} pedidas, ${PLANNED} planejadas para ${day}`).locator("visible=true").first()).toBeVisible();
      const ask = page.getByRole("button", { name: /^Pedir autorização/ }).locator("visible=true").first();
      await expect(ask).toBeEnabled({ timeout: 30_000 });
      await capture(page, testInfo, "validar-travado");

      // 3 · Sem a assinatura não fecha: o diálogo abre, a Fran fecha, nada muda.
      await ask.click();
      const dialog = page.getByRole("dialog", { name: "Autorizar a venda" });
      await expect(dialog).toBeVisible({ timeout: 30_000 });
      await expect(dialog.locator("[data-over-plan-context]")).toContainText(`${QTY} pedidas, ${PLANNED} planejadas para ${day}`);
      // A captura espera a animação de entrada do diálogo terminar.
      await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running"));
      await capture(page, testInfo, "gerente-ve-os-numeros");
      await page.keyboard.press("Escape");
      await expect(dialog).toBeHidden();
      await expect(block).toBeVisible();
      await expect(ask).toBeVisible();

      // 4 · A Gerente, escolhida da lista, assina com o próprio PIN, e a encomenda fecha.
      await ask.click();
      await expect(dialog).toBeVisible({ timeout: 30_000 });
      await dialog.getByRole("button", { name: new RegExp(cast.manager.name) }).first().click();
      for (const digit of cast.manager.pin) {
        await dialog.getByRole("button", { name: digit, exact: true }).click();
      }
      const confirm = dialog.getByRole("button", { name: /^Confirmar|^Autorizar/ }).first();
      if (await confirm.isVisible({ timeout: 2000 }).catch(() => false)) await confirm.click();
      await expect(dialog).toBeHidden({ timeout: 60_000 });
      await expect(page.getByText(/Encomenda registrada|CONFIRME COM O CLIENTE|Confirme com o cliente/).locator("visible=true").first())
        .toBeVisible({ timeout: 60_000 });
      await capture(page, testInfo, "encomenda-registrada");
    });
  });
}
