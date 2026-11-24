import { expect, test, type Locator, type Page } from "@playwright/test";

import {
  lockDevice,
  managerReleasesDevice,
  operatorUnlocksWithPin,
} from "./support/operator";
import { capture, cast, device, settled } from "./support/stack";

// J-P3 (docs/plans/EXCELENCIA-PRODUCAO-PLANO.md, seção 8; WP-F01 a recusa, WP-F07 a
// tela): zerar não cancela. A Cozinha corrige o lote planejado para 0 e lê, no lugar do
// botão, "Cancelar lote é com o gerente."; nada vai ao servidor. A Gerente, com o PIN
// dela, abre "Cancelar lote…" no lote de hoje com encomenda e lê, antes do botão,
// quantas unidades e quais pedidos dependem dele (no tablet e no celular); escolhe o
// motivo e cancela. No celular, ela também tira do plano um lote sem encomenda, com o
// motivo escrito.
//
// O lote com encomenda é o Croissant Manteiga de hoje, que o seed planeja com pedidos
// vinculados; o sem encomenda é a Focaccia do dia, no Planejamento de amanhã. A jornada
// cancela os dois, então roda uma vez por seed.
//
// Ficou para depois (#3364): a encomenda nascendo pela loja e o aceite pela Caixa
// (a J3 do Gestor), que exigem a loja e o Gestor compilados na mesma pilha.
const WITH_ORDERS = process.env.JP3_LOT_WITH_ORDERS || "Croissant Manteiga";
const FREE = process.env.JP3_LOT_FREE || "Focaccia do dia";
const STAKES = /\d+ un\. encomendadas?: \d+ pedidos?$/;

async function openPlanning(page: Page) {
  await page.goto("/plan");
  await settled(page);
}

/** O item planejado do produto, no Planejamento: abre o menu "corrigir, novo lote…". */
function plannedItem(page: Page, product: string) {
  return page
    .getByRole("button", { name: new RegExp(`^${product}, .*: corrigir`) })
    .first();
}

/** O diálogo terminou de entrar: a captura não pega o modal translúcido no meio da
 *  animação (medido na primeira rodada desta jornada). */
async function steady(dialog: Locator) {
  await expect(dialog).toBeVisible();
  await dialog.evaluate((element) =>
    Promise.all(
      element
        .getAnimations({ subtree: true })
        .map((animation) => animation.finished.catch(() => undefined)),
    ),
  );
  await expect
    .poll(() =>
      dialog.evaluate((element) => Number(getComputedStyle(element).opacity)),
    )
    .toBe(1);
}

/** Auditoria da prévia: o que decide o gesto está inteiro na tela e o texto se lê
 *  (contraste WCAG de pelo menos 4,5 contra o fundo efetivo). */
async function legible(page: Page, target: Locator, what: string) {
  await expect(target, `${what} na tela`).toBeInViewport({ ratio: 1 });
  const ratio = await target.evaluate((element) => {
    // O tema fala oklch e color-mix: o canvas do navegador converte qualquer cor CSS
    // para RGBA de 8 bits, que é o que a fórmula do WCAG lê.
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1;
    const paint = canvas.getContext("2d", { willReadFrequently: true })!;
    const rgb = (value: string): number[] => {
      paint.clearRect(0, 0, 1, 1);
      paint.fillStyle = "#000";
      paint.fillStyle = value;
      paint.fillRect(0, 0, 1, 1);
      const [r, g, b, a] = paint.getImageData(0, 0, 1, 1).data;
      return [r!, g!, b!, a! / 255];
    };
    const luminance = ([r, g, b]: number[]) => {
      const channel = (c: number) => {
        const v = c / 255;
        return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
      };
      return 0.2126 * channel(r!) + 0.7152 * channel(g!) + 0.0722 * channel(b!);
    };
    // Compõe os fundos translúcidos de dentro para fora até o primeiro opaco.
    let layers: number[][] = [];
    for (let node: Element | null = element; node; node = node.parentElement) {
      const bg = rgb(getComputedStyle(node).backgroundColor);
      const alpha = bg[3]!;
      if (alpha > 0) layers.push([bg[0]!, bg[1]!, bg[2]!, alpha]);
      if (alpha >= 1) break;
    }
    if (!layers.length || layers[layers.length - 1]![3]! < 1)
      layers.push([255, 255, 255, 1]);
    layers = layers.reverse();
    let base = layers[0]!.slice(0, 3);
    for (const [r, g, b, a] of layers.slice(1))
      base = [r! * a! + base[0]! * (1 - a!), g! * a! + base[1]! * (1 - a!), b! * a! + base[2]! * (1 - a!)];
    const fg = rgb(getComputedStyle(element).color);
    const fgAlpha = fg[3]!;
    const text = fg.slice(0, 3).map((c, i) => c * fgAlpha + base[i]! * (1 - fgAlpha));
    const [l1, l2] = [luminance(text), luminance(base)].sort((a, b) => b - a);
    return (l1! + 0.05) / (l2! + 0.05);
  });
  expect(ratio, `contraste de ${what}`).toBeGreaterThanOrEqual(4.5);
}

async function managerCancelsFromProduction(page: Page) {
  await page.goto("/");
  await settled(page);
  await page
    .getByRole("button", { name: `Mais ações de ${WITH_ORDERS}` })
    .first()
    .click();
  await page.getByRole("menuitem", { name: "Cancelar lote…" }).click();
  const dialog = page.getByRole("dialog");
  await steady(dialog);
  return dialog;
}

test("J-P3: zerar não cancela; cancelar diz o que está em jogo", async ({
  browser,
  baseURL,
}, testInfo) => {
  // ── O tablet da bancada (1024 px, toque) ────────────────────────────────────
  const tabletContext = await device(browser, "tablet", baseURL!);
  const tablet = await tabletContext.newPage();
  await managerReleasesDevice(tablet);
  await lockDevice(tablet);
  await operatorUnlocksWithPin(tablet, cast.kitchen);

  // A Cozinha corrige um lote planejado para 0.
  await openPlanning(tablet);
  const item = plannedItem(tablet, WITH_ORDERS);
  await expect(
    item,
    `o lote planejado do ${WITH_ORDERS} não está no Planejamento: a J-P3 roda uma vez por seed`,
  ).toBeVisible();
  await item.click();
  await tablet.getByRole("menuitem", { name: "Corrigir quantidade" }).click();
  const planDialog = tablet.getByRole("dialog");
  await steady(planDialog);
  await planDialog
    .getByRole("textbox", { name: "Quantidade planejada" })
    .fill("0");
  const hint = planDialog.getByText("Cancelar lote é com o gerente.", {
    exact: true,
  });
  await expect(hint).toBeVisible();
  await expect(
    planDialog.getByRole("button", { name: "Remover do plano" }),
  ).toHaveCount(0);
  await legible(tablet, hint, "a frase de quem cancela");
  await capture(tablet, testInfo, "cozinha-zero-e-com-o-gerente");
  // Sair sem mudar nada é "Fechar": num diálogo sobre cancelar lote, "Cancelar"
  // leria como cancelar o lote. O X do canto tem o mesmo nome; é o do rodapé.
  await expect(
    planDialog.getByRole("button", { name: "Cancelar", exact: true }),
  ).toHaveCount(0);
  await planDialog
    .getByRole("button", { name: "Fechar", exact: true })
    .last()
    .click();
  await expect(planDialog).toBeHidden();
  await expect(plannedItem(tablet, WITH_ORDERS)).toBeVisible();

  // A Gerente assume o tablet com o PIN dela e abre o cancelamento do lote de hoje.
  await lockDevice(tablet);
  await operatorUnlocksWithPin(tablet, cast.manager);
  const tabletCancel = await managerCancelsFromProduction(tablet);
  const tabletStakes = tabletCancel.getByText(STAKES);
  await expect(tabletStakes).toBeVisible();
  await legible(tablet, tabletStakes, "o que está encomendado");
  const tabletConfirm = tabletCancel.getByRole("button", {
    name: "Confirmar cancelamento",
  });
  await expect(tabletConfirm, "sem motivo, o cancelamento não sai").toBeDisabled();
  await expect(tabletConfirm).toBeInViewport({ ratio: 1 });
  await tabletCancel.getByRole("button", { name: "Planejado a mais" }).click();
  await expect(tabletConfirm).toBeEnabled();
  await capture(tablet, testInfo, "gerente-tablet-cancelar-o-que-esta-em-jogo");
  // Ela confere no celular antes de decidir: fecha aqui sem cancelar.
  // O "Fechar" do rodapé (o X do canto tem o mesmo nome).
  await tabletCancel
    .getByRole("button", { name: "Fechar", exact: true })
    .last()
    .click();
  await expect(tabletCancel).toBeHidden();

  // ── O celular da Gerente (375 px) ───────────────────────────────────────────
  const phoneContext = await device(browser, "phone", baseURL!);
  const phone = await phoneContext.newPage();
  await managerReleasesDevice(phone);
  await lockDevice(phone);
  await operatorUnlocksWithPin(phone, cast.manager);

  const phoneCancel = await managerCancelsFromProduction(phone);
  const phoneStakes = phoneCancel.getByText(STAKES);
  await expect(phoneStakes).toBeVisible();
  await legible(phone, phoneStakes, "o que está encomendado (celular)");
  await capture(phone, testInfo, "gerente-celular-cancelar-o-que-esta-em-jogo");
  await phoneCancel.getByRole("button", { name: "Massa perdida" }).click();
  const phoneConfirm = phoneCancel.getByRole("button", {
    name: "Confirmar cancelamento",
  });
  await phoneConfirm.scrollIntoViewIfNeeded();
  await expect(phoneConfirm).toBeEnabled();
  await expect(phoneConfirm).toBeInViewport({ ratio: 1 });
  await capture(phone, testInfo, "gerente-celular-cancelar-com-motivo");
  await phoneConfirm.click();
  await expect(phoneCancel).toBeHidden();
  await expect(phone.getByText(`Lote cancelado: ${WITH_ORDERS}`)).toBeVisible();

  // Ela tira do plano de amanhã um lote sem encomenda: o zero também pede o motivo.
  await openPlanning(phone);
  await plannedItem(phone, FREE).click();
  await phone.getByRole("menuitem", { name: "Corrigir quantidade" }).click();
  const phoneDialog = phone.getByRole("dialog");
  await steady(phoneDialog);
  await phoneDialog
    .getByRole("textbox", { name: "Quantidade planejada" })
    .fill("0");
  const remove = phoneDialog.getByRole("button", { name: "Remover do plano" });
  await expect(remove).toBeDisabled();
  const free = phoneDialog.getByText(/Nenhuma encomenda depende dele\.$/);
  await expect(free).toBeVisible();
  await legible(phone, free, "o aviso sem encomenda");
  await phoneDialog.getByRole("button", { name: "Outro" }).click();
  await phoneDialog
    .getByRole("textbox", { name: /Motivo/ })
    .fill("Forno em manutenção amanhã");
  await expect(remove).toBeEnabled();
  await expect(remove).toBeInViewport({ ratio: 1 });
  await expect(
    phoneDialog.getByRole("button", { name: "Cancelar", exact: true }),
  ).toHaveCount(0);
  await capture(phone, testInfo, "gerente-celular-remover-do-plano");
  await remove.click();
  await expect(phoneDialog).toBeHidden();
  await expect(phone.getByText(`${FREE} saiu do plano.`)).toBeVisible();

  await phoneContext.close();
  await tabletContext.close();
});
