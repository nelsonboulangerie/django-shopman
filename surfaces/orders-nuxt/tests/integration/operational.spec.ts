import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test, expect, type Page } from "@playwright/test";

const lab = JSON.parse(readFileSync(new URL("../../../../.orders-lab/manifest.json", import.meta.url), "utf8"));

async function login(page: Page, username = "orders-lab") {
  await page.goto("/");
  await page.getByRole("textbox", { name: "Usuário", exact: true }).fill(username);
  await page.getByLabel("Senha", { exact: true }).fill("synthetic-lab-only-20260910");
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Entre para operar" })).toHaveCount(0);
}

test("lost response after the Django commit queries receipt and advances only once", async ({ page }) => {
  await login(page, "orders-lab-advance");
  let posts = 0;
  let lookups = 0;
  await page.route(`**/api/v1/backstage/orders/${lab.advance_ref}/advance/**`, async (route) => {
    if (route.request().method() === "POST") {
      posts += 1;
      const response = await route.fetch(); // The real Nitro/Django command commits first.
      expect(response.status()).toBe(200);
      await route.abort("failed"); // Only the browser's response is lost.
    } else { lookups += 1; await route.continue(); }
  });
  await page.goto(`/${lab.advance_ref}`);
  await expect(page.getByRole("button", { name: "Iniciar preparo", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Iniciar preparo", exact: true }).click();
  await expect(page.getByRole("button", { name: "Marcar pronto", exact: true })).toBeVisible();
  const canonical = await (await page.request.get(`/api/v1/backstage/orders/${lab.advance_ref}/`)).json();
  expect(canonical.order.status).toBe("preparing");
  expect(posts).toBe(1);
  await expect.poll(() => lookups).toBe(1);
  await page.screenshot({ path: fileURLToPath(new URL("../../../../.orders-lab/integration-advance.png", import.meta.url)), fullPage: true });
});

test("SSE during notes draft preserves text and offers explicit same-field resolution", async ({ page }) => {
  await login(page, "orders-lab-notes");
  await page.goto(`/${lab.notes_ref}`);
  const editor = page.locator("textarea").first();
  await expect(editor).toHaveValue("Nota inicial");
  await editor.fill("Rascunho preservado");
  const fresh = await (await page.request.get(`/api/v1/backstage/orders/${lab.notes_ref}/`)).json();
  const action = fresh.order.actions.find((value: { ref: string }) => value.ref === "notes");
  const response = await page.request.post(`/api/v1/backstage/orders/${lab.notes_ref}/notes/`, {
    headers: { "Idempotency-Key": crypto.randomUUID() }, data: { ...action.payload_schema, notes: "Outra estação" },
  });
  expect(response.status()).toBe(200);
  await expect(page.getByText("No servidor: Outra estação")).toBeVisible();
  await expect(editor).toHaveValue("Rascunho preservado");
  for (const name of ["Salvar nota", "Manter meu texto", "Usar texto do servidor"]) {
    const box = await page.getByRole("button", { name, exact: true }).boundingBox();
    expect.soft(box?.width, `${name}: largura`).toBeGreaterThanOrEqual(44);
    expect.soft(box?.height, `${name}: altura`).toBeGreaterThanOrEqual(44);
  }
  await expect(page.getByRole("button", { name: "Salvar nota", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Manter meu texto", exact: true }).click();
  await page.getByRole("button", { name: "Salvar nota", exact: true }).click();
  await expect.poll(async () => (await (await page.request.get(`/api/v1/backstage/orders/${lab.notes_ref}/`)).json()).order.kitchen_note).toBe("Rascunho preservado");
  await page.screenshot({ path: fileURLToPath(new URL("../../../../.orders-lab/integration-notes.png", import.meta.url)), fullPage: true });
});

test("price preview confirms exact canonical values through Nitro and Django", async ({ page }) => {
  await login(page, "orders-lab-price");
  await page.goto("/catalog");
  const matrix = await (await page.request.get("/api/v1/backstage/catalog/")).json();
  const before = matrix.matrix.rows.find((row: { sku: string }) => row.sku === "LAB-PROD").cells.find((cell: { surface_ref: string }) => cell.surface_ref === "lab").price_q;
  await page.locator('[data-dragkey="LAB-PROD"]').getByRole("checkbox").check();
  await page.locator('select').filter({ has: page.locator('option[value="*"]') }).selectOption("lab");
  await page.getByRole("button", { name: "Preço…", exact: true }).click();
  await page.getByPlaceholder("+10 ou -20").fill("10");
  await page.getByRole("button", { name: "Revisar alterações", exact: true }).click();
  await expect(page.getByText("Revise 1 células antes de confirmar")).toBeVisible();
  const unchanged = await (await page.request.get("/api/v1/backstage/catalog/")).json();
  expect(unchanged.matrix.rows.find((row: { sku: string }) => row.sku === "LAB-PROD").cells.find((cell: { surface_ref: string }) => cell.surface_ref === "lab").price_q).toBe(before);
  await page.screenshot({ path: fileURLToPath(new URL("../../../../.orders-lab/integration-price-preview.png", import.meta.url)), fullPage: true });
  const result = page.waitForResponse((response) => response.url().endsWith("/catalog/bulk-price/") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Confirmar alterações", exact: true }).click();
  expect((await (await result).json()).outcome).toBe("applied");
  const after = await (await page.request.get("/api/v1/backstage/catalog/")).json();
  expect(after.matrix.rows.find((row: { sku: string }) => row.sku === "LAB-PROD").cells.find((cell: { surface_ref: string }) => cell.surface_ref === "lab").price_q).toBe(Math.round(before * 1.1));
});

test("closed product A cannot hydrate the reopened panel for B", async ({ page }) => {
  await login(page, "orders-lab-product");
  await page.goto("/catalog");
  let release!: () => void;
  let received!: () => void;
  const responseReady = new Promise<void>(resolve => { received = resolve; });
  const delayed = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/backstage/catalog/product/LAB-PROD/**", async route => {
    const response = await route.fetch();
    received();
    await delayed;
    await route.fulfill({ response });
  });
  await page.getByRole("button", { name: "Ações de Produto laboratório", exact: true }).click();
  await page.getByRole("button", { name: "Editar detalhes", exact: true }).click();
  await responseReady;
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Ações de Produto secundário", exact: true }).click();
  await page.getByRole("button", { name: "Editar detalhes", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Produto secundário", exact: true })).toBeVisible();
  const finished = page.waitForResponse("**/api/v1/backstage/catalog/product/LAB-PROD/**");
  release();
  await finished;
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page.getByRole("heading", { name: "Produto secundário", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Produto laboratório", exact: true })).toHaveCount(0);
});

test("same person resumes a locked draft; another person never inherits it", async ({ page }) => {
  await login(page);
  await page.goto(`/${lab.notes_ref}`);
  const serverNote = (await (await page.request.get(`/api/v1/backstage/orders/${lab.notes_ref}/`)).json()).order.kitchen_note;
  const editor = page.locator("textarea").first();
  await expect(editor).toHaveValue(serverNote);
  await editor.fill("Texto privado da pessoa A");
  async function identify(username: string) {
    await page.getByRole("button", { name: /travar \/ trocar/ }).click();
    await expect(page.getByRole("heading", { name: "Entre para operar" })).toBeVisible();
    await expect(editor).not.toBeVisible();
    await page.getByRole("textbox", { name: "Usuário", exact: true }).fill(username);
    await page.getByLabel("Senha", { exact: true }).fill("synthetic-lab-only-20260910");
    await page.getByRole("button", { name: "Entrar", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Entre para operar" })).toHaveCount(0);
  }
  await identify("orders-lab");
  await expect(editor).toHaveValue("Texto privado da pessoa A");
  expect((await (await page.request.get(`/api/v1/backstage/orders/${lab.notes_ref}/`)).json()).order.kitchen_note).toBe(serverNote);
  await identify("orders-lab-b");
  await expect(editor).toHaveValue(serverNote);
});


test("cancel response loss retains the reason and reads the committed receipt", async ({ page }) => {
  await login(page, "orders-lab-cancel");
  let posts = 0;
  let lookups = 0;
  await page.route(`**/api/v1/backstage/orders/${lab.cancel_ref}/cancel/**`, async (route) => {
    if (route.request().method() === "POST") {
      posts += 1;
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      await route.abort("failed");
    } else { lookups += 1; await route.continue(); }
  });
  await page.goto(`/${lab.cancel_ref}`);
  await page.getByRole("button", { name: "Cancelar", exact: true }).click();
  await page.getByRole("textbox", { name: "Motivo", exact: true }).fill("Motivo sintético preservado");
  const confirm = page.getByRole("button", { name: "Confirmar", exact: true });
  await confirm.click({ trial: true });
  expect.soft((await confirm.boundingBox())?.height, "Confirmar: ação principal").toBeGreaterThanOrEqual(48);
  await page.getByRole("dialog").screenshot({ path: fileURLToPath(new URL("../../../../.orders-lab/integration-reason-targets.png", import.meta.url)) });
  await confirm.click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const canonical = await (await page.request.get(`/api/v1/backstage/orders/${lab.cancel_ref}/`)).json();
  expect(canonical.order.status).toBe("cancelled");
  expect(posts).toBe(1);
  expect(lookups).toBe(1);
});


test("cash draft survives close, queue navigation and a declined reload without settlement", async ({ page }) => {
  await login(page, "orders-lab-cash");
  let commands = 0;
  page.on("request", request => { if (request.method() === "POST" && request.url().includes("settle-delivery-cash")) commands++; });
  await page.goto(`/${lab.cash_ref}`);
  await page.getByRole("button", { name: "Acerto dinheiro", exact: true }).click();
  const amount = page.getByRole("textbox", { name: "Valor recebido", exact: true });
  await amount.fill("14,50");
  await page.getByRole("button", { name: "Voltar", exact: true }).click();
  await page.getByRole("button", { name: "Acerto dinheiro", exact: true }).click();
  await expect(amount).toHaveValue("14,50");
  await page.getByRole("button", { name: "Voltar", exact: true }).click();
  await page.getByRole("link", { name: "Voltar para a fila", exact: true }).click();
  await page.getByRole("searchbox", { name: "Buscar por código, cliente ou item (atalho: /)", exact: true }).fill(lab.cash_ref);
  await page.getByRole("button", { name: "Acerto dinheiro", exact: true }).click();
  await expect(amount).toHaveValue("14,50");
  const exit = page.waitForEvent("dialog");
  await page.evaluate(() => { setTimeout(() => window.location.reload(), 0); });
  const confirmation = await exit;
  expect(confirmation.type()).toBe("beforeunload");
  await confirmation.dismiss();
  await expect(amount).toHaveValue("14,50");
  expect(commands).toBe(0);
});

test("cash settlement response loss resolves one receipt in the observed drawer", async ({ page }) => {
  await login(page, "orders-lab-cash");
  let posts = 0;
  let lookups = 0;
  await page.route(`**/api/v1/backstage/orders/${lab.cash_ref}/settle-delivery-cash/**`, async route => {
    if (route.request().method() === "POST") {
      posts += 1;
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      await route.abort("failed");
    } else { lookups += 1; await route.continue(); }
  });
  await page.goto(`/${lab.cash_ref}`);
  await page.getByRole("button", { name: "Acerto dinheiro", exact: true }).click();
  await expect(page.getByText(new RegExp(`turno ${lab.cash_shift_id}`))).toBeVisible();
  await page.getByRole("textbox", { name: "Valor recebido", exact: true }).fill("15,00");
  await page.getByRole("button", { name: "Confirmar", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Acerto dinheiro", exact: true })).toHaveCount(0);
  expect(posts).toBe(1);
  expect(lookups).toBe(1);
});


test("feed selection survives response loss and consults the same scoped receipt", async ({ page }) => {
  await login(page, "orders-lab-feed");
  let posts = 0;
  let lookups = 0;
  await page.route("**/api/v1/backstage/feeds/collections/**", async route => {
    if (route.request().method() === "POST") {
      posts += 1;
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      await route.abort("failed");
    } else {
      lookups += 1;
      expect(new URL(route.request().url()).searchParams.get("ref")).toBe(lab.feed_ref);
      await route.continue();
    }
  });
  await page.goto("/feeds");
  const feed = page.locator("article").filter({ hasText: lab.feed_name });
  for (const control of [feed.getByRole("switch"), feed.getByRole("button", { name: "Coleções", exact: true })]) {
    const box = await control.boundingBox();
    expect.soft(box?.width).toBeGreaterThanOrEqual(44);
    expect.soft(box?.height).toBeGreaterThanOrEqual(44);
  }
  await feed.getByRole("button", { name: "Coleções", exact: true }).click();
  await page.getByRole("button", { name: "Aplicar", exact: true }).click({ trial: true });
  const applyBox = await page.getByRole("button", { name: "Aplicar", exact: true }).boundingBox();
  expect.soft(applyBox?.height, "Aplicar: ação principal").toBeGreaterThanOrEqual(48);
  await page.getByLabel(new RegExp(lab.collection_name)).check();
  await page.getByRole("button", { name: "Aplicar", exact: true }).click();
  await expect(page.getByText("Coleções exibidas", { exact: true })).toHaveCount(0);
  await expect(feed.getByText(lab.collection_name, { exact: true })).toBeVisible();
  expect(posts).toBe(1);
  expect(lookups).toBe(1);
  await feed.screenshot({ path: fileURLToPath(new URL("../../../../.orders-lab/integration-feed-targets.png", import.meta.url)) });
  const state = await (await page.request.get("/api/v1/backstage/feeds/")).json();
  expect(state.board.feeds.find((item: { ref: string }) => item.ref === lab.feed_ref).collections.map((item: { ref: string }) => item.ref)).toEqual([lab.collection_ref]);
});


test("failed refresh leaves the live draft visible and prevents a stale mutation", async ({ page }) => {
  await login(page, "orders-lab-read");
  await page.goto(`/${lab.notes_ref}`);
  const editor = page.locator("#order-notes");
  await editor.fill("Rascunho durante indisponibilidade");
  let posts = 0;
  await page.route(`**/api/v1/backstage/orders/${lab.notes_ref}/**`, async route => {
    if (route.request().method() === "POST") { posts += 1; await route.continue(); }
    else await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Synthetic read outage" }) });
  });
  await page.getByRole("button", { name: "Atualizar", exact: true }).click();
  await expect(page.locator("[data-order-error]")).toContainText("Mantivemos a última leitura");
  await expect(editor).toHaveValue("Rascunho durante indisponibilidade");
  await page.getByRole("button", { name: "Salvar nota", exact: true }).click();
  await expect(page.getByText("A leitura está desatualizada. Atualize o pedido antes de confirmar; seu rascunho foi mantido.", { exact: true })).toBeVisible();
  expect(posts).toBe(0);
});

test("product PATCH response lost after commit closes only after receipt confirmation", async ({ page }) => {
  await login(page, "orders-lab-edit");
  await page.goto("/catalog");
  const path = `/api/v1/backstage/catalog/product/${lab.edit_sku}/`;
  let patches = 0;
  let receipts = 0;
  await page.route(`**${path}**`, async route => {
    if (route.request().method() === "PATCH") {
      patches += 1;
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      await route.abort("failed");
    } else {
      if (route.request().url().includes("idempotency_key")) receipts += 1;
      await route.continue();
    }
  });
  await page.getByRole("button", { name: `Ações de ${lab.edit_name}`, exact: true }).click();
  await page.getByRole("button", { name: "Editar detalhes", exact: true }).click();
  await page.getByRole("textbox", { name: "Nome", exact: true }).fill(`${lab.edit_name} salvo`);
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Nome", exact: true })).toHaveCount(0);
  expect((await (await page.request.get(path)).json()).product.name).toBe(`${lab.edit_name} salvo`);
  expect(patches).toBe(1);
  expect(receipts).toBe(1);
});

test("product same-field dispute preserves draft until explicit reviewed save", async ({ page }) => {
  await login(page, "orders-lab-edit");
  await page.goto("/catalog");
  const path = `/api/v1/backstage/catalog/product/${lab.edit_sku}/`;
  const before = await (await page.request.get(path)).json();
  await page.getByRole("button", { name: `Ações de ${before.product.name}`, exact: true }).click();
  await page.getByRole("button", { name: "Editar detalhes", exact: true }).click();
  const name = page.getByRole("textbox", { name: "Nome", exact: true });
  await expect(name).toHaveValue(before.product.name);
  await name.fill("Rascunho do catálogo");
  const concurrent = await page.request.patch(path, { headers: { "Idempotency-Key": crypto.randomUUID() }, data: { ...before.action.payload_schema, patch: { name: "Outra estação do catálogo" } } });
  expect(concurrent.status()).toBe(200);
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(page.getByText("Nome — atual: Outra estação do catálogo")).toBeVisible();
  await expect(name).toHaveValue("Rascunho do catálogo");
  await expect(page.getByRole("button", { name: "Salvar", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Manter meu rascunho", exact: true }).click();
  await expect(name).toHaveValue("Rascunho do catálogo");
  expect((await (await page.request.get(path)).json()).product.name).toBe("Outra estação do catálogo");
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(name).toHaveCount(0);
  expect((await (await page.request.get(path)).json()).product.name).toBe("Rascunho do catálogo");
});

test("curation drag lost response adopts receipt and canonical exact order", async ({ page }) => {
  await login(page, "orders-lab-curation");
  await page.goto("/catalog");
  await page.getByRole("button", { name: new RegExp(lab.curation_name) }).click();
  const rows = page.locator("tr[data-dragkey]");
  await expect(rows).toHaveCount(2);
  let posts = 0;
  let receipts = 0;
  await page.route("**/api/v1/backstage/catalog/reorder-items/**", async route => {
    if (route.request().method() === "POST") {
      posts += 1;
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      await route.abort("failed");
    } else { receipts += 1; await route.continue(); }
  });
  const first = rows.first();
  const second = rows.nth(1);
  const initial = await rows.evaluateAll(elements => elements.map(element => element.getAttribute("data-dragkey")));
  const from = await first.getByRole("button", { name: "Arrastar para reordenar", exact: true }).boundingBox();
  const to = await second.boundingBox();
  expect(from).toBeTruthy(); expect(to).toBeTruthy();
  await page.mouse.move(from!.x + from!.width / 2, from!.y + from!.height / 2);
  await page.mouse.down();
  await page.mouse.move(from!.x + from!.width / 2, to!.y + to!.height / 2, { steps: 8 });
  await page.mouse.up();
  await expect.poll(() => posts).toBe(1);
  await expect.poll(() => receipts).toBe(1);
  await expect(page.getByText("A ordenação ainda precisa de conferência. Seu arraste foi preservado.")).toHaveCount(0);
  const matrix = await (await page.request.get(`/api/v1/backstage/catalog/?collection=${lab.curation_ref}`)).json();
  expect(matrix.matrix.rows.map((row: { sku: string }) => row.sku)).toEqual([...initial].reverse());
});

test("keyboard curation and frequent targets retain exact order without pointer input", async ({ page }) => {
  await login(page, "orders-lab-curation");
  await page.goto("/catalog");
  await page.getByRole("button", { name: new RegExp(lab.curation_name) }).click();
  const rows = page.locator("tr[data-dragkey]");
  await expect(rows).toHaveCount(2);
  const initial = await rows.evaluateAll(elements => elements.map(element => element.getAttribute("data-dragkey")));
  const handle = rows.first().getByRole("button", { name: "Arrastar para reordenar", exact: true });
  const box = await handle.boundingBox();
  expect(box!.width).toBeGreaterThanOrEqual(44); expect(box!.height).toBeGreaterThanOrEqual(44);
  await handle.focus();
  await page.keyboard.press("ArrowDown");
  await expect.poll(async () => (await (await page.request.get(`/api/v1/backstage/catalog/?collection=${lab.curation_ref}`)).json()).matrix.rows.map((row: { sku: string }) => row.sku)).toEqual([...initial].reverse());
  for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    for (const control of [rows.first().getByRole("switch").first(), rows.first().getByRole("button", { name: /^Preço em/ }).first(), rows.first().getByRole("button", { name: /^Ações de/ })]) {
      const bounds = await control.boundingBox();
      expect(bounds!.width).toBeGreaterThanOrEqual(44); expect(bounds!.height).toBeGreaterThanOrEqual(44);
    }
    if (viewport.width === 390) {
      const toggle = rows.first().getByRole("switch").first();
      await toggle.scrollIntoViewIfNeeded();
      await expect(toggle).toBeInViewport();
      await toggle.click({ trial: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
    }
    await page.screenshot({ path: fileURLToPath(new URL(`../../../../.orders-lab/integration-targets-${viewport.width}.png`, import.meta.url)), fullPage: true });
  }
  await page.goto(`/${lab.advance_ref}`);
  const primary = await page.getByRole("button", { name: "Marcar pronto", exact: true }).boundingBox();
  expect(primary!.width).toBeGreaterThanOrEqual(48); expect(primary!.height).toBeGreaterThanOrEqual(48);
});

test("cell lost response keeps one price intent and one canonical write", async ({ page }) => {
  await login(page, "orders-lab-price");
  await page.goto("/catalog");
  let posts = 0; let receipts = 0;
  await page.route("**/api/v1/backstage/catalog/cell/**", async route => {
    if (route.request().method() === "POST") {
      posts += 1;
      const response = await route.fetch(); expect(response.status()).toBe(200);
      await route.abort("failed");
    } else { receipts += 1; await route.continue(); }
  });
  await page.locator(`tr[data-dragkey="${lab.edit_sku}"]`).getByRole("button", { name: /^Preço em/ }).first().click();
  await page.locator('input[inputmode="decimal"]').fill("14,23");
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect.poll(() => receipts).toBe(1);
  await expect(page.getByRole("button", { name: "Salvar", exact: true })).toHaveCount(0);
  expect(posts).toBe(1);
  const matrix = await (await page.request.get("/api/v1/backstage/catalog/")).json();
  expect(matrix.matrix.rows.find((row: { sku: string }) => row.sku === lab.edit_sku).cells.find((cell: { surface_ref: string }) => cell.surface_ref === "lab").price_q).toBe(1423);
});

test("global pause lost response adopts product receipt without another toggle", async ({ page }) => {
  await login(page, "orders-lab-product");
  await page.goto("/catalog");
  let posts = 0; let receipts = 0;
  await page.route("**/api/v1/backstage/catalog/product/?*", async route => {
    if (route.request().method() === "POST") {
      posts += 1;
      const response = await route.fetch(); expect(response.status()).toBe(200);
      await route.abort("failed");
    } else { receipts += 1; await route.continue(); }
  });
  // The POST has no query; GET receipt carries ref and key.
  await page.route("**/api/v1/backstage/catalog/product/", async route => {
    posts += 1; const response = await route.fetch(); expect(response.status()).toBe(200); await route.abort("failed");
  });
  const row = page.locator(`tr[data-dragkey="${lab.edit_sku}"]`);
  await row.getByRole("button", { name: /^Ações de/ }).click();
  await page.getByRole("button", { name: "Pausar em todos os canais", exact: true }).click();
  await expect.poll(() => receipts).toBe(1); expect(posts).toBe(1);
  const detail = await (await page.request.get(`/api/v1/backstage/catalog/product/${lab.edit_sku}/`)).json();
  expect(detail.product.is_sellable).toBe(false);
});

test("back navigation keeps a product draft after declining discard", async ({ page }) => {
  await login(page, "orders-lab-edit");
  await page.getByRole("link", { name: "Catálogo", exact: true }).click();
  await page.locator(`tr[data-dragkey="${lab.edit_sku}"]`).getByRole("button", { name: /^Ações de/ }).click();
  await page.getByRole("button", { name: "Editar detalhes", exact: true }).click();
  const name = page.getByRole("textbox", { name: "Nome", exact: true });
  await name.fill("Rascunho antes de voltar");
  const confirmation = page.waitForEvent("dialog");
  await page.evaluate(() => history.back());
  const dialog = await confirmation;
  expect(dialog.message()).toContain("Há alterações sem confirmação");
  await dialog.dismiss();
  await expect(page).toHaveURL(/\/catalog$/);
  await expect(name).toHaveValue("Rascunho antes de voltar");
  await page.getByRole("button", { name: "Cancelar", exact: true }).click();
  await page.getByRole("button", { name: "Descartar e fechar", exact: true }).click();
  expect((await (await page.request.get(`/api/v1/backstage/catalog/product/${lab.edit_sku}/`)).json()).product.name).not.toBe("Rascunho antes de voltar");
});

test("delayed collection response cannot replace the selected resource", async ({ page }) => {
  await login(page, "orders-lab-curation");
  await page.goto("/catalog");
  let release!: () => void; let ready!: () => void; let delivered!: () => void;
  const deliveredResponse = new Promise<void>(resolve => { delivered = resolve; });
  const held = new Promise<void>(resolve => { release = resolve; });
  const received = new Promise<void>(resolve => { ready = resolve; });
  await page.route(`**/api/v1/backstage/catalog/?collection=${lab.curation_ref}`, async route => {
    const response = await route.fetch(); ready(); await held; await route.fulfill({ response }); delivered();
  });
  await page.getByRole("button", { name: new RegExp(lab.curation_name) }).click();
  await received;
  // Browser back to the full collection selector remains available during loading.
  await page.getByRole("button", { name: "Todas", exact: true }).click();
  await expect(page.locator('tr[data-dragkey="LAB-PROD-B"]')).toBeVisible();
  release();
  await deliveredResponse;
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page.locator('tr[data-dragkey="LAB-PROD-B"]')).toBeVisible();
});

test("publication preview leaves flags unchanged and lost confirmation response adopts one receipt", async ({ page }) => {
  await login(page, "orders-lab-price");
  await page.goto("/catalog");
  const state = async () => (await (await page.request.get("/api/v1/backstage/catalog/")).json()).matrix.rows.find((row: { sku: string }) => row.sku === lab.edit_sku).cells.find((cell: { surface_ref: string }) => cell.surface_ref === "lab").is_sellable;
  expect(await state()).toBe(true);
  await page.locator(`tr[data-dragkey="${lab.edit_sku}"]`).getByRole("checkbox").check();
  await page.locator('select').filter({ has: page.locator('option[value="*"]') }).selectOption("lab");
  let posts = 0, receipts = 0;
  await page.route("**/api/v1/backstage/catalog/bulk/**", async route => {
    if (route.request().method() === "POST" && !route.request().postDataJSON().preview) {
      posts += 1;
      const response = await route.fetch(); expect(response.status()).toBe(200);
      await route.abort("failed");
    } else { if (route.request().method() === "GET") receipts += 1; await route.continue(); }
  });
  await page.getByRole("button", { name: "Pausar", exact: true }).click();
  const preview = page.getByRole("region", { name: "Prévia de publicação", exact: true });
  await expect(preview).toBeVisible();
  expect(await state()).toBe(true); expect(posts).toBe(0);
  await preview.getByRole("button", { name: "Confirmar este lote", exact: true }).click();
  await expect(preview).toHaveCount(0);
  await expect.poll(() => receipts).toBe(1); expect(posts).toBe(1);
  expect(await state()).toBe(false);
});

async function observeCatalogStream(page: Page) {
  await page.addInitScript(() => {
    const state = window as unknown as { catalogPushes: number };
    state.catalogPushes = 0;
    const NativeEventSource = window.EventSource;
    window.EventSource = class extends NativeEventSource {
      constructor(url: string | URL, options?: EventSourceInit) {
        super(url, options);
        this.addEventListener("backstage-catalog-update", () => { state.catalogPushes += 1; });
      }
    };
  });
}

test("catalog SSE through Redis and BFF updates the row while preserving a price draft", async ({ page }, testInfo) => {
  await observeCatalogStream(page);
  await login(page, "orders-lab-price");
  const stream = page.waitForResponse(response => response.url().endsWith("/sse/catalog"));
  await page.goto("/catalog");
  expect((await stream).status()).toBe(200);
  const row = page.locator(`tr[data-dragkey="${lab.edit_sku}"]`);
  await expect(row).toBeVisible();
  expect((await row.locator("td").first().boundingBox())?.width, "Produto conserva área com múltiplos canais").toBeGreaterThanOrEqual(260);
  await row.getByRole("button", { name: /^Preço em/ }).first().click();
  const draft = page.locator('input[inputmode="decimal"]');
  await draft.fill("18,76");
  const detailPath = `/api/v1/backstage/catalog/product/${lab.edit_sku}/`;
  const observed = await (await page.request.get(detailPath)).json();
  const pushes = await page.evaluate(() => (window as unknown as { catalogPushes: number }).catalogPushes);
  const start = Date.now();
  const updatedName = `Atualização SSE ${start}`;
  const response = await page.request.patch(detailPath, { headers: { "Idempotency-Key": crypto.randomUUID() },
    data: { ...observed.action.payload_schema, patch: { name: updatedName } } });
  expect(response.status()).toBe(200);
  await expect.poll(() => page.evaluate(() => (window as unknown as { catalogPushes: number }).catalogPushes), { timeout: 5000 }).toBeGreaterThan(pushes);
  await expect(row).toContainText(updatedName);
  await expect(draft).toHaveValue("18,76");
  await expect(draft).toBeFocused();
  await testInfo.attach("synthetic-catalog-sse-latency", { body: JSON.stringify({ command_to_visible_ms: Date.now() - start, field_pilot: false }), contentType: "application/json" });
});

test("feed SSE updates active state without replacing the open collection draft", async ({ page }, testInfo) => {
  await observeCatalogStream(page);
  await login(page, "orders-lab-feed");
  const stream = page.waitForResponse(response => response.url().endsWith("/sse/catalog"));
  await page.goto("/feeds");
  expect((await stream).status()).toBe(200);
  const feed = page.locator("article").filter({ hasText: lab.feed_name });
  await feed.getByRole("button", { name: "Coleções", exact: true }).click();
  const draft = page.getByLabel(new RegExp(lab.collection_name));
  const initiallyChecked = await draft.isChecked();
  await draft.setChecked(!initiallyChecked);
  const state = await (await page.request.get("/api/v1/backstage/feeds/")).json();
  const observed = state.board.feeds.find((item: { ref: string }) => item.ref === lab.feed_ref);
  const action = observed.actions.find((item: { ref: string }) => item.ref === "active");
  const start = Date.now();
  const response = await page.request.post("/api/v1/backstage/feeds/active/", { headers: { "Idempotency-Key": crypto.randomUUID() },
    data: { ...action.payload_schema, ref: lab.feed_ref, is_active: !observed.is_active } });
  expect(response.status()).toBe(200);
  await expect(feed.getByRole("switch")).toHaveAttribute("aria-checked", String(!observed.is_active));
  await expect(draft).toHaveJSProperty("checked", !initiallyChecked);
  await expect(draft).toBeFocused();
  await expect(page.getByText("Coleções exibidas", { exact: true })).toBeVisible();
  await testInfo.attach("synthetic-feed-sse-latency", { body: JSON.stringify({ command_to_visible_ms: Date.now() - start, field_pilot: false }), contentType: "application/json" });
});

for (const resource of ["queue", "detail", "catalog", "feeds"]) {
  test(`last useful read remains visible during ${resource} read failure`, async ({ page }) => {
    await login(page, "orders-lab-read");
    const destination = { queue: "/", detail: `/${lab.notes_ref}`, catalog: "/catalog", feeds: "/feeds" }[resource]!;
    const endpoint = { queue: "/api/v1/backstage/orders/", detail: `/api/v1/backstage/orders/${lab.notes_ref}/`, catalog: "/api/v1/backstage/catalog/", feeds: "/api/v1/backstage/feeds/" }[resource]!;
    await page.goto(destination);
    const freshness = page.locator("[data-read-freshness]");
    await expect(freshness.getByText(/Última leitura útil:/)).toBeVisible();
    await page.route(`**${endpoint}?*`, route => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Synthetic read outage" }) }));
    await page.route(`**${endpoint}`, route => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Synthetic read outage" }) }));
    const refresh = page.getByRole("button", { name: /^Atualizar/ });
    await refresh.click();
    await expect(freshness).toContainText("atualização falhou");
    // A successful on-open read may already have been in flight at interception.
    // Once failure is visible, another failed read cannot advance the useful clock.
    const confirmed = await freshness.locator("time").getAttribute("datetime");
    const failure = page.waitForResponse(response => response.url().includes(endpoint) && response.status() === 503);
    await refresh.click();
    await failure;
    await expect(freshness.locator("time")).toHaveAttribute("datetime", confirmed!);
  });
}


test("confirmed note stays visible when the post-commit read fails", async ({ page }) => {
  await login(page, "orders-lab-notes");
  await page.goto(`/${lab.notes_ref}`);
  const note = page.getByPlaceholder("Instruções de preparo para a cozinha…");
  await expect(note).toBeVisible();
  const submitted = `Nota confirmada; leitura seguinte indisponível ${Date.now()}`;
  let blockRead = false;
  let posts = 0;
  await page.route(`**/api/v1/backstage/orders/${lab.notes_ref}/`, async route => {
    if (blockRead && route.request().method() === "GET") await route.abort("failed");
    else await route.continue();
  });
  await page.route(`**/api/v1/backstage/orders/${lab.notes_ref}/notes/`, async route => {
    if (route.request().method() === "POST") {
      blockRead = true; // Also block SSE reads racing the successful POST response.
      posts += 1;
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      await route.fulfill({ response }); // The mutation response is delivered intact.
    } else await route.continue();
  });
  await note.fill(submitted);
  await page.getByRole("button", { name: "Salvar nota", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Ação confirmada" })).toBeVisible();
  await expect(note).toHaveValue(submitted);
  const canonical = await (await page.request.get(`/api/v1/backstage/orders/${lab.notes_ref}/`)).json();
  expect(canonical.order.kitchen_note).toBe(submitted);
  expect(posts).toBe(1);
});


test("reason and note drafts require explicit discard across close, reload and navigation", async ({ page }) => {
  await login(page, "orders-lab-cancel");
  let commands = 0;
  page.on("request", request => { if (request.method() === "POST" && request.url().includes(`/orders/${lab.notes_ref}/`)) commands++; });
  await page.goto(`/${lab.notes_ref}`);
  const before = await (await page.request.get(`/api/v1/backstage/orders/${lab.notes_ref}/`)).json();
  const cancel = page.getByRole("button", { name: "Cancelar", exact: true });
  await cancel.focus();
  await page.keyboard.press("Enter");
  const reason = page.getByRole("textbox", { name: "Motivo", exact: true });
  const close = page.locator('[data-slot="dialog-close"]');
  await close.click({ trial: true });
  const closeBox = await close.boundingBox();
  expect(closeBox?.width).toBeGreaterThanOrEqual(44);
  expect(closeBox?.height).toBeGreaterThanOrEqual(44);
  await reason.fill("Motivo que não deve ser redigitado");
  async function declineReload() {
    const closed = page.waitForEvent("dialog");
    await page.evaluate(() => { setTimeout(() => window.location.reload(), 0); });
    const prompt = await closed;
    expect(prompt.type()).toBe("beforeunload");
    await prompt.dismiss();
  }
  page.once("dialog", async prompt => { expect(prompt.type()).toBe("confirm"); await prompt.dismiss(); });
  await page.getByRole("button", { name: "Voltar", exact: true }).click();
  await expect(reason).toHaveValue("Motivo que não deve ser redigitado");
  await declineReload();
  await expect(reason).toHaveValue("Motivo que não deve ser redigitado");
  page.once("dialog", async prompt => { expect(prompt.type()).toBe("confirm"); await prompt.accept(); });
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await cancel.click();
  await expect(reason).toHaveValue("");
  await page.getByRole("button", { name: "Voltar", exact: true }).click();
  const note = page.locator("textarea").first();
  await note.fill("Nota ainda não salva");
  page.once("dialog", async prompt => { expect(prompt.type()).toBe("confirm"); await prompt.dismiss(); });
  await page.getByRole("link", { name: "Voltar para a fila", exact: true }).click();
  await expect(note).toHaveValue("Nota ainda não salva");
  await declineReload();
  await expect(note).toHaveValue("Nota ainda não salva");
  await note.fill(before.order.kitchen_note);
  const after = await (await page.request.get(`/api/v1/backstage/orders/${lab.notes_ref}/`)).json();
  expect(after.order.status).toBe(before.order.status);
  expect(after.order.kitchen_note).toBe(before.order.kitchen_note);
  expect(commands).toBe(0);
});


test("queue rejection protects its reason on close and reload", async ({ page }) => {
  await login(page, "orders-lab-cancel");
  await page.goto("/");
  await page.getByRole("searchbox", { name: "Buscar por código, cliente ou item (atalho: /)", exact: true }).fill(lab.reject_ref);
  await page.getByRole("button", { name: "Recusar", exact: true }).click();
  const reason = page.getByRole("textbox", { name: "Motivo da recusa", exact: true });
  await reason.fill("Recusa ainda em avaliação");
  let confirmations = 0;
  page.once("dialog", async prompt => { confirmations++; expect(prompt.type()).toBe("confirm"); await prompt.dismiss(); });
  await page.getByRole("dialog").getByRole("button", { name: "Cancelar", exact: true }).click();
  expect(confirmations).toBe(1);
  await expect(reason).toHaveValue("Recusa ainda em avaliação");
  const reload = page.waitForEvent("dialog");
  await page.evaluate(() => { setTimeout(() => window.location.reload(), 0); });
  const prompt = await reload;
  expect(prompt.type()).toBe("beforeunload");
  await prompt.dismiss();
  await expect(reason).toHaveValue("Recusa ainda em avaliação");
  page.once("dialog", async prompt => { expect(prompt.type()).toBe("confirm"); await prompt.accept(); });
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const canonical = await (await page.request.get(`/api/v1/backstage/orders/${lab.reject_ref}/`)).json();
  expect(canonical.order.status).toBe("new");
});


test("bundled icons preserve utility size and mutually exclusive rail states", async ({ page }) => {
  await login(page);
  await page.mouse.move(800, 200);
  const glyph = page.locator('.iconify[class~="size-5"][class~="group-hover:hidden"]').first();
  const arrow = page.locator('.iconify[class~="group-hover:block"][class~="group-focus-visible:block"]').first();
  await expect(glyph).toBeVisible();
  await expect(arrow).toBeHidden();
  const box = await glyph.boundingBox();
  expect(box?.width).toBe(20);
  expect(box?.height).toBe(20);
  await glyph.hover();
  await expect(glyph).toBeHidden();
  await expect(arrow).toBeVisible();
  await page.mouse.move(800, 200);
  const link = glyph.locator('xpath=ancestor::a[1]');
  const linkBox = await link.boundingBox();
  expect(linkBox?.width).toBeGreaterThanOrEqual(44);
  expect(linkBox?.height).toBeGreaterThanOrEqual(44);
  await page.keyboard.press('Tab');
  await link.focus();
  await expect(glyph).toBeHidden();
  await expect(arrow).toBeVisible();
});
