// SONDA: o crachá do gerente autoriza a venda no Pagamento (#2691).
//
// O diálogo "Autorizar a venda" (`PosPaymentWorkspace`, `OperatorManagerAuth`
// `action="sale_approval"`) convida a chamar um gerente com crachá, e o kit emite
// `authorize-badge` quando o leitor lê. A tela não escutava: o gerente passava o
// crachá, nada acontecia, e ele digitava o PIN.
//
// A Caixa (Fran) dá 50% de desconto numa venda em dinheiro, o Validar vira "Pedir
// autorização", e a Gerente (Joyce) passa o crachá dela no diálogo. O leitor é
// emulado como um leitor HID de verdade: as teclas do token, rápidas, e Enter. O
// crachá é o de dev que o `setup_operators` grava (`dev_badge`: sha256 da semente com
// a SECRET_KEY da pilha). A conferência vai a `/pos/manager-approval/check/` com
// `{badge}`, volta o carimbo, o diálogo fecha e a venda fecha. No celular (375 px) e
// no balcão (1366 px). Como rodar: README.md desta pasta (filtro `cracha`).
//
// A mesma sonda roda na base (antes) para registrar o crachá sem resposta: por isso a
// asserção do fechamento é `soft`.
import { createHash } from "node:crypto";

import { audits, still } from "./support/audit";
import { capture, cast, expect, settled, test, type Page } from "./support/operator";

/** O crachá de dev da Gerente, como o `setup_operators.dev_badge` o deriva. */
function managerBadge(): string {
  const secret = process.env.DJANGO_SECRET_KEY || "";
  if (!secret) throw new Error("DJANGO_SECRET_KEY da pilha ausente: o crachá de dev não se deriva sem ela.");
  return createHash("sha256").update(`shopman-dev-badge:${cast.manager.username}:${secret}`).digest("hex").slice(0, 12);
}

/** O leitor HID: as teclas do token, sem pausa, e Enter. */
async function swipesBadge(page: Page, badge: string) {
  await page.keyboard.type(badge, { delay: 0 });
  await page.keyboard.press("Enter");
}

/** Uma venda de balcão em dinheiro com 50% de desconto, até o "Pedir autorização". */
async function saleNeedsManager(page: Page) {
  await page.getByRole("button", { name: /Próxima livre/ }).first().click();
  await settled(page);
  const tile = page.locator("button[data-pos-product]").and(page.locator(":enabled")).locator("visible=true").first();
  await tile.click({ timeout: 30_000 });
  // No celular a comanda é a folha de baixo: abre para chegar ao Pagamento.
  const sheet = page.getByRole("button", { name: "Ver a comanda" }).locator("visible=true").first();
  if (await sheet.isVisible().catch(() => false)) await sheet.click();
  await page.getByRole("button", { name: /^Pagamento|^Outras formas|^Cobrar/ }).locator("visible=true").first().click();

  await page.getByRole("button", { name: /^Desconto/ }).locator("visible=true").first().click();
  const discount = page.getByRole("dialog", { name: "Desconto" });
  await expect(discount).toBeVisible({ timeout: 30_000 });
  await discount.getByRole("button", { name: "Percentual", exact: true }).click();
  const value = discount.getByPlaceholder("0");
  await value.click();
  await value.pressSequentially("50");
  const reason = discount.getByRole("button", { name: "Cortesia", exact: true });
  if (await reason.isVisible().catch(() => false)) await reason.click();
  await discount.getByRole("button", { name: "Voltar ao pagamento" }).click();
  await expect(discount).toBeHidden({ timeout: 30_000 });

  await page.getByRole("button", { name: /^Dinheiro/ }).and(page.locator(":enabled")).locator("visible=true").first().click();
  const ask = page.getByRole("button", { name: /^Pedir autorização/ }).and(page.locator(":enabled")).locator("visible=true").first();
  await expect(ask).toBeVisible({ timeout: 60_000 });
  return ask;
}

test.describe.configure({ mode: "serial" });

for (const device of ["phone", "counter"] as const) {
  test.describe(`Crachá autoriza a venda · ${device === "phone" ? "375 px" : "1366 px"}`, () => {
    test.use({ device });

    test("a Gerente passa o crachá no 'Autorizar a venda' e a venda fecha", async ({ cashierAtCounter: page }, testInfo) => {
      test.setTimeout(8 * 60_000);
      const badge = managerBadge();
      const checks: Array<{ status: number; via: string }> = [];
      page.on("response", async (response) => {
        if (!response.url().includes("/manager-approval/check/")) return;
        const body = (response.request().postDataJSON() ?? {}) as { manager_approval?: Record<string, unknown> };
        const approval = body.manager_approval ?? {};
        // O token não vai para o log: só por qual porta a conferência passou.
        checks.push({ status: response.status(), via: approval.badge ? "badge" : approval.pin ? "pin" : "nenhuma" });
      });

      const ask = await saleNeedsManager(page);
      await capture(page, testInfo, "pedir-autorizacao");
      await ask.click();
      const dialog = page.getByRole("dialog", { name: "Autorizar a venda" });
      await expect(dialog).toBeVisible({ timeout: 30_000 });
      await still(page);
      // O convite do crachá está na tela que o gerente lê.
      await audits(page, `dialogo ${device}`, '[role="dialog"] h2, [role="dialog"] [data-slot="description"], [role="dialog"] p');
      await capture(page, testInfo, "autorizar-a-venda");

      await swipesBadge(page, badge);
      // Na base o crachá não chegava a lugar nenhum: o diálogo ficava aberto, mudo.
      await expect.soft(dialog, "o crachá não autorizou a venda").toBeHidden({ timeout: 30_000 });
      await still(page);
      console.log(`AUDITORIA crachá ${device}: ${JSON.stringify({ checks, dialogOpen: await dialog.isVisible() })}`);
      if (await dialog.isVisible()) {
        await capture(page, testInfo, "cracha-sem-resposta");
        return;
      }
      expect(checks.filter((c) => c.via === "badge" && c.status === 200)).toHaveLength(1);
      expect(checks.filter((c) => c.via === "pin")).toHaveLength(0);
      await expect(page.getByRole("button", { name: /Nova venda/ }).locator("visible=true").first()).toBeVisible({ timeout: 60_000 });
      await still(page);
      await capture(page, testInfo, "venda-fechada-com-o-cracha");
    });
  });
}
