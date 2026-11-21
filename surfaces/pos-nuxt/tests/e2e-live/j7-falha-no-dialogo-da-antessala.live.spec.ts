// JORNADA J7, segunda metade: a falha dos gestos da antessala mora DENTRO do diálogo (#2726).
//
// O WP-E6 (#2689) levou o erro da saída de caixa, do fechamento, da devolução e do
// estorno para dentro do diálogo do gesto. Quatro diálogos ficaram de fora e seguiam
// com a falha num toast ATRÁS do véu do diálogo aberto, apagado: pedir troco, atender
// ou cancelar o pedido de troco, acertar a conta na casa e abrir a gaveta sem venda.
//
// A Caixa (Fran) faz cada gesto pela tela; a rede cai na ida (o servidor não chega a
// gravar) e o aviso tem de aparecer dentro do diálogo, como alerta, legível, com o
// botão que repete o gesto. Ela toca nele, a repetição confirma e o aviso some. No
// celular (375 px) e no balcão (1366 px). Como rodar: README.md desta pasta.
//
// A mesma jornada roda na base (antes) para registrar o toast atrás do véu: por isso
// as asserções do aviso são `soft`, e o gesto se repete pelo botão do diálogo quando
// o aviso não traz o dele.
import type { Locator, TestInfo } from "@playwright/test";

import { audits, measure, still } from "./support/audit";
import { capture, cast, expect, settled, test, type Page } from "./support/operator";

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
  await expect(dialog).toBeHidden({ timeout: 60_000 });
}

async function opensSession(page: Page) {
  await page.goto("/session");
  await settled(page);
}

async function opensTile(page: Page, name: RegExp) {
  await page.getByRole("button", { name }).locator("visible=true").first().click({ timeout: 30_000 });
}

/** A rede cai na ida, UMA vez: o servidor não chega a ver o pedido. */
async function dropsOnce(page: Page, pattern: string) {
  let dropped = false;
  await page.route(pattern, async (route) => {
    if (!dropped && route.request().method() === "POST") {
      dropped = true;
      await route.abort("connectionreset");
      return;
    }
    await route.continue();
  });
  return {
    dropped: () => dropped,
    restore: () => page.unroute(pattern),
  };
}

/**
 * O aviso dentro do diálogo: alerta, legível, no lugar, com o botão que resolve, e
 * nenhum toast repetindo a mesma frase atrás do véu. Mede e registra (AUDITORIA …)
 * para o `auditoria.txt` do PR. Devolve o botão "Tentar de novo" do aviso, se houver.
 */
async function failsInsideDialog(
  page: Page,
  testInfo: TestInfo,
  opts: { dialog: Locator; gesture: string; text: RegExp; label: string },
): Promise<Locator | null> {
  const notice = opts.dialog.locator(`[data-cash-failure-gesture="${opts.gesture}"]`);
  const toast = page.locator("[data-sonner-toast]").filter({ hasText: opts.text });
  await expect.poll(async () => (await notice.count()) + (await toast.count()), { timeout: 30_000 }).toBeGreaterThan(0);
  await still(page);

  // O "antes": a falha virava toast. Fica medido (encoberto pelo véu?) e capturado.
  if (await toast.count()) {
    const rows = await measure(page, "[data-sonner-toast] [data-title]");
    console.log(`AUDITORIA ${opts.label} (toast): ${JSON.stringify(rows.rows)}`);
  }

  await expect.soft(notice, `${opts.label}: o aviso não está dentro do diálogo`).toBeVisible();
  await expect.soft(toast, `${opts.label}: toast duplicado atrás do véu`).toHaveCount(0);
  if (!(await notice.count())) {
    await capture(page, testInfo, `${opts.gesture}-falhou`);
    return null;
  }

  await expect(notice).toHaveAttribute("role", "alert");
  await expect(notice).toContainText(opts.text);
  const retry = notice.getByRole("button", { name: "Tentar de novo" });
  await expect(retry, `${opts.label}: o aviso não traz o botão que resolve`).toBeVisible();
  await expect(notice.getByRole("button").filter({ hasNotText: "Tentar de novo" }), `${opts.label}: o aviso não tem X`).toHaveCount(1);

  // O ponteiro fica onde estava o botão do gesto, e no balcão o aviso nasce embaixo
  // dele: o "Tentar de novo" mediria o tom de hover (passageiro, do kit inteiro), não
  // o do repouso. A régua mede o repouso; o hover fica registrado no auditoria.txt.
  await page.mouse.move(0, 0);
  await still(page);
  const selector = `[data-cash-failure-gesture="${opts.gesture}"]`;
  // O X (só ícone, com `aria-label`) fica de fora da régua de texto; a presença dele
  // já foi conferida acima.
  await audits(page, opts.label, `${selector} [data-slot="title"], ${selector} [data-slot="actions"] button:not([aria-label])`);

  // Posição: dentro do diálogo e da área visível dele; alinhado com o que está acima
  // e abaixo na mesma coluna. Foco: segue dentro do diálogo (a falha não o rouba).
  const geometry = await notice.evaluate((el) => {
    const dialog = el.closest('[role="dialog"]') as HTMLElement;
    const box = el.getBoundingClientRect();
    const frame = dialog.getBoundingClientRect();
    const column = el.parentElement!.getBoundingClientRect();
    const siblings = [...el.parentElement!.children]
      .filter((child) => child !== el && (child as HTMLElement).offsetParent !== null)
      .map((child) => Math.round(child.getBoundingClientRect().left));
    return {
      notice: [Math.round(box.left), Math.round(box.top), Math.round(box.right), Math.round(box.bottom)],
      dialog: [Math.round(frame.left), Math.round(frame.top), Math.round(frame.right), Math.round(frame.bottom)],
      inDialog: box.left >= frame.left - 0.5 && box.right <= frame.right + 0.5 && box.top >= frame.top - 0.5 && box.bottom <= frame.bottom + 0.5,
      onScreen: box.top >= 0 && box.bottom <= window.innerHeight + 0.5 && box.left >= 0 && box.right <= window.innerWidth + 0.5,
      // A borda de CONTEÚDO da coluna (a linha do pedido tem `p-3`), não a da caixa.
      columnLeft: Math.round(column.left + Number.parseFloat(getComputedStyle(el.parentElement!).paddingLeft)),
      siblingLefts: [...new Set(siblings)],
      focusInDialog: dialog.contains(document.activeElement),
      focused: document.activeElement?.tagName ?? "",
    };
  });
  console.log(`AUDITORIA ${opts.label} (posição e foco): ${JSON.stringify(geometry)}`);
  expect(geometry.inDialog, `${opts.label}: o aviso passa da borda do diálogo`).toBe(true);
  expect(geometry.onScreen, `${opts.label}: o aviso não está na área visível`).toBe(true);
  expect(Math.round(geometry.notice[0]!), `${opts.label}: o aviso não alinha com a coluna`).toBe(geometry.columnLeft);
  expect(geometry.focusInDialog, `${opts.label}: o foco saiu do diálogo`).toBe(true);
  await capture(page, testInfo, `${opts.gesture}-falhou`);
  return retry;
}

/** Repete pelo botão do aviso; na base (sem ele), pelo botão do próprio diálogo. */
async function retries(retry: Locator | null, fallback: Locator) {
  await (retry ?? fallback).click();
}

test.describe.configure({ mode: "serial" });

for (const device of ["phone", "counter"] as const) {
  test.describe(`J7 Falha no diálogo da antessala · ${device === "phone" ? "375 px" : "1366 px"}`, () => {
    test.use({ device });

    test("pedir, atender e cancelar troco, acertar a conta e abrir a gaveta: a falha aparece no diálogo", async (
      { cashierAtCounter: page },
      testInfo,
    ) => {
      test.setTimeout(12 * 60_000);
      const stamp = `${device}-${Date.now().toString(36)}`;
      await opensSession(page);

      // 1 · Pedir troco. A rede cai; o aviso aparece no diálogo; "Tentar de novo"
      // envia o mesmo pedido e o diálogo fecha.
      for (const note of [`primeiro ${stamp}`, `segundo ${stamp}`]) {
        await opensTile(page, /Pedir troco/);
        const dialog = page.getByRole("dialog", { name: "Pedido de troco" });
        await expect(dialog).toBeVisible({ timeout: 30_000 });
        const amount = dialog.getByPlaceholder("0,00");
        await amount.click();
        await amount.pressSequentially("50,00");
        await dialog.getByRole("textbox", { name: "Observação do pedido" }).fill(note);
        const network = await dropsOnce(page, "**/pos/cash/change-request/");
        await dialog.getByRole("button", { name: "Preciso de troco" }).click();
        await expect.poll(network.dropped, { timeout: 30_000 }).toBe(true);
        let retry: Locator | null = null;
        if (note.startsWith("primeiro")) {
          retry = await failsInsideDialog(page, testInfo, {
            dialog, gesture: "request_change", text: /O pedido de troco não foi enviado/, label: `pedir troco ${device}`,
          });
        }
        await network.restore();
        await retries(retry, dialog.getByRole("button", { name: "Preciso de troco" }));
        await expect(dialog).toBeHidden({ timeout: 30_000 });
        await expect(page.locator("[data-cash-failure]")).toHaveCount(0);
      }
      await still(page);
      await capture(page, testInfo, "dois-pedidos-de-troco");

      // 2 · Atender o primeiro. A rede cai na ida; o aviso fica NA LINHA do pedido.
      // "Tentar de novo" atende: o servidor pede o gerente, e a Joyce assina.
      await opensTile(page, /Pedidos? de troco/);
      const requests = page.getByRole("dialog", { name: "Pedidos de troco" });
      await expect(requests).toBeVisible({ timeout: 30_000 });
      const first = requests.getByRole("listitem").filter({ hasText: `primeiro ${stamp}` });
      const serve = await dropsOnce(page, "**/pos/cash/change-request/*/serve/");
      await first.getByRole("button", { name: "Atender" }).click();
      await expect.poll(serve.dropped, { timeout: 30_000 }).toBe(true);
      const serveRetry = await failsInsideDialog(page, testInfo, {
        dialog: first, gesture: "serve_change", text: /O pedido de troco não foi atendido/, label: `atender troco ${device}`,
      });
      await serve.restore();
      await retries(serveRetry, first.getByRole("button", { name: "Atender" }));
      await managerSigns(page, "Autorizar troco");
      // Atendido, o pedido sai da lista (a confirmação com o valor é um toast breve).
      await expect(first).toHaveCount(0, { timeout: 30_000 });

      // 3 · Cancelar o segundo. O aviso fica na confirmação, que segue aberta.
      const second = requests.getByRole("listitem").filter({ hasText: `segundo ${stamp}` });
      await second.getByRole("button", { name: "Cancelar pedido" }).click();
      const cancel = await dropsOnce(page, "**/pos/cash/change-request/*/cancel/");
      await second.getByRole("button", { name: "Cancelar o pedido" }).click();
      await expect.poll(cancel.dropped, { timeout: 30_000 }).toBe(true);
      const cancelRetry = await failsInsideDialog(page, testInfo, {
        dialog: second, gesture: "cancel_change", text: /O pedido de troco não foi cancelado/, label: `cancelar troco ${device}`,
      });
      await cancel.restore();
      await retries(cancelRetry, second.getByRole("button", { name: "Cancelar o pedido" }));
      await expect(second).toHaveCount(0, { timeout: 30_000 });
      // Sem pedido na lista, o diálogo fecha sozinho; com pedido de outro turno, fecha aqui.
      if (await requests.isVisible()) await page.keyboard.press("Escape");
      await expect(requests).toBeHidden({ timeout: 30_000 });

      // 4 · Acerto de conta na casa, em dinheiro (sem PIN). O aviso fica na conta.
      await opensTile(page, /Contas na casa/);
      const accounts = page.getByRole("dialog", { name: "Contas na casa" });
      await expect(accounts).toBeVisible({ timeout: 30_000 });
      const account = accounts.getByRole("listitem").filter({ has: page.getByRole("button", { name: "Receber acerto" }) }).first();
      const customer = ((await account.locator("span").first().textContent()) || "").trim();
      await account.getByRole("button", { name: "Receber acerto" }).click();
      const row = accounts.getByRole("listitem").filter({ hasText: customer });
      const settle = await dropsOnce(page, "**/pos/accounts/*/settle/");
      await row.getByRole("button", { name: "Receber", exact: true }).click();
      await expect.poll(settle.dropped, { timeout: 30_000 }).toBe(true);
      const settleRetry = await failsInsideDialog(page, testInfo, {
        dialog: row, gesture: "settle_account", text: /O acerto não foi registrado/, label: `acerto ${device}`,
      });
      await settle.restore();
      await retries(settleRetry, row.getByRole("button", { name: "Receber", exact: true }));
      // Acertada, a conta sai da lista ou fecha o formulário do acerto.
      await expect(row.getByRole("button", { name: "Receber", exact: true })).toHaveCount(0, { timeout: 30_000 });
      if (await accounts.isVisible()) await page.keyboard.press("Escape");

      // 5 · Abrir a gaveta sem venda, quando este dispositivo tem caminho de software
      // para ela (agente do Balcão ou o relay do servidor). Sem caminho, o card mostra
      // o motivo e o gesto não existe aqui: fica registrado, não reprovado.
      const drawerTile = page.getByRole("button", { name: /Abrir gaveta/ }).locator("visible=true").first();
      if (!(await drawerTile.isEnabled().catch(() => false))) {
        console.log(`AUDITORIA gaveta ${device}: sem caminho de software neste dispositivo; o card está desabilitado.`);
        await capture(page, testInfo, "gaveta-sem-caminho");
        return;
      }
      await drawerTile.click();
      const drawer = page.getByRole("dialog", { name: "Abrir gaveta" });
      await expect(drawer).toBeVisible({ timeout: 30_000 });
      const drop = await dropsOnce(page, "**/pos/cash/drawer-open/");
      await drawer.getByRole("button", { name: "Conferência", exact: true }).click();
      await expect.poll(drop.dropped, { timeout: 30_000 }).toBe(true);
      const drawerRetry = await failsInsideDialog(page, testInfo, {
        dialog: drawer, gesture: "open_drawer", text: /gaveta não abriu|abertura da gaveta|gaveta continua/i, label: `gaveta ${device}`,
      });
      await drop.restore();
      await retries(drawerRetry, drawer.getByRole("button", { name: "Conferência", exact: true }));
      await still(page);
      await capture(page, testInfo, "gaveta-depois-de-repetir");
    });
  });
}
