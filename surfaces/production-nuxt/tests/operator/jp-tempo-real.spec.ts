import { execSync } from "node:child_process";

import { expect, test, type Page } from "@playwright/test";

import {
  lockDevice,
  managerReleasesDevice,
  operatorUnlocksWithPin,
} from "./support/operator";
import { capture, cast, device, settled } from "./support/stack";

// WP-F15 (#3364): tempo real honesto. Dois tablets da bancada: a Cozinha confirma o
// previsto de um lote no tablet A (a grade), e o cartão do lote na Finalização do tablet
// B passa de "a confirmar" para "em produção desde …" em menos de 3 s, sem recarregar (o canal `backstage-production` refaz o GET canônico).
// O selo do tablet B diz "Ao vivo" só enquanto o canal está aberto.
//
// Com `OPERATOR_DJANGO_STOP` e `OPERATOR_DJANGO_START` (comandos de shell que param e
// sobem o Django da pilha), a jornada também para o Django: o selo deixa de dizer "Ao
// vivo", o dado velho vira o aviso do cabeçalho com "Tentar de novo", e a Qualidade e a
// Finalização abertas pelo menu sem leitura boa mostram o erro com "Tentar de novo" em
// vez da tela em branco. (Recarregar a página inteira com o Django parado cai antes, na
// tela de acesso do kit, que tem o próprio "Tentar de novo".) Sem eles,
// essa parte fica de fora (e a jornada diz isso).
//
// Abre um lote planejado de hoje, então roda uma vez por lote a confirmar no seed.
const LIVE_BUDGET_MS = 3_000;

function liveSeal(page: Page) {
  return page.locator("[data-live-seal]").first();
}

test("Tempo real: o lote confirmado num tablet aparece na Finalização do outro", async ({
  browser,
  baseURL,
}, testInfo) => {
  // ── Dois tablets da bancada, a Cozinha com PIN nos dois ──────────────────────
  const contextA = await device(browser, "tablet", baseURL!);
  const tabletA = await contextA.newPage();
  await managerReleasesDevice(tabletA);
  await lockDevice(tabletA);
  await operatorUnlocksWithPin(tabletA, cast.kitchen);

  const contextB = await device(browser, "tablet", baseURL!);
  const tabletB = await contextB.newPage();
  await managerReleasesDevice(tabletB);
  await lockDevice(tabletB);
  await operatorUnlocksWithPin(tabletB, cast.kitchen);

  // B fica na Finalização; o selo diz "Ao vivo" quando o canal abre.
  await tabletB.goto("/close");
  await settled(tabletB);
  await expect(liveSeal(tabletB)).toHaveAttribute("data-live-seal", "live");
  await capture(tabletB, testInfo, "tablet-b-finalizacao-ao-vivo");

  // A abre a grade e escolhe o primeiro lote de hoje a confirmar.
  await tabletA.goto("/");
  await settled(tabletA);
  const open = tabletA.getByRole("button", { name: /^Confirmar \D/ }).first();
  await expect(open, "nenhum lote de hoje a confirmar: rode o seed de novo").toBeVisible();
  const product = ((await open.getAttribute("aria-label")) ?? (await open.innerText()))
    .replace(/^Confirmar /, "")
    .trim();
  // A Finalização lista o lote planejado como "a confirmar".
  const cardLine = tabletB
    .locator("[data-close-card]")
    .filter({ has: tabletB.getByRole("button", { name: `Finalizar o lote de ${product}` }) })
    .first()
    .locator("[data-close-card-line]");
  await expect(cardLine).toContainText("a confirmar");
  await open.click();
  const panel = tabletA.getByRole("complementary", { name: "Confirmar o previsto" });
  await expect(panel).toBeVisible();
  await capture(tabletA, testInfo, "tablet-a-cozinha-confirma-o-previsto");

  // O relógio corre do toque em Confirmar até o lote aparecer no tablet B.
  const started = Date.now();
  await panel.getByRole("button", { name: /^Confirmar \d/ }).click();
  await expect(cardLine).toContainText(/em produção desde/, { timeout: 10_000 });
  const elapsed = Date.now() - started;
  testInfo.annotations.push({
    type: "tempo-real",
    description: `${product}: apareceu no tablet B em ${elapsed} ms`,
  });
  console.log(`[F15] ${product}: apareceu no tablet B em ${elapsed} ms`);
  await capture(tabletB, testInfo, "tablet-b-lote-apareceu-sem-recarregar");
  expect(elapsed, `o lote levou ${elapsed} ms para aparecer`).toBeLessThan(LIVE_BUDGET_MS);
  await expect(liveSeal(tabletB)).toHaveAttribute("data-live-seal", "live");

  // ── O canal caído com o Django de pé: o selo diz a cadência, nunca "Ao vivo" ──
  await tabletB.route("**/sse/**", (route) => route.abort());
  await tabletB.reload();
  await settled(tabletB);
  await expect(liveSeal(tabletB)).toHaveAttribute("data-live-seal", "calm", { timeout: 30_000 });
  await expect(liveSeal(tabletB)).not.toContainText("Ao vivo");
  await capture(tabletB, testInfo, "tablet-b-canal-caido-a-cada-30-s");
  await tabletB.unroute("**/sse/**");
  await tabletB.reload();
  await settled(tabletB);
  await expect(liveSeal(tabletB)).toHaveAttribute("data-live-seal", "live");

  // ── Django parado ──────────────────────────────────────────────────────────
  const stop = process.env.OPERATOR_DJANGO_STOP;
  const start = process.env.OPERATOR_DJANGO_START;
  if (!stop || !start) {
    testInfo.annotations.push({
      type: "fora",
      description: "Django parado: defina OPERATOR_DJANGO_STOP e OPERATOR_DJANGO_START",
    });
    await contextB.close();
    await contextA.close();
    return;
  }
  execSync(stop, { stdio: "inherit" });
  try {
    // O canal cai: o selo deixa de dizer "Ao vivo" e diz a cadência da reserva.
    await expect(liveSeal(tabletB)).not.toHaveAttribute("data-live-seal", "live", {
      timeout: 30_000,
    });

    // A releitura falha com o painel na tela: o dado velho vira o aviso do cabeçalho.
    await tabletB.keyboard.press("r");
    await expect(liveSeal(tabletB)).toHaveAttribute("data-live-seal", "late");
    const staleAlert = tabletB.getByText(/^Sem atualizar: a tela mostra os lotes/);
    await expect(staleAlert).toBeVisible();
    await expect(tabletB.getByRole("button", { name: "Tentar de novo" }).first()).toBeVisible();
    await capture(tabletB, testInfo, "tablet-b-django-parado-aviso-dado-velho");

    // Sem nenhuma leitura boa, a tela diz o erro com "Tentar de novo", em vez de ficar em
    // branco: a Qualidade e a Finalização abertas pelo menu, com o Django parado.
    await tabletB.getByRole("link", { name: "Qualidade", exact: true }).first().click();
    await expect(tabletB.locator("[data-quality-error]")).toBeVisible();
    await expect(liveSeal(tabletB)).toHaveAttribute("data-live-seal", "off");
    await capture(tabletB, testInfo, "tablet-b-qualidade-sem-leitura-django-parado");
    await tabletB.getByRole("link", { name: "Finalização", exact: true }).first().click();
    await expect(tabletB.locator("[data-close-error]")).toBeVisible();
    await expect(tabletB.getByRole("button", { name: "Tentar de novo" }).first()).toBeVisible();
    await expect(liveSeal(tabletB)).toHaveAttribute("data-live-seal", "off");
    await capture(tabletB, testInfo, "tablet-b-finalizacao-sem-leitura-django-parado");
  } finally {
    execSync(start, { stdio: "inherit" });
  }

  // O Django volta: "Tentar de novo" relê, e o canal reabre sozinho.
  await expect
    .poll(
      async () => {
        await tabletB.getByRole("button", { name: "Tentar de novo" }).first().click().catch(() => {});
        return liveSeal(tabletB).getAttribute("data-live-seal");
      },
      { timeout: 90_000, intervals: [2_000] },
    )
    .toBe("live");
  await expect(tabletB.getByText(/^Sem atualizar: a tela mostra os lotes/)).toHaveCount(0);
  await capture(tabletB, testInfo, "tablet-b-django-de-volta-ao-vivo");

  await contextB.close();
  await contextA.close();
});
