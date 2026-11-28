// JORNADA J-P5 — pedido à Produção (EXCELENCIA-PRODUCAO WP-F13, D-041 item 2, D-042 item 2).
//
// A Caixa (Fran) abre no PDV uma encomenda de 30 croissants para uma data que o seed
// ainda não planejou (daqui a doze dias: a J5 usa os dez, e as duas não se somam). A
// encomenda fecha sem gerente, como pedido à Produção. Data futura sem lote ainda não é
// "Promessa em risco" (`order_promise._gap_cause`: é assim que toda encomenda feita com
// antecedência nasce); o lugar dela é o Planejamento. A Cozinha (Diofer), com o PIN dela,
// abre o Planejamento daquela data e lê a encomenda no chip da linha do Croissant ("30 un.
// · <dia> <hora>"), cuja sugestão já a conta: a faixa do topo não aparece para ela
// (decisão da coordenação, 28/11: a faixa é só para o que nenhuma linha cobre; repetir a
// linha era nota de rodapé, e um segundo "Planejar" com outro número, armadilha). Ela
// planeja a sugestão pela linha, e o chip segue no planejado. De volta ao PDV, a
// encomenda segue sem
// risco, agora com o plano da data cobrindo a reserva (a régua do aviso é a mesma do
// Gestor, `order_promise`; a reserva se ancora no lote quando ele fecha, no Stockman).
//
// A Produção não tem botão de recusar: se a casa não vai produzir, a encomenda segue em
// "Promessa em risco" e quem fala com o cliente é o Gestor (D-042, item 2).
//
// Pede a Produção compilada na pilha (`PDV_LIVE_PRODUCTION_URL`) e pula sem ela. Planeja o
// croissant daquela data, então roda uma vez por seed. Como rodar: README.md desta pasta.
import { capture, cast, expect, lockDevice, newDevice, settled, test } from "./support/operator";
import { daysAhead, identifiesCustomer, opensOrder, ordersQuantity, schedulesPickupOn } from "./support/order";
import {
  managerReleasesProductionDevice,
  opensPlanning,
  productionUrl,
  unlocksProductionWithPin,
} from "./support/production";

const PRODUCT = "Croissant";
const QTY = "30";
/** O chip da linha: "30 un. · <dia> 9h"; mais, se outra passada no mesmo banco já
 *  encomendou para a data (a jornada lê o número). */
const CHIP = /^(\d+) un\. · /;
/** A data: daqui a doze dias (`JP5_DAYS_AHEAD` escolhe outra num banco já usado). */
const DAYS_AHEAD = Number(process.env.JP5_DAYS_AHEAD || 12);
const CUSTOMER = { name: "Ana Ferreira", phone: "43995555555" };

test.describe.configure({ mode: "serial" });
test.use({ device: "counter" });

test("J-P5: a encomenda de data sem lote vira pedido à Produção, e planejar cobre a reserva", async ({ browser, cashierAtCounter: pos }, testInfo) => {
  test.skip(!productionUrl, "a J-P5 pede a Produção na pilha (PDV_LIVE_PRODUCTION_URL)");
  test.setTimeout(10 * 60_000);
  const target = daysAhead(DAYS_AHEAD);

  // 1 · A Caixa monta a encomenda no PDV: 30 croissants para a data sem lote.
  await opensOrder(pos);
  await identifiesCustomer(pos, CUSTOMER);
  await schedulesPickupOn(pos, target);
  await ordersQuantity(pos, PRODUCT, QTY);
  await expect(pos.locator('[data-pos-line-plan="unplanned"]').locator("visible=true").first())
    .toHaveText(`Ainda sem lote planejado para ${target.day}: vira pedido à Produção`, { timeout: 30_000 });
  await pos.getByRole("button", { name: /^Pagamento|^Outras formas/ }).locator("visible=true").first().click();
  await pos.getByRole("button", { name: /^Dinheiro/ }).and(pos.locator(":enabled")).locator("visible=true").first().click();
  const closed = pos.waitForResponse((r) => r.url().includes("/pos/sale/close/") && r.request().method() === "POST", { timeout: 90_000 });
  await pos.getByRole("button", { name: /^Validar/ }).and(pos.locator(":enabled")).locator("visible=true").first().click({ timeout: 30_000 });
  const ref = String(((await (await closed).json()) as { order_ref?: string }).order_ref || "");
  expect(ref, "o fechamento devolve o número da encomenda").not.toBe("");
  await capture(pos, testInfo, "pdv-encomenda-registrada");

  // 2 · O detalhe da encomenda: data futura ainda sem lote não é risco (é assim que toda
  //     encomenda feita com antecedência nasce, `order_promise._gap_cause`); o lugar do
  //     pedido é o Planejamento daquela data.
  await pos.goto(`/preorders/${encodeURIComponent(ref)}`);
  await settled(pos);
  await expect(pos.getByRole("heading", { name: `Encomenda ${ref}` }).locator("visible=true").first()).toBeVisible({ timeout: 60_000 });
  await expect(pos.getByText("Promessa em risco").locator("visible=true")).toHaveCount(0);
  await capture(pos, testInfo, "pdv-encomenda-sem-lote");

  // 3 · A Cozinha abre o Planejamento da data e lê o pedido à Produção, no tablet e no celular.
  const kitchenContext = await newDevice(browser, "phone", productionUrl);
  const phone = await kitchenContext.newPage();
  await managerReleasesProductionDevice(phone);
  await lockDevice(phone);
  await unlocksProductionWithPin(phone, cast.kitchen);
  await opensPlanning(phone, target.iso);
  const phoneLine = phone.locator('[data-plan-row][data-sku="CRO"]');
  const phoneChip = phoneLine.locator("[data-commitment-chip]");
  await expect(phoneChip).toHaveText(CHIP, { timeout: 60_000 });
  const ordered = Number(CHIP.exec((await phoneChip.innerText()).trim())![1]);
  expect(ordered, "o chip conta a encomenda desta passada").toBeGreaterThanOrEqual(Number(QTY));
  // Coberta pela linha, a encomenda não vai para a faixa: um "Planejar" só por produto.
  await expect(phone.locator('[data-plan-promised-item][data-sku="CRO"]')).toHaveCount(0);
  await capture(phone, testInfo, "producao-375-pedido-a-producao");

  const tabletContext = await browser.newContext({
    viewport: { width: 1024, height: 768 },
    hasTouch: true,
    baseURL: productionUrl,
    locale: "pt-BR",
    timezoneId: "America/Sao_Paulo",
  });
  const tablet = await tabletContext.newPage();
  await managerReleasesProductionDevice(tablet);
  await lockDevice(tablet);
  await unlocksProductionWithPin(tablet, cast.kitchen);
  await opensPlanning(tablet, target.iso);
  const line = tablet.locator('[data-plan-row][data-sku="CRO"]');
  await expect(line.locator("[data-commitment-chip]")).toHaveText(new RegExp(`^${ordered} un\\. · `), { timeout: 60_000 });
  await expect(tablet.locator('[data-plan-promised-item][data-sku="CRO"]')).toHaveCount(0);
  await expect(tablet.getByText(/recusar/i)).toHaveCount(0);
  await capture(tablet, testInfo, "producao-1024-pedido-a-producao");

  // 4 · Planeja a sugestão pela linha, que já conta as encomendas; o chip segue no planejado.
  const planned = tablet.waitForResponse((r) => /\/production\/.*plan/.test(r.url()) && r.request().method() === "POST", { timeout: 60_000 });
  await line.getByRole("button", { name: /^Planejar \d/ }).click();
  expect((await planned).ok(), "o plano foi aceito").toBe(true);
  await expect(line).toBeHidden({ timeout: 60_000 });
  await capture(tablet, testInfo, "producao-1024-planejado");

  // 5 · De volta ao PDV: o plano da data cobre a reserva, e a promessa já não está em risco.
  await expect(async () => {
    await pos.reload();
    await settled(pos);
    await expect(pos.getByRole("heading", { name: `Encomenda ${ref}` }).locator("visible=true").first()).toBeVisible({ timeout: 10_000 });
    await expect(pos.getByText("Promessa em risco").locator("visible=true")).toHaveCount(0, { timeout: 5_000 });
  }).toPass({ timeout: 90_000 });
  await capture(pos, testInfo, "pdv-promessa-coberta");

  await kitchenContext.close();
  await tabletContext.close();
});
