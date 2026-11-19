import { expect, test, type Page } from "@playwright/test";

// "Resolver" a promessa em risco, na tela de verdade (WP-G08). O cenário mora no mock
// (`mockBackend.mjs`, ligado pelo cookie `e2e_promise`): um pedido com a promessa em
// risco na fila, e a leitura do diálogo com as quatro famílias de escolha. O que estas
// provas travam:
//  - o aviso (cartão, Fila, detalhe) oferece "Resolver", e as saídas antigas saíram dele;
//  - o diálogo não marca nada sozinho, e cada escolha traz a mensagem dela e o botão
//    com o nome do que ela faz;
//  - tirar o item grava a lista final do servidor e a leitura se refaz; cancelar leva
//    ao cancelar que já existe; trocar e remarcar são atalhos para o PDV;
//  - em 375 px nada passa da largura e o botão que conclui fica à vista.
const MOCK = `http://127.0.0.1:${Number(process.env.MOCK_PORT || 8796)}`;
const COOKIE = { cookie: "e2e_promise=risk" };
const REF = "WEB-2611-G8G-N75";
// No desktop a coluna "Em preparo" abre recolhida, como tira: o quadro com todas abertas.
const BOARD = "/?view=board&columns=all";
const HELLO =
  "Oi, Nelson! Aqui é da Nelson Boulangerie 💛 A Focaccia Cebola, Bacon e Tomilho do seu pedido N75 não vai ficar pronta hoje, e sinto muito por isso.";
const CHOICES = [
  {
    radio: /^Trocar por Campagne Passas & Castanhas/,
    message: `${HELLO} Posso trocar por Campagne Passas & Castanhas? Me avisa e eu ajusto por aqui ✨`,
    conclude: "Trocar no PDV",
    href: `https://pdv.example.test/preorders/${REF}?swap=FOCACCIA-CBT`,
  },
  {
    radio: /^Trocar por Fendu/,
    message: `${HELLO} Posso trocar por Fendu? Me avisa e eu ajusto por aqui ✨`,
    conclude: "Trocar no PDV",
    href: `https://pdv.example.test/preorders/${REF}?swap=FOCACCIA-CBT`,
  },
  {
    radio: /^Remarcar para outro dia ou outro lote/,
    message: `${HELLO} Posso remarcar o seu pedido para outro dia? Me diz qual fica melhor para você ✨`,
    conclude: "Remarcar no PDV",
    href: `https://pdv.example.test/preorders/${REF}`,
  },
  {
    radio: /^Tirar só o item que falta e devolver a diferença/,
    message: `${HELLO} Posso tirar esse item do pedido e devolver R$ 44,00 pelo Pix? Me avisa e eu ajusto por aqui ✨`,
    conclude: "Tirar o item",
    href: "",
  },
  {
    radio: /^Cancelar o pedido inteiro/,
    message: `${HELLO} Se preferir, cancelo o pedido e devolvo R$ 72,00 pelo Pix. Me avisa como fica melhor ✨`,
    conclude: "Cancelar pedido",
    href: "",
  },
];

async function mockState(page: Page): Promise<{ resolved: boolean; edits: Array<Record<string, unknown>> }> {
  const response = await page.request.get(`${MOCK}/api/v1/backstage/e2e/promise/state/`, { headers: COOKIE });
  return response.json();
}

const dialogOf = (page: Page) => page.getByRole("dialog", { name: "Promessa em risco no pedido N75" });
const card = (page: Page) => page.locator(`[data-focus-target="order:${REF}"]`).first();

/** Abre o aviso do cartão e toca em "Resolver". */
async function openFromCard(page: Page) {
  await card(page).locator('[data-card-notice="promise"]').click();
  const notice = page.locator("[data-promise-risk]");
  await expect(notice).toBeVisible();
  await notice.getByRole("button", { name: "Resolver: pedido N75" }).click();
  const dialog = dialogOf(page);
  await expect(dialog.locator("[data-resolve-content]")).toBeVisible();
  return dialog;
}

/** Nada passa da largura: nem a página, nem o diálogo, nem o que está dentro dele. */
async function expectFitsWidth(page: Page) {
  const overflow = await page.evaluate(() => {
    const view = document.documentElement.clientWidth;
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]');
    const wide = dialog
      ? [dialog, ...dialog.querySelectorAll<HTMLElement>("*")]
          .filter((element) => element.getClientRects().length > 0)
          .filter((element) => {
            const box = element.getBoundingClientRect();
            return box.left < -0.5 || box.right > view + 0.5;
          })
          .map((element) => `${element.tagName.toLowerCase()}.${element.className}`.slice(0, 120))
      : ["sem diálogo"];
    return { page: document.documentElement.scrollWidth - view, wide };
  });
  expect(overflow.page).toBeLessThanOrEqual(0);
  expect(overflow.wide).toEqual([]);
}

test.beforeEach(async ({ context, page, baseURL }) => {
  await context.addCookies([{ name: "e2e_promise", value: "risk", url: baseURL! }]);
  await page.request.get(`${MOCK}/api/v1/backstage/e2e/promise/reset/`, { headers: COOKIE });
});

test.describe("Promessa em risco: o diálogo Resolver", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("o aviso do cartão oferece só \"Resolver\", que abre o diálogo sem nada marcado", async ({ page }) => {
    await page.goto(BOARD);
    await card(page).locator('[data-card-notice="promise"]').click();
    const notice = page.locator("[data-promise-risk]");
    await expect(notice).toContainText("Faltam 4x Focaccia Cebola, Bacon e Tomilho");
    await expect(notice).toContainText("Sugestões:");
    // As saídas antigas saíram do aviso: moram no diálogo.
    await expect(notice.locator("[data-promise-exit]")).toHaveText(["Resolver"]);
    for (const old of ["Avisar o cliente", "Remarcar no PDV", "Cancelar pedido"])
      await expect(notice.getByText(old, { exact: true })).toHaveCount(0);
    // O aviso não abre nada sozinho.
    await expect(page.getByRole("dialog", { name: "Promessa em risco no pedido N75" })).toHaveCount(0);

    await notice.getByRole("button", { name: "Resolver: pedido N75" }).click();
    const dialog = dialogOf(page);
    await expect(dialog.locator("[data-resolve-fact]")).toHaveText([
      "Faltam 4x Focaccia Cebola, Bacon e Tomilho. O lote de hoje foi cancelado.",
    ]);
    await expect(dialog.getByText("O que fazer", { exact: true })).toBeVisible();
    await expect(dialog.getByRole("radio")).toHaveCount(CHOICES.length);
    await expect(dialog.getByRole("radio", { checked: true })).toHaveCount(0);
    const conclude = dialog.locator("[data-resolve-conclude]");
    await expect(conclude).toHaveText("Escolha o que fazer");
    await expect(conclude).toBeDisabled();
    await expect(dialog.locator("[data-resolve-message-pending]")).toHaveText("Escolha o que fazer para ver a mensagem.");
    await expect(dialog.locator("[data-resolve-interim]")).toHaveText(
      "O envio automático ainda não existe: copie a mensagem ou chame o cliente no WhatsApp.",
    );
    // O detalhe de cada escolha está escrito ao lado dela.
    await expect(dialog).toContainText("6 disponíveis hoje");
    await expect(dialog).toContainText("R$ 44,00 serão estornados ao Pix do cliente.");
    await expect(dialog).toContainText("R$ 72,00 serão estornados ao Pix do cliente.");
  });

  test("cada escolha traz a mensagem dela e o botão com o nome do que ela faz", async ({ page }) => {
    await page.goto(BOARD);
    const dialog = await openFromCard(page);
    const conclude = dialog.locator("[data-resolve-conclude]");
    for (const choice of CHOICES) {
      await dialog.getByRole("radio", { name: choice.radio }).click();
      await expect(dialog.locator("[data-resolve-message]")).toHaveText(choice.message);
      await expect(conclude).toHaveText(choice.conclude);
      await expect(conclude).toBeEnabled();
      if (choice.href) await expect(conclude).toHaveAttribute("href", choice.href);
      else await expect(conclude).not.toHaveAttribute("href", /.*/);
      // A conversa é só um link, em outra aba, já com a mensagem da escolha.
      const whatsapp = dialog.locator("[data-resolve-whatsapp]");
      await expect(whatsapp).toHaveText("Chamar no WhatsApp");
      await expect(whatsapp).toHaveAttribute("target", "_blank");
      await expect(whatsapp).toHaveAttribute(
        "href",
        `https://wa.me/5543999990000?text=${encodeURIComponent(choice.message)}`,
      );
    }
    // Nada foi gravado só por escolher.
    expect((await mockState(page)).edits).toEqual([]);
    await dialog.getByRole("button", { name: "Voltar" }).click();
    await expect(dialog).toHaveCount(0);
  });

  test("\"Copiar mensagem\" copia a mensagem da escolha e confirma por escrito", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.goto(BOARD);
    const dialog = await openFromCard(page);
    await dialog.getByRole("radio", { name: CHOICES[2]!.radio }).click();
    await dialog.getByRole("button", { name: "Copiar mensagem" }).click();
    await expect(dialog.locator("[data-resolve-copied]")).toHaveText("Mensagem copiada.");
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(CHOICES[2]!.message);
  });

  test("\"Tirar o item\" grava a lista final do servidor, fecha, diz o que foi feito e a leitura se refaz", async ({ page }) => {
    await page.goto(BOARD);
    const dialog = await openFromCard(page);
    await dialog.getByRole("radio", { name: CHOICES[3]!.radio }).click();
    await dialog.getByRole("button", { name: "Tirar o item" }).click();
    await expect(dialog).toHaveCount(0);
    await expect(
      page.getByText("O que faltava saiu do pedido. R$ 44,00 serão estornados ao Pix do cliente.", { exact: true }),
    ).toBeVisible();
    const state = await mockState(page);
    expect(state.edits).toEqual([
      { items: [{ line_id: "line-2", sku: "CROISSANT", qty: "2" }], base_revision: "edit-fixture", expected_actor_id: 1 },
    ]);
    // Uma ida só: a revisão e quem a tela leu vieram da leitura do diálogo (`payload_schema`).
    // O painel releu a fila: o pedido não está mais em risco.
    await expect(card(page).locator('[data-card-notice="promise"]')).toHaveCount(0);
  });

  test("\"Cancelar o pedido inteiro\" leva ao cancelar que já existe, com motivo e dinheiro", async ({ page }) => {
    await page.goto(BOARD);
    const dialog = await openFromCard(page);
    await dialog.getByRole("radio", { name: CHOICES[4]!.radio }).click();
    await dialog.getByRole("button", { name: "Cancelar pedido" }).click();
    await expect(page).toHaveURL(new RegExp(`/${REF}#cancel$`));
    const cancel = page.getByRole("dialog", { name: "Cancelar pedido" });
    await expect(cancel).toBeVisible();
    await expect(cancel).toContainText("R$ 72,00 serão estornados ao Pix do cliente.");
    // Chegar ao cancelar não cancela nada, e o PIN do gerente é desse diálogo, não do "Resolver".
    expect((await mockState(page)).edits).toEqual([]);
  });

  test("o pedido deixou de estar em risco: o diálogo fecha dizendo a frase e o aviso some", async ({ page }) => {
    await page.goto(BOARD);
    await card(page).locator('[data-card-notice="promise"]').click();
    const notice = page.locator("[data-promise-risk]");
    await expect(notice).toBeVisible();
    // Outra tela resolveu o pedido enquanto esta estava aberta.
    await page.request.post(`${MOCK}/api/v1/backstage/orders/${REF}/edit/`, {
      headers: COOKIE,
      data: { items: [], base_revision: "edit-fixture", expected_actor_id: 1 },
    });
    await notice.getByRole("button", { name: "Resolver: pedido N75" }).click();
    await expect(page.getByText("Este pedido não tem mais promessa em risco.", { exact: true })).toBeVisible();
    await expect(dialogOf(page)).toHaveCount(0);
    await expect(card(page).locator('[data-card-notice="promise"]')).toHaveCount(0);
  });

  test("escolha fechada continua na lista com o motivo escrito e não se marca; sem WhatsApp, o chamar fica travado", async ({ page, context, baseURL }) => {
    await context.addCookies([{ name: "e2e_promise", value: "closed", url: baseURL! }]);
    await page.goto(BOARD);
    const dialog = await openFromCard(page);
    await expect(dialog.getByRole("radio")).toHaveCount(CHOICES.length);
    for (const choice of CHOICES.slice(0, 4)) await expect(dialog.getByRole("radio", { name: choice.radio })).toBeDisabled();
    // O motivo de cada uma está escrito na linha dela, não em `title`.
    await expect(dialog.getByText("Pedido em preparo não pode ser editado.", { exact: true })).toHaveCount(3);
    await expect(dialog.getByText("Pedido em preparo não pode ser remarcado.", { exact: true })).toBeVisible();
    // O toque na travada não marca nada.
    await dialog.getByText("Trocar por Fendu", { exact: true }).click({ force: true });
    await expect(dialog.getByRole("radio", { checked: true })).toHaveCount(0);
    await expect(dialog.locator("[data-resolve-conclude]")).toHaveText("Escolha o que fazer");
    // Cancelar segue aberto; a mensagem continua pronta para copiar.
    await dialog.getByRole("radio", { name: CHOICES[4]!.radio }).click();
    await expect(dialog.locator("[data-resolve-message]")).toHaveText(CHOICES[4]!.message);
    await expect(dialog.getByRole("button", { name: "Copiar mensagem" })).toBeEnabled();
    await expect(dialog.locator("[data-resolve-whatsapp]")).toBeDisabled();
    await expect(dialog.locator("[data-resolve-contact-reason]")).toHaveText("Este pedido não tem WhatsApp do cliente.");
  });

  test("na Fila, \"Resolver\" é o botão cheio da linha e abre o mesmo diálogo", async ({ page }) => {
    await page.goto("/?view=queue");
    const row = page.locator(`[data-queue-ref="${REF}"]`);
    const risk = row.locator("[data-queue-promise-risk]");
    await expect(risk.locator("[data-promise-exit]")).toHaveText(["Resolver"]);
    await risk.getByRole("button", { name: "Resolver: pedido N75" }).click();
    await expect(dialogOf(page).locator("[data-resolve-content]")).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(1);
  });

  test("na Tabela, a linha aberta tem o mesmo \"Resolver\", que abre o mesmo diálogo", async ({ page }) => {
    await page.goto("/?view=queue");
    await page.getByRole("tab", { name: "Tabela" }).click();
    const row = page.getByRole("row").filter({ hasText: "Nelson Dias" });
    await expect(row.locator("[data-table-promise-risk]")).toHaveText("Promessa em risco");
    await row.locator("[data-operator-table-expand]").click();
    const risk = page.locator("[data-supervision-promise-risk]");
    await expect(risk.locator("[data-promise-exit]")).toHaveText(["Resolver"]);
    await risk.getByRole("button", { name: "Resolver: pedido N75" }).click();
    await expect(dialogOf(page).locator("[data-resolve-content]")).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(1);
  });

  test("no detalhe, a linha da promessa tem \"Resolver\", que abre o diálogo; cancelar abre o cancelar da própria página", async ({ page }) => {
    await page.goto(`/${REF}#promise`);
    const line = page.locator('[data-pending="promise"]');
    await expect(line.locator("[data-pending-action]")).toHaveText(["Resolver"]);
    await line.getByRole("button", { name: "Resolver" }).click();
    const dialog = dialogOf(page);
    await expect(dialog.locator("[data-resolve-content]")).toBeVisible();
    await dialog.getByRole("radio", { name: CHOICES[4]!.radio }).click();
    await dialog.getByRole("button", { name: "Cancelar pedido" }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: "Cancelar pedido" })).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`/${REF}#promise$`));
  });
});

test.describe("Promessa em risco no celular (375 px)", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("o diálogo aberto pelo cartão cabe na largura em cada escolha, e o botão que conclui fica à vista", async ({ page }) => {
    await page.goto("/");
    const dialog = await openFromCard(page);
    await expectFitsWidth(page);
    const conclude = dialog.locator("[data-resolve-conclude]");
    for (const choice of CHOICES) {
      const radio = dialog.getByRole("radio", { name: choice.radio });
      await radio.scrollIntoViewIfNeeded();
      await radio.click();
      await expect(dialog.locator("[data-resolve-message]")).toHaveText(choice.message);
      await expect(conclude).toHaveText(choice.conclude);
      await expectFitsWidth(page);
      // O rodapé não rola: o botão que conclui está na área visível sem rolar nada.
      await expect(conclude).toBeInViewport({ ratio: 1 });
      await expect(dialog.getByRole("button", { name: "Voltar" })).toBeInViewport({ ratio: 1 });
    }
  });
});
