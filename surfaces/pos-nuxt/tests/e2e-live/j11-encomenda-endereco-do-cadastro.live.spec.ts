// JORNADA J11 — encomenda de entrega com endereço do cadastro (EXCELENCIA-PDV WP-E13,
// pedido do dono de 19/11/2026, #2754).
//
// A Caixa (Fran) monta uma encomenda de entrega para a Maria Santos, que tem três
// endereços no cadastro: Casa (o padrão), Trabalho e um salvo de pedido de entrega,
// sem etiqueta, como o sistema grava (é o do cliente vindo do iFood, #2775).
//
// O que a jornada prova, pela tela, no celular (375 px) e no balcão (1366 px):
//   1. a encomenda pede o cliente, depois "para quando", depois o recebimento;
//   2. ao escolher Entrega, o endereço padrão já vem marcado, numa lista de linha
//      inteira em que cada endereço se identifica sozinho (o sem etiqueta não ganha
//      "Outro" nem "Entrega": quem fala é o endereço);
//   3. no balcão, a seta desce para outro endereço e o Enter aceita e segue; no
//      celular, o toque na linha escolhe e "Montar encomenda" segue;
//   4. a barra da venda vem na ordem cliente, quando, recebimento, com F6, F7 e F8;
//   5. no Recebimento (F8), "Tirar o endereço desta entrega" devolve a entrega a
//      "sem endereço", diz que o cadastro não mudou e deixa desfazer ali mesmo.
// Como rodar: README.md desta pasta.
import { audits, still } from "./support/audit";
import { capture, expect, settled, test, type Page } from "./support/operator";
import { picksNextOpenDay } from "./support/schedule";

const CUSTOMER = process.env.PDV_LIVE_ADDRESS_CUSTOMER || "Maria Santos";
const CUSTOMER_PHONE = process.env.PDV_LIVE_ADDRESS_PHONE || "43991111111";
// Os três endereços do seed (`config/management/commands/seed.py`, `_seed_addresses`),
// na ordem do cadastro: o padrão, o salvo de pedido de entrega e o do trabalho.
const HOME = "Rua Belo Horizonte, 540, Apto 12";
const WORK = "Av. Higienópolis, 350, Sala 201";
const FROM_DELIVERY = "Rua Sergipe, 890";

function exact(text: string) {
  return new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
}

async function opensOrder(page: Page) {
  await page.getByRole("link", { name: /^Encomendas/ }).locator("visible=true").first().click();
  await settled(page);
  await page.getByRole("button", { name: /^Nova( encomenda)?$/ }).locator("visible=true").first().click({ timeout: 30_000 });
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
  const done = dialog.getByRole("button", { name: "Concluir", exact: true });
  await expect(async () => {
    if (await done.isVisible().catch(() => false)) await done.click({ timeout: 2000 });
    await expect(dialog).toBeHidden({ timeout: 2000 });
  }).toPass({ timeout: 30_000 });
}

/** A etapa da vez do assistente, pela trilha (`aria-current="step"`). */
function currentStep(page: Page) {
  return page.locator("[data-order-step-nav][aria-current='step']");
}

/**
 * A GEOMETRIA da lista de endereços: cada linha ocupa a largura inteira do bloco em
 * que mora (bordas iguais entre as linhas e iguais às do bloco), tem altura de alvo de
 * toque, e nada transborda para o lado.
 */
async function auditsAddressList(page: Page, label: string, blockSelector: string, minRowHeight: number) {
  const report = await page.evaluate((block) => {
    const visible = (el: Element) => (el as HTMLElement).offsetParent !== null;
    const list = Array.from(document.querySelectorAll("[data-pos-saved-addresses]")).find(visible)!;
    const container = list.closest(block)!;
    const style = getComputedStyle(container);
    const box = container.getBoundingClientRect();
    const inner = {
      left: Math.round(box.left + Number.parseFloat(style.paddingLeft) + Number.parseFloat(style.borderLeftWidth)),
      right: Math.round(box.right - Number.parseFloat(style.paddingRight) - Number.parseFloat(style.borderRightWidth)),
    };
    const rows = Array.from(list.querySelectorAll('[data-slot="item"]')).map((row) => {
      const r = row.getBoundingClientRect();
      return { left: Math.round(r.left), right: Math.round(r.right), height: Math.round(r.height) };
    });
    const buttons = Array.from(container.querySelectorAll("button")).filter(visible)
      .filter((button) => button.getAttribute("role") !== "radio")
      .map((button) => ({ text: (button.textContent || "").trim().slice(0, 40), height: Math.round(button.getBoundingClientRect().height) }));
    return {
      inner,
      rows,
      buttons,
      overflowX: document.documentElement.scrollWidth - window.innerWidth,
      viewport: window.innerWidth,
    };
  }, blockSelector);
  console.log(`AUDITORIA geometria ${label}: ${JSON.stringify(report)}`);
  expect(report.rows.length, `${label}: nenhuma linha de endereço`).toBeGreaterThan(0);
  for (const row of report.rows) {
    // 1 px de folga: a borda do bloco cai em meio pixel conforme a largura da tela.
    expect(Math.abs(row.left - report.inner.left), `${label}: a linha começa na borda do bloco`).toBeLessThanOrEqual(1);
    expect(Math.abs(row.right - report.inner.right), `${label}: a linha termina na borda do bloco`).toBeLessThanOrEqual(1);
    expect(row.height, `${label}: altura da linha (alvo de toque)`).toBeGreaterThanOrEqual(minRowHeight);
  }
  for (const button of report.buttons) {
    expect(button.height, `${label}: altura do botão "${button.text}"`).toBeGreaterThanOrEqual(32);
  }
  expect(report.overflowX, `${label}: transbordo horizontal`).toBeLessThanOrEqual(0);
  return report;
}

const LIST_TEXT = "[data-pos-saved-addresses] legend, [data-pos-saved-address-line], [data-pos-saved-address-detail], [data-pos-saved-address-tag]";

/** Aviso passageiro na tela (o parabéns do aniversariante, por exemplo): a Fran lê e fecha. */
async function dismissesNotices(page: Page) {
  const close = page.locator("[data-sonner-toast] [data-close-button]");
  for (let left = await close.count(); left > 0; left -= 1) {
    await close.first().click({ timeout: 5000 }).catch(() => undefined);
  }
  await expect(page.locator("[data-sonner-toast]")).toHaveCount(0, { timeout: 15_000 });
}

test.describe.configure({ mode: "serial" });

for (const device of ["phone", "counter"] as const) {
  test.describe(`J11 Encomenda de entrega com endereço do cadastro · ${device === "phone" ? "375 px" : "1366 px"}`, () => {
    test.use({ device });

    test("cliente, para quando, entrega: o endereço padrão já vem marcado e sai da entrega sem sair do cadastro", async ({ cashierAtCounter: page }, testInfo) => {
      test.setTimeout(8 * 60_000);
      const keyboard = device === "counter";

      // 1 · A encomenda nova pede o CLIENTE.
      await opensOrder(page);
      await expect(currentStep(page)).toHaveAttribute("aria-label", "1. Cliente");
      await expect(page.locator("[data-order-step-nav]")).toHaveCount(3);
      await capture(page, testInfo, "encomenda-pede-o-cliente");

      // 2 · Depois do cliente, "PARA QUANDO" (não mais o recebimento).
      await identifiesCustomer(page);
      await dismissesNotices(page);
      await expect(currentStep(page)).toHaveAttribute("aria-label", "2. Data e horário", { timeout: 30_000 });
      await expect(page.getByRole("heading", { name: "Para quando?" })).toBeVisible();
      await capture(page, testInfo, "depois-pra-quando");
      // O próximo dia em que a loja abre: amanhã, ou a próxima data quando amanhã é
      // dia fechado (#2976).
      await picksNextOpenDay(page);
      // O dia escolhido não empurra a tela: a etapa ainda pergunta o horário.
      await expect(currentStep(page)).toHaveAttribute("aria-label", "2. Data e horário, pronta", { timeout: 30_000 });
      const slot = page.locator('[data-order-step="schedule"]').getByRole("button")
        .filter({ hasText: /\d{1,2}h|\d{2}:\d{2}/ }).and(page.locator(":enabled")).first();
      await slot.click({ timeout: 30_000 });
      await capture(page, testInfo, "dia-e-horario-no-cartao");
      await page.getByRole("button", { name: "Continuar", exact: true }).click();

      // 3 · Só então o RECEBIMENTO.
      await expect(currentStep(page)).toHaveAttribute("aria-label", "3. Recebimento");
      await expect(page.getByRole("heading", { name: "Entrega ou retirada?" })).toBeVisible();
      await capture(page, testInfo, "depois-o-recebimento");

      // 4 · Entrega: o endereço PADRÃO já vem marcado, cada endereço em linha inteira.
      await page.locator("[data-order-fulfillment-options]").getByRole("radio", { name: /^Entrega/ }).click();
      await expect(currentStep(page)).toHaveAttribute("aria-label", "4. Endereço, pronta", { timeout: 30_000 });
      const step = page.locator('[data-order-step="address"]');
      const radios = step.getByRole("radio");
      await expect(radios).toHaveCount(3);
      await expect(radios.nth(0)).toBeChecked();
      await expect(step.locator("[data-pos-saved-address-line]")).toHaveText([HOME, FROM_DELIVERY, WORK]);
      // A etiqueta do cliente aparece; o endereço sem etiqueta não ganha "Outro" nem "Entrega".
      await expect(step.locator("[data-pos-saved-address-tag]")).toHaveText(["Casa", "Trabalho"]);
      await expect(step.locator("[data-pos-saved-addresses]")).not.toContainText("Entrega");
      await expect(step.locator("[data-pos-saved-addresses]")).not.toContainText("Outro");
      if (keyboard) await expect(radios.nth(0)).toBeFocused();
      await still(page);
      await audits(page, "lista no assistente", LIST_TEXT, { fontScale: true, crushed: true });
      await audits(page, "gestos do endereço", "[data-order-address-other], [data-order-address-clear]", { fontScale: true, crushed: true });
      await auditsAddressList(page, "assistente", '[data-order-step="address"]', 44);
      await capture(page, testInfo, "entrega-padrao-ja-marcado");

      // 5 · Outro endereço: a seta desce e o Enter aceita e segue (balcão); o toque na
      // linha escolhe e "Montar encomenda" segue (celular).
      if (keyboard) {
        // A tecla desce e sobe como no dedo: o grupo de rádio marca a opção com a
        // seta ainda apertada, e um toque instantâneo de robô soltaria antes.
        await page.keyboard.down("ArrowDown");
        await expect(radios.nth(1)).toBeChecked();
        await page.keyboard.up("ArrowDown");
        await expect(radios.nth(1)).toBeFocused();
        await capture(page, testInfo, "seta-escolhe-outro");
        await page.keyboard.press("Enter");
      } else {
        await step.locator("[data-pos-saved-address-line]").nth(1).click();
        await expect(radios.nth(1)).toBeChecked();
        await capture(page, testInfo, "toque-escolhe-outro");
        await page.getByRole("button", { name: /Montar encomenda/ }).click();
      }
      await expect(page.getByPlaceholder(/Buscar produto/).locator("visible=true").first()).toBeVisible({ timeout: 30_000 });

      // 6 · A barra da venda: cliente, quando, recebimento. No balcão cada chip leva a
      // tecla da posição (F6, F7, F8); no celular os dois moram no "Mais ações".
      if (keyboard) {
        const bar = page.locator("[data-pos-sale-bar]");
        await expect(bar.locator("[data-context-entry]")).toHaveCount(3);
        const order = await bar.locator("[data-context-entry]").evaluateAll((chips) => chips.map((chip) => chip.getAttribute("data-context-entry")));
        expect(order).toEqual(["customer", "schedule", "fulfillment"]);
        await expect(bar.locator('[data-context-entry="schedule"] kbd')).toHaveText("F7");
        await expect(bar.locator('[data-context-entry="fulfillment"] kbd')).toHaveText("F8");
        await expect(bar.locator('[data-context-entry="fulfillment"]')).toContainText("Entrega · Centro");
        await audits(page, "barra da venda", "[data-pos-sale-bar] [data-context-entry] span:not(:has(*))", { fontScale: true, crushed: true });
        await capture(page, testInfo, "barra-da-venda-na-ordem-nova");
        // F7 abre o Quando (era o Recebimento) e F8 abre o Recebimento (era o Quando).
        await page.keyboard.press("F7");
        await expect(page.getByRole("dialog", { name: "Quando" })).toBeVisible({ timeout: 30_000 });
        await still(page);
        await capture(page, testInfo, "f7-abre-o-quando");
        await page.keyboard.press("Escape");
        await expect(page.getByRole("dialog", { name: "Quando" })).toBeHidden();
        await page.keyboard.press("F8");
      } else {
        await page.getByRole("button", { name: /^Mais ações/ }).locator("visible=true").first().click();
        const items = page.getByRole("menuitem");
        await expect(items.filter({ hasText: /^Quando:/ })).toBeVisible({ timeout: 30_000 });
        const labels = (await items.allTextContents()).map((text) => text.trim());
        expect(labels.findIndex((text) => text.startsWith("Quando:")))
          .toBeLessThan(labels.findIndex((text) => text.startsWith("Recebimento:")));
        await still(page);
        await capture(page, testInfo, "mais-acoes-quando-antes-do-recebimento");
        await items.filter({ hasText: /^Recebimento:/ }).click();
      }

      // 7 · No Recebimento, a mesma lista, com o endereço escolhido marcado.
      const dialog = page.getByRole("dialog", { name: "Recebimento" });
      await expect(dialog).toBeVisible({ timeout: 30_000 });
      const dialogRadios = dialog.locator("[data-pos-saved-addresses]").getByRole("radio");
      await expect(dialogRadios).toHaveCount(3);
      await expect(dialogRadios.nth(1)).toBeChecked();
      if (keyboard) await expect(dialogRadios.nth(1)).toBeFocused();
      await still(page);
      await audits(page, "lista no Recebimento", LIST_TEXT, { fontScale: true, crushed: true });
      await auditsAddressList(page, "Recebimento", ".grid.gap-3", 44);
      await capture(page, testInfo, "recebimento-lista-de-linha-inteira");

      // 8 · Tirar o endereço DESTA entrega: ela volta a "sem endereço"; o cadastro fica.
      const clear = dialog.locator("[data-pos-address-clear]");
      await expect(clear).toHaveText("Tirar o endereço desta entrega");
      await clear.scrollIntoViewIfNeeded();
      await audits(page, "endereço da entrega e o gesto de tirar", "[data-pos-address-summary] p, [data-pos-address-clear]", { fontScale: true, crushed: true });
      await clear.click();
      await expect(dialogRadios.nth(0)).not.toBeChecked();
      await expect(dialogRadios.nth(1)).not.toBeChecked();
      await expect(dialogRadios.nth(2)).not.toBeChecked();
      await expect(dialogRadios).toHaveCount(3);
      // A frase fica no lugar do endereço, dentro do diálogo, com o Desfazer ao lado.
      const removed = dialog.locator("[data-pos-address-removed]");
      await expect(removed).toBeVisible({ timeout: 30_000 });
      await expect(removed.locator("p")).toHaveText("Endereço tirado desta entrega. O cadastro do cliente não mudou.");
      await removed.scrollIntoViewIfNeeded();
      await still(page);
      await audits(page, "endereço tirado", "[data-pos-address-removed] p, [data-pos-address-restore]", { fontScale: true, crushed: true });
      await capture(page, testInfo, "endereco-tirado-da-entrega");

      // 9 · O Desfazer devolve o endereço, e o diálogo continua aberto.
      await removed.locator("[data-pos-address-restore]").click();
      await expect(dialogRadios.nth(1)).toBeChecked({ timeout: 30_000 });
      await expect(removed).toBeHidden();
      await expect(dialog).toBeVisible();
      // Outro endereço, agora pelo toque na linha: o do trabalho.
      await dialog.locator("[data-pos-saved-address-line]").nth(2).click();
      await expect(dialogRadios.nth(2)).toBeChecked();
      await still(page);
      await capture(page, testInfo, "outro-endereco-escolhido-no-recebimento");
      await dialog.locator("[data-pos-fulfillment-confirm]").click();
      await expect(dialog).toBeHidden({ timeout: 30_000 });
      if (keyboard) {
        await expect(page.locator('[data-pos-sale-bar] [data-context-entry="fulfillment"]')).toContainText("Entrega · Higienópolis");
      }
    });
  });
}
