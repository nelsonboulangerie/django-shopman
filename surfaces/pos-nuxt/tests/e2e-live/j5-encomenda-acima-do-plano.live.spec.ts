// JORNADA J5 — encomenda de outro dia acima do plano (EXCELENCIA-PDV WP-E2, D-041).
//
// A Caixa (Fran) monta uma encomenda de 200 Baguette de Tradition para o próximo dia
// em que a loja abre (amanhã, ou a próxima data quando amanhã é dia fechado, #2976),
// contra o lote que o seed planeja para essa data. A linha mostra a fornada da data; o Validar fica travado com
// os dois números e pede o gerente; sem a assinatura nada fecha; a Gerente (Joyce),
// escolhida da lista, vê os dois números no diálogo e assina com o próprio PIN; "Na
// retirada" não aparece para outro dia. Tudo pela tela, no celular (375 px) e no
// balcão (1366 px). Como rodar: README.md desta pasta.
//
// O seed planeja a Baguette de Tradition para cada dia aberto da semana: 22, ou 28 na
// sexta e no sábado (`seedPlannedQty`). A régua é o lote planejado PARA a data; a sobra de hoje (que o seed deixa na vitrine) não entra em nenhum número.
//
// WP-E3 estende a jornada com a data SEM plano (D2 do dono): a Fran abre uma encomenda
// para daqui a dez dias, quando o seed ainda não planejou lote nenhum, e lança 30
// croissants. O tile não diz "Sem saldo"; a linha diz "Ainda sem lote planejado para
// DD/MM: vira pedido à Produção", e a encomenda fecha sem gerente.
import { audits } from "./support/audit";
import { seedPlannedQty } from "./support/nextOpenDay";
import { capture, cast, expect, settled, test, type Page } from "./support/operator";
import { picksNextOpenDay, type ChosenDay } from "./support/schedule";

const PRODUCT = process.env.PDV_LIVE_OVER_PLAN_PRODUCT || "Baguette de Tradition";
/** O lote do seed para a data escolhida (`PDV_LIVE_OVER_PLAN_PLANNED` fixa outro número). */
const plannedFor = (day: ChosenDay) => process.env.PDV_LIVE_OVER_PLAN_PLANNED || String(seedPlannedQty(22, day.iso));
const CUSTOMER = process.env.PDV_LIVE_OVER_PLAN_CUSTOMER || "Ana Ferreira";
const CUSTOMER_PHONE = process.env.PDV_LIVE_OVER_PLAN_PHONE || "43995555555";
const QTY = "200";

function exact(text: string) {
  return new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
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
  const search = page.getByRole("combobox", { name: "Buscar cliente" }).locator("visible=true").first();
  await search.click();
  await search.pressSequentially(CUSTOMER_PHONE);
  const dialog = page.getByRole("dialog").filter({ has: page.getByRole("combobox", { name: "Buscar cliente" }) });
  await dialog.getByRole("option", { name: exact(CUSTOMER) }).first().click({ timeout: 30_000 });
  // Escolher o cadastro pode fechar o diálogo sozinho; se não fechar, "Concluir".
  const done = dialog.getByRole("button", { name: "Concluir", exact: true });
  await expect(async () => {
    if (await done.isVisible().catch(() => false)) await done.click({ timeout: 2000 });
    await expect(dialog).toBeHidden({ timeout: 2000 });
  }).toPass({ timeout: 30_000 });
}

// A ordem do funil (WP-E13, #2754): depois do cliente vem "para quando", e só
// então o recebimento.
async function schedulesNextOpenDayPickup(page: Page): Promise<ChosenDay> {
  const day = await picksNextOpenDay(page);
  const slot = page
    .locator('[data-order-step="schedule"]')
    .getByRole("button")
    .filter({ hasText: /\d{1,2}h|\d{2}:\d{2}/ })
    .and(page.locator(":enabled"))
    .first();
  await slot.click({ timeout: 30_000 });
  await page.getByRole("button", { name: "Continuar", exact: true }).click();
  await page.locator("[data-order-fulfillment-options]").getByRole("radio", { name: /^Retirada/ }).click();
  await page.getByRole("button", { name: /Montar encomenda/ }).click();
  await expect(page.getByPlaceholder(/Buscar produto/).locator("visible=true").first()).toBeVisible({ timeout: 30_000 });
  return day;
}

/**
 * Daqui a dez dias no relógio da loja, pulando o domingo (a casa não abre): a data do
 * laudo (P1-1). O seed planeja só a próxima semana, então a data não tem lote planejado.
 */
const MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

function tenDaysAhead(): { iso: string; day: string; cell: RegExp; month: string } {
  const now = new Date(new Date().toLocaleString("en-US", { timeZone: "America/Sao_Paulo" }));
  now.setDate(now.getDate() + 10);
  if (now.getDay() === 0) now.setDate(now.getDate() + 1);
  const dd = String(now.getDate()).padStart(2, "0");
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const month = `${MONTHS[now.getMonth()]} de ${now.getFullYear()}`;
  return { iso: `${now.getFullYear()}-${mm}-${dd}`, day: `${dd}/${mm}`, cell: new RegExp(`, ${now.getDate()} de ${month}$`), month };
}

/** "Outra data": a Fran escolhe o dia no calendário do kit, o turno, e monta a encomenda. */
async function schedulesPickupOn(page: Page, target: { cell: RegExp; month: string }) {
  await page.locator('[data-day-option="other"]').locator("visible=true").first().click();
  const calendar = page.getByRole("dialog", { name: /^Abrir calendário/ });
  if (!(await calendar.isVisible().catch(() => false))) {
    await page.getByRole("button", { name: /^Abrir calendário/ }).locator("visible=true").first().click();
  }
  await expect(calendar).toBeVisible({ timeout: 10_000 });
  const cell = calendar.getByRole("button", { name: target.cell }).and(calendar.locator(":not([data-outside-view]):not([data-disabled])")).first();
  // O mês da data pode ser o próximo: avança só se a célula não está na grade aberta.
  if (!(await cell.waitFor({ timeout: 3000 }).then(() => true, () => false))) {
    await calendar.getByRole("button", { name: "Próximo mês" }).click();
  }
  await cell.click();
  await expect(calendar).toBeHidden({ timeout: 10_000 });
  const slot = page
    .locator('[data-order-step="schedule"]')
    .getByRole("button")
    .filter({ hasText: /\d{1,2}h|\d{2}:\d{2}/ })
    .and(page.locator(":enabled"))
    .first();
  await slot.click({ timeout: 30_000 });
  await page.getByRole("button", { name: "Continuar", exact: true }).click();
  await page.locator("[data-order-fulfillment-options]").getByRole("radio", { name: /^Retirada/ }).click();
  await page.getByRole("button", { name: /Montar encomenda/ }).click();
  await expect(page.getByPlaceholder(/Buscar produto/).locator("visible=true").first()).toBeVisible({ timeout: 30_000 });
}

/** O tile do produto pelo nome exato (há "Croissant Mini" ao lado do "Croissant"). */
function tileOf(page: Page, product: string) {
  return page
    .locator("button[data-pos-product]")
    .filter({ has: page.locator("[data-pos-product-name]", { hasText: new RegExp(`^${product}$`) }) })
    .locator("visible=true")
    .first();
}

/** Lança o produto e digita a quantidade no editor da linha. */
async function ordersQuantity(page: Page, product = PRODUCT, qty = QTY) {
  const search = page.getByPlaceholder(/Buscar produto/).locator("visible=true").first();
  await search.click();
  await search.pressSequentially(product);
  await tileOf(page, product).click({ timeout: 30_000 });
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
    for (const digit of qty) await editor.getByRole("button", { name: `Dígito ${digit}`, exact: true }).click();
    await editor.locator("[data-pos-line-editor-close]").click();
  } else {
    // Balcão: o teclado físico digita a quantidade da linha aberta.
    await page.keyboard.type(qty);
    await page.keyboard.press("Enter");
  }
}

/**
 * O resto da auditoria do WP-E3: BORDA (a pílula cabe no tile, sem encostar), FOCO (o
 * tile recebe o foco do teclado com anel visível) e ALINHAMENTO (o fato da linha começa
 * onde começa o nome do item).
 */
async function auditsGeometry(page: Page, tileSelector: string | null) {
  const report = await page.evaluate((sel) => {
    const tile = sel ? (document.querySelector(sel) as HTMLElement | null) : null;
    const pill = tile?.querySelector("[data-pos-product-unplanned]") as HTMLElement | null;
    const fact = Array.from(document.querySelectorAll('[data-pos-line-plan="unplanned"]')).find((el) => (el as HTMLElement).offsetParent !== null) as HTMLElement | undefined;
    const name = fact?.closest("[data-item-select]")?.querySelector("[data-pos-line-name]") as HTMLElement | null;
    const box = (el: Element | null | undefined) => (el ? el.getBoundingClientRect() : null);
    const t = box(tile);
    const p = box(pill);
    if (tile) tile.focus({ focusVisible: true } as FocusOptions);
    const focused = document.activeElement === tile;
    const style = tile ? getComputedStyle(tile) : null;
    const ring = Boolean(style && ((style.outlineStyle !== "none" && Number.parseFloat(style.outlineWidth) > 0) || style.boxShadow !== "none"));
    return {
      pillInsideTile: Boolean(t && p && p.left >= t.left + 4 && p.right <= t.right - 4 && p.top >= t.top + 4),
      pill: p && [Math.round(p.left), Math.round(p.right)],
      tile: t && [Math.round(t.left), Math.round(t.right)],
      focused,
      ring,
      factLeft: box(fact) && Math.round(box(fact)!.left),
      nameLeft: box(name) && Math.round(box(name)!.left),
    };
  }, tileSelector);
  console.log(`AUDITORIA geometria e foco: ${JSON.stringify(report)}`);
  return report;
}

test.describe.configure({ mode: "serial" });

for (const device of ["phone", "counter"] as const) {
  test.describe(`J5 Encomenda acima do plano · ${device === "phone" ? "375 px" : "1366 px"}`, () => {
    test.use({ device });

    test("200 baguetes para o próximo dia aberto, acima do lote planejado: só o gerente libera", async ({ cashierAtCounter: page }, testInfo) => {
      test.setTimeout(8 * 60_000);
      await opensOrder(page);
      await identifiesCustomer(page);
      const chosen = await schedulesNextOpenDayPickup(page);
      const day = chosen.dayMonth;
      const PLANNED = plannedFor(chosen);
      await capture(page, testInfo, "encomenda-para-o-proximo-dia-aberto");

      await ordersQuantity(page);
      // 1 · A linha mostra a fornada da data e que o pedido passa dela.
      const fact = page.locator('[data-pos-line-plan="over"]').locator("visible=true").first();
      await expect(fact).toContainText(`Passa do plano: ${PLANNED} planejadas para ${day}`, { timeout: 30_000 });
      // A sobra de hoje não lastreia encomenda (dono, 18/11/2026): nenhum número além do plano.
      await expect(fact).not.toContainText("livres");
      await audits(page, "linha", '[data-pos-line-plan="over"] > span', { covered: false });
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
      await audits(page, "aviso", "li.border-warning > span > span", { covered: false });
      await capture(page, testInfo, "validar-travado");

      // 3 · Sem a assinatura não fecha: o diálogo abre, a Fran fecha, nada muda.
      await ask.click();
      const dialog = page.getByRole("dialog", { name: "Autorizar a venda" });
      await expect(dialog).toBeVisible({ timeout: 30_000 });
      await expect(dialog.locator("[data-over-plan-context]")).toContainText(`${QTY} pedidas, ${PLANNED} planejadas para ${day}`);
      // A captura espera a animação de entrada do diálogo terminar.
      await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running"));
      const context = await audits(page, "dialogo", "[data-over-plan-context] p", { covered: false });
      // Alinhamento: o quadro dos números bate borda com o aviso "Você continua como".
      const edges = await page.evaluate(() => {
        const ctx = document.querySelector("[data-over-plan-context]")!.getBoundingClientRect();
        const sibling = (document.querySelector("[data-over-plan-context]")!.parentElement!.firstElementChild as HTMLElement).getBoundingClientRect();
        return { ctx: [Math.round(ctx.left), Math.round(ctx.right)], alert: [Math.round(sibling.left), Math.round(sibling.right)] };
      });
      console.log(`AUDITORIA alinhamento do diálogo: ${JSON.stringify(edges)}`);
      expect(edges.ctx).toEqual(edges.alert);
      void context;
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

    test("30 croissants para daqui a dez dias, sem lote planejado: vira pedido à Produção", async ({ cashierAtCounter: page }, testInfo) => {
      test.setTimeout(8 * 60_000);
      const target = tenDaysAhead();
      const note = `Ainda sem lote planejado para ${target.day}: vira pedido à Produção`;

      await opensOrder(page);
      await identifiesCustomer(page);
      await schedulesPickupOn(page, target);

      // 1 · A grade: o croissant não diz "Sem saldo"; diz que vira pedido à Produção.
      const search = page.getByPlaceholder(/Buscar produto/).locator("visible=true").first();
      await search.click();
      await search.pressSequentially("Croissant");
      const tile = tileOf(page, "Croissant");
      await expect(tile).toBeVisible({ timeout: 30_000 });
      await capture(page, testInfo, "grade-sem-plano");
      await expect(tile.locator("[data-pos-product-blocked]")).toHaveCount(0);
      await expect(tile.locator("[data-pos-product-unplanned]")).toContainText("Vira pedido à Produção", { timeout: 30_000 });
      await expect(tile.locator("[data-pos-product-unplanned]")).toHaveAttribute("title", note);
      await audits(page, "pilula", "[data-pos-product-unplanned] > span[aria-hidden]", { covered: false });
      const tileGeometry = await auditsGeometry(page, "button[data-pos-product]:has([data-pos-product-unplanned])");
      expect(tileGeometry.pillInsideTile, "a pílula cabe no tile, longe da borda").toBe(true);
      expect(tileGeometry.focused, "o tile recebe o foco do teclado").toBe(true);
      expect(tileGeometry.ring, "o foco do tile tem anel visível").toBe(true);
      await search.fill("");

      // 2 · A linha: 30 croissants, e o fato da data sem plano.
      await ordersQuantity(page, "Croissant", "30");
      const fact = page.locator('[data-pos-line-plan="unplanned"]').locator("visible=true").first();
      await expect(fact).toHaveText(note, { timeout: 30_000 });
      await audits(page, "linha", '[data-pos-line-plan="unplanned"] > span', { covered: false });
      const lineGeometry = await auditsGeometry(page, null);
      expect(lineGeometry.factLeft, "o fato da linha começa onde começa o nome").toBe(lineGeometry.nameLeft);
      await capture(page, testInfo, "linha-sem-plano");

      // 3 · Nada pede o gerente: o Validar fecha a encomenda em dinheiro.
      await page.getByRole("button", { name: /^Pagamento|^Outras formas/ }).locator("visible=true").first().click();
      await page.getByRole("button", { name: /^Dinheiro/ }).and(page.locator(":enabled")).locator("visible=true").first().click();
      await expect(page.getByText("A encomenda passa do plano. Só o gerente libera.")).toHaveCount(0);
      await capture(page, testInfo, "pagamento-sem-gerente");
      await page.getByRole("button", { name: /^Validar/ }).and(page.locator(":enabled")).locator("visible=true").first().click({ timeout: 30_000 });
      await expect(page.getByText(/Encomenda registrada|CONFIRME COM O CLIENTE|Confirme com o cliente/).locator("visible=true").first())
        .toBeVisible({ timeout: 60_000 });
      await capture(page, testInfo, "encomenda-registrada");
    });
  });
}
