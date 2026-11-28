// JORNADA J7 — cancelar e estornar (EXCELENCIA-PDV WP-E6).
//
// A Caixa (Fran) vende em dinheiro e cancela a venda pela lista das Últimas vendas
// (dentro da janela, cancelar em dinheiro devolve na hora); depois tira R$ 50 da
// gaveta. Em cada gesto a Gerente (Joyce), escolhida da lista, assina com o próprio
// PIN VENDO O VALOR: o da venda cancelada e o da saída. Na saída a rede cai depois de o servidor gravar: a
// Fran toca de novo e o livro-caixa fica com UM lançamento (a chave do gesto ignora
// a assinatura do gerente, P1-5). Tudo pela tela, no celular (375 px) e no balcão
// (1366 px). Como rodar: README.md desta pasta.
import { audits, still } from "./support/audit";
import { capture, cast, expect, settled, test, type Page } from "./support/operator";

const OUT_AMOUNT = "50,00";

/** A Gerente escolhida da lista assina com o próprio PIN, no diálogo aberto. */
async function managerSigns(page: Page, dialogName: string | RegExp) {
  const dialog = page.getByRole("dialog", { name: dialogName });
  await expect(dialog).toBeVisible({ timeout: 30_000 });
  await dialog.getByRole("button", { name: new RegExp(cast.manager.name) }).first().click();
  for (const digit of cast.manager.pin) {
    await dialog.getByRole("button", { name: digit, exact: true }).click();
  }
  const confirm = dialog.getByRole("button", { name: /^Confirmar|^Autorizar/ }).first();
  if (await confirm.isVisible({ timeout: 2000 }).catch(() => false)) await confirm.click();
  return dialog;
}

/** O contexto do ato bate borda com o aviso "Você continua como" (alinhamento). */
async function alignedWithOperatorNotice(page: Page, selector: string) {
  const edges = await page.evaluate((sel) => {
    const ctx = document.querySelector(sel)!;
    const grid = ctx.closest(".grid.gap-4") ?? ctx.parentElement!;
    const first = grid.firstElementChild as HTMLElement;
    const a = ctx.getBoundingClientRect();
    const b = first.getBoundingClientRect();
    return { ctx: [Math.round(a.left), Math.round(a.right)], notice: [Math.round(b.left), Math.round(b.right)] };
  }, selector);
  console.log(`AUDITORIA alinhamento ${selector}: ${JSON.stringify(edges)}`);
  expect(edges.ctx[0]).toBe(edges.notice[0]);
}

/** Uma venda de balcão em dinheiro, do quadro até a tela da venda concluída. */
async function sellsInCash(page: Page): Promise<string> {
  await page.getByRole("button", { name: /Próxima livre/ }).first().click();
  await settled(page);
  const tile = page.locator("button[data-pos-product]").and(page.locator(":enabled")).locator("visible=true").first();
  await tile.click({ timeout: 30_000 });
  // No celular a comanda é a folha de baixo: abre para chegar ao Pagamento.
  const sheet = page.getByRole("button", { name: "Ver a comanda" }).locator("visible=true").first();
  if (await sheet.isVisible().catch(() => false)) await sheet.click();
  await page.getByRole("button", { name: /^Pagamento|^Outras formas|^Cobrar/ }).locator("visible=true").first().click();
  await page.getByRole("button", { name: /^Dinheiro/ }).and(page.locator(":enabled")).locator("visible=true").first().click();
  const finish = page.getByRole("button", { name: /^Validar/ }).and(page.locator(":enabled")).locator("visible=true").first();
  await finish.click({ timeout: 30_000 });
  const total = page.locator("[data-sale-result-total], [data-pos-sale-total]").locator("visible=true").first();
  await expect(page.getByRole("button", { name: /Nova venda/ }).locator("visible=true").first()).toBeVisible({ timeout: 60_000 });
  return (await total.textContent().catch(() => "")) || "";
}

async function opensRecentSales(page: Page) {
  const direct = page.getByRole("button", { name: /Últimas vendas/ }).locator("visible=true").first();
  if (!(await direct.isVisible().catch(() => false))) {
    await page.getByRole("button", { name: /Mais ações/ }).locator("visible=true").first().click();
    await page.getByRole("menuitem", { name: /Últimas vendas/ }).first().click();
  } else {
    await direct.click();
  }
  await expect(page.getByRole("dialog", { name: "Últimas vendas" })).toBeVisible({ timeout: 30_000 });
}

async function opensSession(page: Page) {
  await page.goto("/session");
  await settled(page);
}

async function opensTile(page: Page, name: RegExp) {
  await page.getByRole("button", { name }).locator("visible=true").first().click({ timeout: 30_000 });
}

test.describe.configure({ mode: "serial" });

for (const device of ["phone", "counter"] as const) {
  test.describe(`J7 Cancelar e estornar · ${device === "phone" ? "375 px" : "1366 px"}`, () => {
    test.use({ device });

    test("cancelar pela lista e tirar R$ 50: o gerente vê o valor, e repetir grava uma vez", async (
      { cashierAtCounter: page },
      testInfo,
    ) => {
      test.setTimeout(10 * 60_000);

      // 1 · A Fran vende em dinheiro.
      await sellsInCash(page);
      await capture(page, testInfo, "venda-concluida");

      // 2 · Cancela pela lista das Últimas vendas: o gerente vê o valor da venda.
      await opensRecentSales(page);
      const sheet = page.getByRole("dialog", { name: "Últimas vendas" });
      const firstSale = sheet.getByRole("listitem").filter({ has: page.getByRole("button", { name: "Cancelar venda" }) }).first();
      const saleTotal = ((await firstSale.textContent()) || "").match(/R\$ ?[\d.]+,\d{2}/)?.[0] ?? "";
      expect(saleTotal, "a linha da venda mostra o total").not.toBe("");
      await firstSale.getByRole("button", { name: "Cancelar venda" }).click();
      const cancelDialog = page.getByRole("dialog", { name: "Autorizar cancelamento" });
      await expect(cancelDialog).toBeVisible({ timeout: 30_000 });
      await still(page);
      await capture(page, testInfo, "cancelar-mostra-o-valor");
      // `soft`: a mesma jornada roda na base (antes) para registrar a captura do
      // diálogo sem o valor, e segue até a saída de R$ 50.
      const totalLine = cancelDialog.locator("[data-cancel-sale-total]");
      await expect.soft(totalLine).toContainText(saleTotal.replace(/R\$\s*/, "R$ "));
      if (await totalLine.count()) {
        await audits(page, "cancelamento", "[data-cancel-sale-total], [data-cancel-sale-total] + p");
        await alignedWithOperatorNotice(page, "[data-cancel-sale-total]");
      }
      await managerSigns(page, "Autorizar cancelamento");
      await expect(cancelDialog).toBeHidden({ timeout: 60_000 });
      await expect(page.getByText("Venda cancelada").first()).toBeVisible({ timeout: 30_000 });
      await page.keyboard.press("Escape");

      // No balcão, dentro da janela, cancelar a venda em dinheiro JÁ devolve: o
      // dinheiro sai da gaveta no mesmo gesto, com a mesma assinatura (por isso o
      // gerente precisa ver o valor). A devolução pendente da antessala é a da venda
      // cancelada fora daqui (gestor, de noite), e o diálogo dela já mostrava o valor.
      await opensSession(page);

      // 3 · A saída de R$ 50: o gerente vê o valor; a rede cai DEPOIS de o servidor
      // gravar; a Fran toca de novo e o livro fica com um lançamento só.
      await opensTile(page, /Saída de caixa/);
      const amount = page.getByPlaceholder("0,00").locator("visible=true").first();
      await amount.click();
      await amount.pressSequentially(OUT_AMOUNT);
      const reasons = page.getByRole("group", { name: /Motivo/ }).getByRole("button");
      await reasons.first().click();

      const recorded: Array<{ status: number; entry_id?: number; signed: boolean }> = [];
      let cutOnce = false;
      await page.route("**/pos/cash/movement/", async (route) => {
        const body = route.request().postDataJSON() as Record<string, unknown>;
        const signed = Boolean(body.manager_approval);
        // O Node do Playwright não resolve `*.localhost` como o Chromium: a ida vai ao
        // loopback com o mesmo Host, cookies e corpo do navegador.
        const original = new URL(route.request().url());
        const response = await route.fetch({
          url: route.request().url().replace(original.hostname, "127.0.0.1"),
          headers: { ...(await route.request().allHeaders()), host: original.host },
        });
        const data = (await response.json().catch(() => ({}))) as { entry_id?: number };
        recorded.push({ status: response.status(), entry_id: data.entry_id, signed });
        if (signed && response.status() === 200 && !cutOnce) {
          // O servidor gravou; a resposta se perde no caminho.
          cutOnce = true;
          await route.abort("connectionreset");
          return;
        }
        await route.fulfill({ response });
      });

      await page.getByRole("button", { name: "Registrar movimento" }).click();
      const outDialog = page.getByRole("dialog", { name: "Autorizar retirada da gaveta" });
      await expect(outDialog).toBeVisible({ timeout: 30_000 });
      await still(page);
      await expect(outDialog).toContainText(`R$ ${OUT_AMOUNT}`);
      await capture(page, testInfo, "saida-mostra-o-valor");
      await managerSigns(page, "Autorizar retirada da gaveta");
      await expect(outDialog).toBeHidden({ timeout: 60_000 });
      await expect.poll(() => cutOnce, { timeout: 60_000 }).toBe(true);
      // O erro mora DENTRO do diálogo da saída, junto do botão que repete, e não num
      // toast atrás do véu: um aviso só, legível, com X.
      const failure = page.getByRole("dialog", { name: "Saída de caixa" }).locator("[data-cash-failure]");
      await expect(failure).toBeVisible({ timeout: 30_000 });
      await expect(failure).toHaveAttribute("role", "alert");
      await expect(failure).toContainText("O movimento não entrou no livro-caixa.");
      await expect(page.getByText(/O movimento não entrou no livro-caixa/)).toHaveCount(1);
      await still(page);
      await audits(page, "erro da saída", "[data-cash-failure] [data-slot='title']");
      await capture(page, testInfo, "rede-caiu-depois-de-gravar");

      // A Fran toca de novo, sem chamar o gerente outra vez.
      await page.getByRole("button", { name: "Registrar movimento" }).click();
      // Na base (antes), a chave mudava com a assinatura: o servidor pedia o gerente
      // de novo, e a segunda assinatura gravaria a segunda saída.
      await expect
        .poll(async () => recorded.filter((r) => r.status === 200).length === 2 || (await outDialog.isVisible()), { timeout: 60_000 })
        .toBe(true);
      // Confirmado o mesmo lançamento, o aviso do diálogo some e o diálogo fecha.
      await expect(failure).toHaveCount(0, { timeout: 30_000 });
      await expect(page.getByRole("dialog", { name: "Saída de caixa" })).toBeHidden({ timeout: 30_000 });
      await still(page);
      await capture(page, testInfo, "repetir-depois-da-rede");
      console.log(`J7 saída: ${JSON.stringify(recorded)}`);
      await expect(outDialog, "repetir não pode pedir o gerente de novo").toBeHidden();
      await expect.poll(() => recorded.filter((r) => r.status === 200).length, { timeout: 30_000 }).toBe(2);
      const accepted = recorded.filter((r) => r.status === 200);
      // O mesmo lançamento: o servidor devolveu a linha da primeira vez.
      expect(accepted[1]!.entry_id).toBe(accepted[0]!.entry_id);
      await expect(page.getByText(`R$ ${OUT_AMOUNT} saiu da gaveta.`).first()).toBeVisible({ timeout: 30_000 });
      // O aviso da tentativa perdida sai da tela quando a repetição confirma.
      await expect(page.getByText(/O movimento não entrou no livro-caixa/)).toHaveCount(0, { timeout: 10_000 });
      await still(page);
      await capture(page, testInfo, "saida-registrada-uma-vez");
      await page.unroute("**/pos/cash/movement/");
    });
  });
}
