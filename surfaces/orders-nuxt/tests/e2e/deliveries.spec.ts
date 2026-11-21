import { expect, test } from "@playwright/test";

// A seção Entregas contra o mock: duas corridas na rua (números 1 e 2) e três entregas
// aguardando. Decisão do dono (16/11/2026): corrida se nomeia por LETRA em toda tela;
// o número só escolhe a cor, e a URL do detalhe leva a chave da corrida (`?ride=<chave>`).
test.describe("Entregas: corrida por letra", () => {
  test.use({ viewport: { width: 1360, height: 900 } });

  test("as corridas vivas aparecem como A e B, nunca como 1 e 2", async ({ page }) => {
    await page.goto("/delivery");
    const mirrors = page.locator("[data-ride-mirror]");
    await expect(mirrors).toHaveCount(2);
    await expect(mirrors.nth(0).locator("span").first()).toHaveText("A");
    await expect(mirrors.nth(1).locator("span").first()).toHaveText("B");
    // No mapa, a moto leva a letra e o nome acessível fala a letra (e a idade da posição, F7b).
    await expect(page.getByRole("button", { name: "Entregador da corrida A. Posição agora", exact: true })).toHaveText("A");
    await expect(page.getByRole("button", { name: /^Entregador da corrida B\. Última posição há 3 min/ })).toHaveText("B");
    await expect(page.getByRole("button", { name: "Corrida B, parada 2, pedido F09", exact: true })).toBeVisible();
    await expect(page.getByText(/[Cc]orrida \d/)).toHaveCount(0);
    await expect(page.locator("[aria-label*='orrida 1'], [aria-label*='orrida 2']")).toHaveCount(0);
  });

  test("a corrida em edição ganha a próxima letra livre, do título ao botão de chamar", async ({ page }) => {
    await page.goto("/delivery");
    await page.getByRole("button", { name: /A47 · Ana/ }).click();
    await expect(page.getByText("Corrida C", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Desfazer a corrida C", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Chamar a corrida C", exact: true }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Pedido A47, parada 1 da corrida C", exact: true })).toBeVisible();
    await expect(page.getByText(/[Cc]orrida \d/)).toHaveCount(0);
  });

  test("a corrida em edição cota em duas linhas, segue a ordem da rota e deixa conferir o troco", async ({ page }) => {
    await page.goto("/delivery");
    // Toca primeiro o mais longe: a ordem mostrada é a da rota, nunca a dos toques.
    await page.getByRole("button", { name: /C03 · Caio/ }).click();
    await page.getByRole("button", { name: /A47 · Ana/ }).click();
    const quote = page.locator("[data-ride-quote]");
    await expect(quote.getByText("Juntas: R$ 16,50 · 24 min · 5,7 km ✔", { exact: true })).toBeVisible();
    await expect(quote.getByText("Separadas sairiam R$ 25,00", { exact: true })).toBeVisible();
    await expect(page.getByText("O entregador sai da loja e segue esta ordem.", { exact: true })).toBeVisible();
    // Por extenso: "2 de 4" obrigava o leitor a adivinhar de 4 o quê.
    await expect(page.locator("[data-ride-capacity]")).toHaveText("2 pedidos (cabem até 4)");
    const order = await page.locator("[data-ride-change]").evaluateAll(() =>
      [...document.querySelectorAll("ol li span.block.op-body")].map((node) => node.textContent?.trim() ?? ""),
    );
    expect(order.slice(0, 2)).toEqual(["A47 · Ana", "C03 · Caio"]);
    // O mapa numera igual à lista: o "1" é o primeiro da rota, não o primeiro toque.
    await expect(page.getByRole("button", { name: "Pedido A47, parada 1 da corrida C", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Pedido C03, parada 2 da corrida C", exact: true })).toBeVisible();
    const change = page.getByRole("textbox", { name: "Troco para C03", exact: true });
    await expect(change).toHaveValue("20,00");
    await change.fill("30,00");
    await expect(change).toHaveValue("30,00");
    await expect(page.getByText("2 pedidos em 1 corrida · R$ 16,50", { exact: false }).first()).toBeVisible();
  });

  test("o detalhe abre pela chave na URL e se apresenta pela letra", async ({ page }) => {
    await page.goto("/delivery?ride=776753358");
    const detail = page.locator("[data-ride-detail]");
    await expect(detail.getByText("Corrida B · Em rota", { exact: true })).toBeVisible();
    await expect(page.getByRole("dialog", { name: "Corrida B" })).toBeVisible();
    await expect(detail.getByText(/[Cc]orrida \d/)).toHaveCount(0);
  });
});

// F5: a casa sugere quem vai junto (`ride_plan`), no topo de Aguardando. Cotada e mais
// barata, vem com "Chamar juntas"; o sheet confere e chama num gesto (decisões 1 e 2 = A).
const MOCK = `http://127.0.0.1:${Number(process.env.MOCK_PORT || 8796)}`;

test.describe("Entregas: sugestões da casa", () => {
  test.use({ viewport: { width: 1360, height: 900 } });

  test("o cartão diz a economia em duas linhas e quem chega depois, sem chip de bairro", async ({ page }) => {
    await page.goto("/delivery");
    const card = page.locator("[data-ride-suggestions]");
    await expect(card.getByText("1 corrida sugerida: 2 pedidos.", { exact: true })).toBeVisible();
    const row = card.locator("[data-ride-suggestion]");
    await expect(row.getByText("A47 + C03", { exact: true })).toBeVisible();
    await expect(row.getByText("Juntas: R$ 16,50 · 24 min · 5,7 km ✔", { exact: true })).toBeVisible();
    await expect(row.getByText("Separadas sairiam R$ 25,00", { exact: true })).toBeVisible();
    await expect(row.getByText("C03 chega uns 6 min depois.", { exact: true })).toBeVisible();
    // O chip por nome de bairro saiu.
    await expect(page.getByRole("button", { name: "Gleba Palhano · 2", exact: true })).toHaveCount(0);
  });

  test("Chamar juntas abre o sheet e o Voltar desfaz só o que a sugestão pôs", async ({ page }) => {
    await page.goto("/delivery");
    await page.getByRole("button", { name: "Chamar juntas", exact: true }).click();
    const sheet = page.getByRole("dialog", { name: "Chamar a corrida C" });
    await expect(sheet).toBeVisible();
    await expect(sheet.getByText("A47 → C03", { exact: true })).toBeVisible();
    await expect(sheet.getByText("C03 chega uns 6 min depois.", { exact: true })).toBeVisible();
    await expect(sheet.getByRole("textbox", { name: "Troco para C03", exact: true })).toHaveValue("20,00");
    await sheet.getByRole("button", { name: "Voltar", exact: true }).click();
    await expect(sheet).toBeHidden();
    await expect(page.getByText("Corrida C", { exact: true })).toHaveCount(0);
    await expect(page.locator("[data-ride-suggestion]")).toHaveCount(1);
  });

  test("confirmar no sheet chama UMA corrida com os dois, pelo protocolo de intenção", async ({ page }) => {
    await page.request.delete(`${MOCK}/api/v1/backstage/e2e/deliveries/rides/`);
    await page.goto("/delivery");
    await page.getByRole("button", { name: "Chamar juntas", exact: true }).click();
    const sheet = page.getByRole("dialog", { name: "Chamar a corrida C" });
    await sheet.getByRole("button", { name: "Chamar a corrida C", exact: true }).click();
    await expect(sheet).toBeHidden();
    await expect
      .poll(async () => {
        const answer = await page.request.get(`${MOCK}/api/v1/backstage/e2e/deliveries/rides/`);
        return ((await answer.json()) as { rides: { refs: string[]; ride_number: number }[] }).rides.at(-1) ?? null;
      })
      .toMatchObject({ refs: ["WEB-20261116-0A47", "WEB-20261116-0C03"], ride_number: 3 });
  });

  test("Agora não esconde a sugestão", async ({ page }) => {
    await page.goto("/delivery");
    await page.getByRole("button", { name: "Agora não", exact: true }).click();
    await expect(page.locator("[data-ride-suggestions]")).toHaveCount(0);
  });

  // #2874 (prévia 2A): a sugestão também aparece no mapa, tracejada e cinza, com o preço.
  test("a rota sugerida aparece no mapa enquanto a sugestão está no cartão", async ({ page }) => {
    await page.goto("/delivery");
    const map = page.locator("[data-deliveries-map]").first();
    await expect(map.locator("path[data-map-suggestion]")).toHaveCount(1);
    await expect(map.locator("[data-map-suggestion-label]")).toHaveText("A47 + C03 · R$ 16,50");
    await expect(map.locator("[data-map-legend-suggestion]")).toHaveText("Sugestão");
    // Só leitura: a etiqueta não é alvo de toque e não cobre o pino de ninguém.
    await expect(map.locator("[data-map-suggestion-label]")).toHaveCSS("pointer-events", "none");
    await page.getByRole("button", { name: "Agora não", exact: true }).click();
    await expect(map.locator("[data-map-suggestion]")).toHaveCount(0);
    await expect(map.locator("[data-map-suggestion-label]")).toHaveCount(0);
    await expect(map.locator("[data-map-legend-suggestion]")).toHaveCount(0);
  });

  test("a rota sugerida some quando a sugestão vira corrida em edição", async ({ page }) => {
    await page.goto("/delivery");
    const map = page.locator("[data-deliveries-map]").first();
    await expect(map.locator("path[data-map-suggestion]")).toHaveCount(1);
    await page.getByRole("button", { name: "Chamar juntas", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Chamar a corrida C" })).toBeVisible();
    await expect(map.locator("[data-map-suggestion]")).toHaveCount(0);
    await expect(map.locator("[data-map-suggestion-label]")).toHaveCount(0);
  });
});

// #2908: no celular a legenda aberta cobria pinos ("Entregador" saía "Entrega…" sob o A47).
// No mapa estreito ela começa recolhida num botão e abre só quando o operador pede.
test.describe("Entregas: legenda do mapa no celular", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("a legenda começa recolhida, abre por cima do mapa e fecha pelo X", async ({ page }) => {
    await page.goto("/delivery");
    const map = page.locator("[data-deliveries-map]").first();
    await expect(map.locator("[data-map-legend]")).toHaveCount(0);
    const toggle = map.getByRole("button", { name: "Legenda", exact: true });
    await expect(toggle).toBeVisible();
    const box = await toggle.boundingBox();
    expect(box!.height).toBeGreaterThanOrEqual(44);
    // Nenhum pino fica por baixo do botão: o quadro começa abaixo da faixa da legenda.
    const under = await map.locator("button[aria-label]").evaluateAll((els, b) => els
      .filter((el) => !el.hasAttribute("data-map-legend-toggle"))
      .map((el) => ({ name: el.getAttribute("aria-label"), r: el.getBoundingClientRect() }))
      .filter(({ r }) => r.width && r.left < b.x + b.width && r.right > b.x && r.top < b.y + b.height && r.bottom > b.y)
      .map(({ name }) => name), box!);
    expect(under).toEqual([]);
    await toggle.click();
    const legend = map.locator("[data-map-legend]");
    await expect(legend).toBeVisible();
    await expect(legend.getByText("Entregador", { exact: true })).toBeVisible();
    // Aberta, ela fica por cima dos pinos: o texto não é cortado por nenhum deles.
    const top = await legend.getByText("Entregador", { exact: true }).evaluate((el) => {
      const r = el.getBoundingClientRect();
      const hit = document.elementFromPoint(r.right - 2, r.top + r.height / 2);
      return hit !== null && (el === hit || el.contains(hit) || hit.contains(el));
    });
    expect(top).toBe(true);
    await legend.getByRole("button", { name: "Fechar a legenda", exact: true }).click();
    await expect(map.locator("[data-map-legend]")).toHaveCount(0);
    await expect(toggle).toBeVisible();
  });
});

test.describe("Entregas: legenda do mapa no desktop", () => {
  test.use({ viewport: { width: 1360, height: 900 } });

  test("no mapa largo a legenda fica aberta, sem botão", async ({ page }) => {
    await page.goto("/delivery");
    const map = page.locator("[data-deliveries-map]").first();
    await expect(map.locator("[data-map-legend]")).toBeVisible();
    await expect(map.getByRole("button", { name: "Legenda", exact: true })).toHaveCount(0);
  });
});
