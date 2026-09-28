// SONDA DE TEXTO CORTADO — o PDV inteiro, em três larguras de balcão.
//
// Queixa do dono (28/09/2026): "tem copy estourando o espaço disponível… muito
// deselegante" ("Dividir co…" no pagamento, o aviso do CPF da nota de entrega).
// Em vez de caçar caso a caso, esta sonda percorre as telas principais e MEDE
// todo elemento com texto que não cabe na própria caixa (`findClippedText`).
//
// O critério é o da casa (`violatesHouseRule`): texto de AÇÃO e de AVISO nunca
// se corta; DADO do usuário (nome de produto, endereço) pode ser truncado se o
// texto inteiro estiver no `title`. Qualquer violação reprova, com a lista.
//
// Roda contra um PDV de verdade (Django semeado + pos-nuxt), não contra o mock:
// as telas que estouram são as CHEIAS. Como rodar: tests/e2e-live/README.md.
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { expect, test, type Page } from "@playwright/test";

// @ts-expect-error — módulo JS puro, serializado e injetado na página como está.
import { findClippedText, violatesHouseRule } from "../../../operator-kit/tests/support/clippedText.js";

type Finding = {
  kind: string; role: string; titled: boolean; text: string; width: number; needed: number;
  height: number; neededHeight: number; selector: string;
};
type Measured = Finding & { screen: string; viewport: string };

const VIEWPORTS = [
  { width: 1366, height: 768 },
  { width: 1280, height: 800 },
  { width: 1024, height: 768 },
];
// A barra lateral do operador tem três estados (`RailToggle`); ESTENDIDA é a
// que mais rouba largura — é onde o "Dividir conta" virou "Dividir co…".
const RAILS = (process.env.PDV_LIVE_RAILS || "compact,extended").split(",") as Array<"compact" | "extended">;
const SHOTS = process.env.PDV_LIVE_SHOTS || "";
const CUSTOMER = process.env.PDV_LIVE_CUSTOMER || "Ana Ferreira";
const PRODUCTS = (process.env.PDV_LIVE_PRODUCTS || "Baguete Gergelim|Baguette Campagne|Croissant Tradicional|Pain au Chocolat").split("|");

const findings: Measured[] = [];
let currentRail: "compact" | "extended" = "compact";
const skipped: string[] = [];

async function measure(page: Page, screen: string) {
  // Transições de diálogo e o debounce da review assentam antes da medida.
  await page.waitForTimeout(600);
  const size = page.viewportSize();
  const viewport = `${size?.width}x${size?.height}${currentRail === "extended" ? "+barra" : ""}`;
  const found = (await page.evaluate(findClippedText, {})) as Finding[];
  for (const f of found) findings.push({ ...f, screen, viewport });
  if (SHOTS) {
    mkdirSync(SHOTS, { recursive: true });
    await page.screenshot({ path: `${SHOTS}/${viewport}-${screen.replace(/[^a-z0-9]+/gi, "_")}.png` });
  }
}

/** Um passo que não acha o que procura não derruba a varredura: fica anotado. */
async function step(page: Page, screen: string, run: () => Promise<unknown>) {
  try {
    await run();
    await measure(page, screen);
  } catch (error) {
    skipped.push(`${page.viewportSize()?.width}: ${screen} — ${String(error).split("\n")[0]}`);
  }
}

async function closeDialog(page: Page) {
  await page.keyboard.press("Escape");
  await page.getByRole("dialog").waitFor({ state: "hidden", timeout: 5000 }).catch(() => {});
}

async function login(page: Page) {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  const user = page.getByPlaceholder("Usuário");
  if (await user.isVisible({ timeout: 8000 }).catch(() => false)) {
    await measure(page, "login");
    const enter = page.getByRole("button", { name: "Entrar" });
    // Campo SSR antes da hidratação não liga o v-model: repete até o botão acordar.
    await expect(async () => {
      await user.fill(process.env.PDV_LIVE_USER || "");
      await page.getByPlaceholder("Senha").fill(process.env.PDV_LIVE_PASSWORD || "");
      await expect(enter).toBeEnabled({ timeout: 1000 });
    }).toPass({ timeout: 20_000 });
    await enter.click();
  }
  const station = page.getByRole("button", { name: "É este balcão" });
  const board = page.getByRole("button", { name: /Próxima livre/ });
  await station.or(board).first().waitFor({ timeout: 30_000 });
  if (await station.isVisible()) {
    await measure(page, "iniciar-dispositivo");
    await station.click();
  }
  await board.waitFor({ timeout: 30_000 });
}

async function openPayment(page: Page) {
  await page.getByRole("button", { name: /^Pagamento/ }).first().click();
  await page.getByRole("button", { name: /^Validar|^Autorizar/ }).first().waitFor();
}

async function openFreshTab(page: Page) {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  // Clique antes da hidratação não abre a comanda: repete até a venda aparecer.
  await expect(async () => {
    await page.getByRole("button", { name: /Próxima livre/ }).click();
    await page.getByPlaceholder(/Buscar produto/).waitFor({ timeout: 3000 });
  }).toPass({ timeout: 30_000 });
}

function exact(text: string) {
  return new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
}

async function addProducts(page: Page, names = PRODUCTS) {
  for (const name of names) {
    const search = page.getByPlaceholder(/Buscar produto/);
    await search.fill(name);
    const tile = page.getByRole("button", { name: exact(name) }).and(page.locator(":enabled")).first();
    // Esgotado não entra (o tile fica desabilitado): segue com os outros.
    if (await tile.isVisible({ timeout: 3000 }).catch(() => false)) await tile.click();
    await search.fill("");
  }
}

async function identifyCustomer(page: Page) {
  await page.keyboard.press("F6");
  await page.getByRole("dialog").waitFor();
  await measure(page, "dialogo-cliente-vazio");
  await page.getByRole("dialog").getByPlaceholder(/Buscar por nome/).fill(CUSTOMER.split(" ")[0]!);
  await page.getByRole("dialog").getByRole("option", { name: exact(CUSTOMER) }).first().click();
  await page.waitForTimeout(800);
}

async function removeTenders(page: Page) {
  const remove = page.getByRole("button", { name: /^Remover .* de / });
  while (await remove.first().isVisible().catch(() => false)) await remove.first().click();
}

for (const rail of RAILS) for (const viewport of VIEWPORTS) {
  test(`PDV sem texto cortado em ${viewport.width}x${viewport.height}, barra ${rail}`, async ({ browser }) => {
    currentRail = rail;
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    await login(page);
    if (rail === "extended") await page.getByRole("button", { name: "Expandir barra" }).click();
    await measure(page, "comandas");
    await step(page, "ultimas-vendas", async () => {
      await page.getByRole("button", { name: /Últimas vendas|Vendas recentes/ }).first().click();
      await page.getByRole("dialog").waitFor();
    });
    await closeDialog(page);
    await step(page, "atalhos", async () => {
      await page.getByRole("button", { name: /Atalhos/ }).first().click();
      await page.getByRole("dialog").waitFor();
    });
    await closeDialog(page);

    // ── BALCÃO ──
    await openFreshTab(page);
    await measure(page, "venda-balcao-vazia");
    await addProducts(page);
    await measure(page, "venda-balcao-itens");
    await step(page, "dialogo-cliente-escolhido", () => identifyCustomer(page));
    await closeDialog(page);

    await openPayment(page);
    await measure(page, "pagamento-balcao");
    for (const method of ["Dinheiro", "Pix", "Crédito", "Débito", "Link de pagamento"]) {
      await step(page, `pagamento-balcao-${method}`, async () => {
        await removeTenders(page);
        await page.getByRole("button", { name: new RegExp(`^${method}`) }).and(page.locator(":enabled")).first().click();
      });
    }
    await removeTenders(page);
    await step(page, "dialogo-desconto", async () => { await page.keyboard.press("F9"); await page.getByRole("dialog").waitFor(); });
    await closeDialog(page);
    await step(page, "dialogo-dividir-conta", async () => { await page.keyboard.press("F10"); await page.getByRole("dialog").waitFor(); });
    await closeDialog(page);

    // ── ENCOMENDA DE ENTREGA, PARA AMANHÃ ──
    // O bloqueio "Entrega com nota fiscal: falta o CPF" depende do resolver
    // fiscal do ambiente. Para medi-lo em qualquer banco, a review desta venda
    // responde que a nota da entrega é exigida — a tela é o que se mede.
    await page.route("**/pos/sale/review/**", async (route) => {
      const response = await route.fetch();
      const body = await response.json().catch(() => null);
      if (body?.review) {
        await route.fulfill({ response, json: { ...body, review: { ...body.review, delivery_tax_id_required: true } } });
      } else {
        await route.fulfill({ response });
      }
    });
    // A encomenda nasce guiada: cliente → recebimento → data → "Montar encomenda".
    await openFreshTab(page);
    await step(page, "encomenda-nova", async () => {
      await page.getByRole("group", { name: "Modo de atendimento" }).getByRole("button", { name: "Encomendas" }).click();
      await page.getByRole("button", { name: /Montar encomenda/ }).waitFor();
    });
    await step(page, "encomenda-cliente", () => identifyCustomer(page));
    await closeDialog(page);
    await step(page, "dialogo-recebimento", async () => { await page.keyboard.press("F7"); await page.getByRole("dialog").waitFor(); });
    await step(page, "dialogo-recebimento-entrega", async () => {
      const dialog = page.getByRole("dialog");
      await dialog.getByRole("button", { name: /^Entrega/ }).first().click();
      const saved = dialog.locator("button").filter({ hasText: /Casa|Trabalho|Rua|Av/ }).first();
      if (await saved.isVisible().catch(() => false)) await saved.click();
    });
    await page.getByRole("dialog").getByRole("button", { name: /Entrega neste endereço|Retirada no balcão/ }).click().catch(() => closeDialog(page));
    await step(page, "dialogo-quando", async () => { await page.keyboard.press("F8"); await page.getByRole("dialog").waitFor(); });
    await step(page, "dialogo-quando-amanha", async () => {
      await page.getByRole("dialog").getByRole("button", { name: /^Amanhã/ }).first().click();
    });
    await page.getByRole("dialog").getByRole("button", { name: "Confirmar dia e horário" }).click().catch(() => closeDialog(page));
    await step(page, "encomenda-combinada", async () => {
      await page.getByRole("button", { name: /Montar encomenda/ }).waitFor();
    });
    await page.getByRole("button", { name: /Montar encomenda/ }).click().catch(() => {});
    await addProducts(page, PRODUCTS.slice(0, 1));
    await measure(page, "venda-encomenda-entrega-cabecalho");
    await step(page, "pagamento-encomenda-entrega", () => openPayment(page));
    // Cada cobrança muda os bloqueios: a nota da entrega (CPF), o link, o Pix.
    for (const [collection, method] of [
      ["No balcão", "Dinheiro"], ["No balcão", "Pix"], ["No balcão", "Crédito"], ["No balcão", "Link de pagamento"],
      ["Na entrega", "Dinheiro"], ["Na entrega", "Crédito"],
    ] as const) {
      await step(page, `pagamento-encomenda-entrega-${collection}-${method}`, async () => {
        await removeTenders(page);
        await page.getByRole("button", { name: new RegExp(`^${collection}`) }).first().click().catch(() => {});
        await page.getByRole("button", { name: new RegExp(`^${method}`) }).and(page.locator(":enabled")).first().click();
      });
    }
    await step(page, "pagamento-encomenda-dividir-conta", async () => { await page.keyboard.press("F10"); await page.getByRole("dialog").waitFor(); });
    await closeDialog(page);

    // ── VENDA FECHADA: o resultado ──
    await openFreshTab(page);
    await addProducts(page, PRODUCTS.slice(0, 1));
    await step(page, "resultado-da-venda", async () => {
      await openPayment(page);
      await page.getByRole("button", { name: /^Dinheiro/ }).first().click();
      await page.getByRole("button", { name: /^Exato/ }).click();
      await page.getByRole("button", { name: /^Validar/ }).click();
      await page.getByText(/Nova venda|Venda concluída|Troco/).first().waitFor({ timeout: 15_000 });
    });

    // ── ENCOMENDAS ──
    for (const path of ["/preorders", "/preorders/today", "/preorders/week", "/preorders/panel"]) {
      await step(page, `encomendas${path.replace("/preorders", "") || "-inicio"}`, async () => {
        await page.goto(path);
        await page.waitForLoadState("networkidle");
      });
    }
    await step(page, "encomenda-detalhe", async () => {
      await page.goto("/preorders/week");
      await page.waitForLoadState("networkidle");
      await page.locator('a[href*="/preorders/"]').filter({ hasNotText: /Hoje|Semana|Painel/ }).first().click();
      await page.waitForLoadState("networkidle");
    });

    // ── CAIXA ──
    await step(page, "caixa-sessao", async () => { await page.goto("/session"); await page.waitForLoadState("networkidle"); });
    for (const [label, screen] of [
      [/^Saída de caixa/, "dialogo-saida-de-caixa"],
      [/^Entrada de caixa/, "dialogo-entrada-de-caixa"],
      [/^Pedir troco/, "dialogo-pedir-troco"],
      [/^Fechar (o )?caixa/, "dialogo-fechar-caixa"],
    ] as const) {
      await step(page, screen, async () => {
        await page.getByRole("button", { name: label }).first().click();
        await page.getByRole("dialog").waitFor();
      });
      await closeDialog(page);
    }
    await step(page, "caixa-fechamento-do-dia", async () => { await page.goto("/session/closing"); await page.waitForLoadState("networkidle"); });
    await step(page, "caixa-relatorio", async () => { await page.goto("/session/report"); await page.waitForLoadState("networkidle"); });

    await context.close();
  });
}

test.afterAll(() => {
  const out = process.env.PDV_LIVE_REPORT || "test-results/copy-overflow.json";
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, JSON.stringify({ findings, skipped }, null, 2));
  const violations = findings.filter(violatesHouseRule);
  expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
});
