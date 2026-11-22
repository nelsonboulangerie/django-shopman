import { expect, type Page, type TestInfo } from "@playwright/test";
import { capture, djangoLogMark, readLoginCode, settled } from "./stack";

// O cliente na loja, pelo celular: cardápio, sacola, entrar com o código que chegou,
// finalizar e pagar. Os passos são os da pessoa; o único "atalho" é ler o código no
// log do Django, que é onde a pilha entrega o SMS.

export interface PickupOrder {
  product: string;
  phone: string;
  name: string;
  /** O dia da retirada como a loja o oferece ("Hoje", "Amanhã"); padrão: hoje. */
  day?: "Hoje" | "Amanhã";
  /** A janela como a loja a escreve: meia hora hoje ("17h às 17h30"), turno na encomenda
   *  ("A partir das 15h"); padrão: a primeira livre. */
  window?: string;
  /** CPF ou CNPJ na nota (o "CPF na nota?" da retirada, no passo do pagamento). */
  taxId?: string;
  /** `false`: a cliente envia o pedido e não paga o Pix (fica no acompanhamento). */
  pays?: boolean;
}

/** Cliente novo pede retirada (hoje, ou amanhã: a encomenda) e paga com Pix (pagamento
 *  simulado da pilha). Devolve o código do pedido, como a loja mostra no acompanhamento. */
export async function customerOrdersPickupToday(page: Page, testInfo: TestInfo, order: PickupOrder): Promise<string> {
  await customerReachesCheckout(page, testInfo, order);

  await page.getByRole("radio", { name: /^Retirada/ }).click();
  await page.getByRole("button", { name: "Continuar", exact: true }).click();
  await expect(page.getByText("Horário da retirada")).toBeVisible();
  const day = order.day ?? "Hoje";
  if (day === "Hoje") await page.getByRole("radio", { name: /^Hoje/ }).click().catch(() => undefined);
  else await page.getByRole("radio", { name: new RegExp(`^${day}`) }).click();
  // A janela pedida, ou o primeiro horário livre do dia, no formato da casa ("10h às 10h30").
  if (order.window) {
    // Trocar o dia relê os horários: a janela clicada antes disso some com a lista velha.
    await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
    const window = page.getByRole("radio", { name: order.window, exact: true });
    await window.click();
    await expect(window).toBeChecked();
    await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
    await expect(window, `a janela ${order.window} continua escolhida`).toBeChecked();
  } else await page.getByRole("radio", { name: /^\d{1,2}h(\d{2})? às \d{1,2}h(\d{2})?$/ }).first().click();
  await page.getByRole("button", { name: "Continuar", exact: true }).click();
  await page.getByRole("radio", { name: /^Pix/ }).click();
  if (order.taxId) {
    await page.getByRole("switch", { name: /CPF ou CNPJ na nota\?/ }).click();
    const taxId = page.getByRole("textbox", { name: "CPF ou CNPJ na nota", exact: true });
    await taxId.click();
    await taxId.pressSequentially(order.taxId);
    // Com o campo em foco o teclado do celular está aberto e o card do total recolhe:
    // a cliente fecha o teclado antes de revisar.
    await taxId.blur();
  }
  await capture(page, testInfo, "loja-finalizar");
  await page.getByRole("button", { name: "Revisar pedido" }).click();
  await expect(page.getByText(new RegExp(`Retirada · ${day}`)).last()).toBeVisible();
  if (order.window) await expect(page.getByText(order.window).last()).toBeVisible();
  await capture(page, testInfo, "loja-revisar");
  return customerSendsAndPaysPix(page, testInfo, order.pays ?? true);
}

/** Cardápio → sacola → entrar com o código → nome: a cliente nova chega ao Finalizar. */
async function customerReachesCheckout(
  page: Page,
  testInfo: TestInfo,
  order: { product: string; phone: string; name: string; quantity?: number },
): Promise<void> {
  await page.goto("/menu");
  await settled(page);
  await expect(page.getByText(/^Aberto/).first(), "a loja da pilha precisa estar aberta agora (README: expediente)").toBeVisible();
  await page.getByRole("button", { name: `Adicionar ${order.product}`, exact: true }).first().click();
  // A sacola tem dois caminhos no celular: o ícone do topo e a aba da barra de baixo.
  const bag = page.getByRole("link", { name: /^Sacola, 1 item/ }).first();
  await expect(bag).toBeVisible();
  await capture(page, testInfo, "loja-cardapio");

  await bag.click();
  await expect(page.getByRole("heading", { name: "Sua sacola" })).toBeVisible();
  const quantity = order.quantity ?? 1;
  if (quantity > 1) {
    const stepper = page.getByRole("group", { name: `Quantidade de ${order.product}` });
    for (let n = 2; n <= quantity; n++) {
      await stepper.getByRole("button", { name: /Adicionar|Aumentar|Mais/i }).first().click();
      await expect(stepper).toContainText(String(n));
    }
  }
  await page.getByRole("link", { name: "Finalizar pedido" }).last().click();

  // Entrar: código por SMS, que nesta pilha cai no log do Django.
  await expect(page).toHaveURL(/\/entrar/);
  await settled(page);
  await page.getByRole("button", { name: "Prefere receber um código por SMS?" }).click();
  const phone = page.getByRole("textbox", { name: "Telefone", exact: true });
  await phone.click();
  await phone.pressSequentially(order.phone);
  const mark = djangoLogMark();
  await page.getByRole("button", { name: "Receber por SMS" }).click();
  const code = await readLoginCode(mark);
  await page.getByRole("textbox", { name: "Dígito 1 de 6" }).click();
  await page.keyboard.type(code);
  await capture(page, testInfo, "loja-codigo");

  // Cliente novo: a loja pergunta como chamar.
  const name = page.getByRole("textbox", { name: "Nome", exact: true });
  await expect(name).toBeVisible();
  await name.pressSequentially(order.name);
  await page.getByRole("button", { name: "Continuar", exact: true }).click();

  // Finalizar, uma etapa por vez.
  await expect(page).toHaveURL(/\/finalizar/);
  await settled(page);
}

/** Revisado: envia e paga com o Pix simulado da pilha (ou não paga, com `pays` falso).
 *  Devolve o código do pedido. */
async function customerSendsAndPaysPix(page: Page, testInfo: TestInfo, pays = true): Promise<string> {
  await page.getByRole("button", { name: "Enviar pedido" }).click();
  await expect(page).toHaveURL(/\/pedido\/[^/]+$/, { timeout: 60_000 });
  const ref = decodeURIComponent(new URL(page.url()).pathname.split("/").pop()!);
  await settled(page);
  if (!pays) {
    await expect(page.getByRole("button", { name: "Simular pagamento" })).toBeVisible({ timeout: 60_000 });
    await capture(page, testInfo, "loja-pix-sem-pagar");
    return ref;
  }
  await page.getByRole("button", { name: "Simular pagamento" }).click();
  await expect(page.getByText("Pagamento recebido")).toBeVisible({ timeout: 60_000 });
  await capture(page, testInfo, "loja-pago");
  return ref;
}

export interface DeliveryOrder {
  product: string;
  /** Quantas unidades: a entrega tem pedido mínimo. */
  quantity: number;
  phone: string;
  name: string;
  /** O endereço como a cliente digita (o caminho manual: a pilha não tem Google). */
  address: { route: string; number: string; neighborhood: string; cep: string; city: string; state: string };
}

/** Cliente nova pede entrega para hoje, SEM CPF na nota, e paga com o Pix simulado. */
export async function customerOrdersDeliveryToday(page: Page, testInfo: TestInfo, order: DeliveryOrder): Promise<string> {
  await customerReachesCheckout(page, testInfo, order);
  await page.getByRole("radio", { name: /^Entrega/ }).click();
  await expect(page.locator("[data-checkout-delivery-minimum]")).toHaveCount(0);

  const step = page.locator("[data-checkout-step='address']");
  await expect(step.locator("[data-address-picker]")).toBeVisible();
  const fresh = step.locator("[data-address-new]");
  if (await fresh.first().isVisible().catch(() => false)) await fresh.first().click();
  await step.locator("[data-address-manual]").click();
  await step.locator("#address-route").fill(order.address.route);
  await step.locator("#address-number").fill(order.address.number);
  await step.locator("#address-neighborhood").fill(order.address.neighborhood);
  await step.locator("#address-cep").fill(order.address.cep);
  const city = step.locator("#address-city");
  if (!(await city.inputValue()).trim()) await city.fill(order.address.city);
  const state = step.locator("#address-state");
  if (!(await state.innerText()).trim()) {
    await state.click();
    await page.getByRole("option", { name: order.address.state, exact: true }).click();
  }
  await step.locator("[data-address-confirm]").click();

  // O CPF da entrega mora no passo do endereço, e é opcional: esta cliente não informa.
  await expect(page.locator("#checkout-tax-id")).toHaveValue("");
  const when = page.locator("[data-checkout-step='when']");
  const window = when.locator("[data-checkout-delivery-windows] [role='radio']:not([data-disabled]):not([disabled])").first();
  await expect(window).toBeVisible({ timeout: 30_000 });
  await window.click();
  await expect(window).toHaveAttribute("aria-checked", "true");
  await page.getByRole("button", { name: "Continuar", exact: true }).click();
  await page.getByRole("radio", { name: /^Pix/ }).click();
  await capture(page, testInfo, "loja-finalizar");
  await page.getByRole("button", { name: "Revisar pedido" }).click();
  await expect(page.getByText(/Entrega · Hoje/).last()).toBeVisible();
  await capture(page, testInfo, "loja-revisar");
  return customerSendsAndPaysPix(page, testInfo);
}

/** No acompanhamento, antes do preparo: a cliente cancela sozinha e confirma. */
export async function customerCancelsOwnOrder(page: Page, testInfo: TestInfo): Promise<void> {
  await page.getByRole("button", { name: "Cancelar pedido", exact: true }).click();
  const dialog = page.getByRole("alertdialog", { name: "Cancelar pedido?" });
  await expect(dialog).toBeVisible();
  await capture(page, testInfo, "loja-cancelar");
  await dialog.getByRole("button", { name: "Sim, cancelar", exact: true }).click();
  await expect(page.getByText("Cancelado", { exact: true }).first()).toBeVisible({ timeout: 60_000 });
  await capture(page, testInfo, "loja-cancelado");
}
