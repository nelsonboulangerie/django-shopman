import { expect, test, type Locator } from "@playwright/test";

import {
  lockDevice,
  managerReleasesDevice,
  operatorUnlocksWithPin,
} from "./support/operator";
import { capture, cast, device, settled } from "./support/stack";

// J-P7 (docs/plans/EXCELENCIA-PRODUCAO-PLANO.md, seção 8; WP-F11): falta de insumo.
// A Cozinha confirma um previsto acima do que o estoque cobre e lê o que falta, na
// medida da bancada ("Falta 1240 g de massa ciabatta"): é aviso, e ela abre assim
// mesmo. Na Finalização a falta trava, e a saída é a assinatura da lista: a Gerente
// toca no próprio nome e digita o PIN (decisão 3 do dono, D-042). Sem texto livre.
//
// A falta nasce pelo gesto da Cozinha: a Focaccia do dia de hoje, que o seed planeja
// com 10, é confirmada com 70, e a massa de ciabatta do estoque do seed não cobre 70
// (medido em 26/11/2026: cobre até cerca de 66). A massa é feita na casa, então a tela
// não oferece o Compras. A jornada abre e fecha esse lote: roda uma vez por seed.
//
// Ficou para depois (#3661): a falta nascendo de um insumo comprado, com a entrada dada
// pela tela do Compras, que pede o Compras compilado na mesma pilha.
const PRODUCT = process.env.JP7_PRODUCT || "Focaccia do dia";
const OPEN_WITH = process.env.JP7_QUANTITY || "70";
const SHORT = /^Falta \d[\d.,]* (g|kg|ml|l|un) de .+/;

/** O diálogo terminou de entrar (a captura não pega o modal no meio da animação). */
async function steady(dialog: Locator) {
  await expect(dialog).toBeVisible();
  await dialog.evaluate((element) =>
    Promise.all(
      element
        .getAnimations({ subtree: true })
        .map((animation) => animation.finished.catch(() => undefined)),
    ),
  );
}

test("J-P7: falta de insumo, do aviso à assinatura", async ({
  browser,
  baseURL,
}, testInfo) => {
  const tabletContext = await device(browser, "tablet", baseURL!);
  const tablet = await tabletContext.newPage();
  await managerReleasesDevice(tablet);
  await lockDevice(tablet);
  await operatorUnlocksWithPin(tablet, cast.kitchen);

  // ── Abertura: o previsto acima do estoque é aviso, não trava ────────────────
  await tablet.goto("/");
  await settled(tablet);
  const open = tablet
    .getByRole("button", { name: `Confirmar ${PRODUCT}`, exact: true })
    .first();
  await expect(
    open,
    `o lote de hoje da ${PRODUCT} já não está a confirmar: a J-P7 roda uma vez por seed`,
  ).toBeVisible();
  await open.click();
  const panel = tablet.getByRole("complementary", {
    name: "Confirmar o previsto",
  });
  await expect(panel).toBeVisible();
  await panel.getByRole("button", { name: "Limpar quantidade prevista" }).click();
  for (const digit of OPEN_WITH) {
    await panel
      .getByRole("button", { name: `Dígito ${digit}`, exact: true })
      .click();
  }
  // Setenta é muitas vezes o planejado: a tela pede para conferir o número.
  const checked = panel.getByRole("button", { name: "O número está certo" });
  if (await checked.isVisible().catch(() => false)) await checked.click();
  await panel
    .getByRole("button", { name: new RegExp(`^Confirmar ${OPEN_WITH}`) })
    .click();

  const warning = tablet.getByRole("dialog");
  await steady(warning);
  await expect(warning.getByText("Falta insumo para este lote")).toBeVisible();
  const line = warning.locator("[data-shortage-item] span").first();
  await expect(line).toHaveText(SHORT);
  await expect(warning.getByRole("textbox")).toHaveCount(0);
  // A massa é feita na casa: pedir ao Compras levaria a um beco.
  await expect(warning.getByRole("link", { name: "Pedir no Compras" })).toHaveCount(0);
  await capture(tablet, testInfo, "abertura-falta-e-aviso");
  await warning.getByRole("button", { name: "Abrir assim mesmo" }).click();
  await expect(tablet.getByText(`Lote aberto: ${PRODUCT} × ${OPEN_WITH}`)).toBeVisible();
  await capture(tablet, testInfo, "abertura-lote-aberto");

  // ── Finalização: a falta trava, e a saída é a assinatura da lista ───────────
  await tablet.goto("/close");
  await settled(tablet);
  await tablet
    .getByRole("button", { name: `Finalizar o lote de ${PRODUCT}` })
    .first()
    .click();
  await expect(tablet.getByText(`Previsto: ${OPEN_WITH} un.`)).toBeVisible();
  await tablet
    .getByRole("button", { name: "Finalizar", exact: true })
    .locator("visible=true")
    .first()
    .click();
  const block = tablet.getByRole("dialog");
  await steady(block);
  await expect(block.getByText("Falta insumo para fechar")).toBeVisible();
  await expect(block.locator("[data-shortage-item] span").first()).toHaveText(SHORT);
  await expect(block.getByRole("textbox"), "o 'quem autorizou' em texto livre morreu").toHaveCount(0);
  await capture(tablet, testInfo, "finalizacao-falta-trava");
  await block.getByRole("button", { name: "Fechar com autorização" }).click();

  // O diálogo de autorização de sempre: o ato nomeado, quem continua, e a lista.
  const sign = tablet.getByRole("dialog", { name: "Autorizar fechar com falta" });
  await steady(sign);
  await expect(sign.getByText(SHORT)).toBeVisible();
  await expect(sign.getByText(`Você continua como ${cast.kitchen.name}.`)).toBeVisible();
  await capture(tablet, testInfo, "finalizacao-quem-autoriza");
  await sign.getByRole("button", { name: cast.manager.name, exact: true }).click();
  for (const digit of cast.manager.pin) {
    await sign.getByRole("button", { name: digit, exact: true }).click();
  }
  const done = sign.getByRole("button", { name: "Confirmar", exact: true });
  if (await done.isVisible().catch(() => false)) await done.click();
  await expect(sign).toBeHidden({ timeout: 30_000 });
  await expect(
    tablet.getByRole("button", { name: `Finalizar o lote de ${PRODUCT}` }),
  ).toHaveCount(0);
  await capture(tablet, testInfo, "finalizacao-lote-fechado-com-assinatura");
  await tabletContext.close();
});
