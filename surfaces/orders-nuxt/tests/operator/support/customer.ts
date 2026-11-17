import { expect, type Page, type TestInfo } from "@playwright/test";
import { capture, djangoLogMark, readLoginCode, settled } from "./stack";

// O cliente na loja, pelo celular: cardápio, sacola, entrar com o código que chegou,
// finalizar e pagar. Os passos são os da pessoa; o único "atalho" é ler o código no
// log do Django, que é onde a pilha entrega o SMS.

export interface PickupOrder {
  product: string;
  phone: string;
  name: string;
}

/** Cliente novo pede retirada para hoje e paga com Pix (pagamento simulado da pilha).
 *  Devolve o código do pedido, como a loja mostra no acompanhamento. */
export async function customerOrdersPickupToday(page: Page, testInfo: TestInfo, order: PickupOrder): Promise<string> {
  await page.goto("/menu");
  await settled(page);
  await expect(page.getByText(/^Aberto/).first(), "a loja da pilha precisa estar aberta agora (README: expediente)").toBeVisible();
  await page.getByRole("button", { name: `Adicionar ${order.product}`, exact: true }).first().click();
  await expect(page.getByRole("link", { name: /^Sacola, 1 item/ })).toBeVisible();
  await capture(page, testInfo, "loja-cardapio");

  await page.getByRole("link", { name: /^Sacola, 1 item/ }).click();
  await expect(page.getByRole("heading", { name: "Sua sacola" })).toBeVisible();
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
  await page.getByRole("radio", { name: /^Retirada/ }).click();
  await page.getByRole("button", { name: "Continuar", exact: true }).click();
  await expect(page.getByText("Horário da retirada")).toBeVisible();
  await page.getByRole("radio", { name: /^Hoje/ }).click().catch(() => undefined);
  await page.getByRole("radio", { name: /^\d{2}:\d{2} às \d{2}:\d{2}$/ }).first().click();
  await page.getByRole("button", { name: "Continuar", exact: true }).click();
  await page.getByRole("radio", { name: /^Pix/ }).click();
  await capture(page, testInfo, "loja-finalizar");
  await page.getByRole("button", { name: "Revisar pedido" }).click();
  await expect(page.getByText(/Retirada · Hoje/).last()).toBeVisible();
  await capture(page, testInfo, "loja-revisar");
  await page.getByRole("button", { name: "Enviar pedido" }).click();

  // Acompanhamento: paga com o Pix simulado da pilha.
  await expect(page).toHaveURL(/\/pedido\/[^/]+$/, { timeout: 60_000 });
  const ref = decodeURIComponent(new URL(page.url()).pathname.split("/").pop()!);
  await settled(page);
  await page.getByRole("button", { name: "Simular pagamento" }).click();
  await expect(page.getByText("Pagamento recebido")).toBeVisible({ timeout: 60_000 });
  await capture(page, testInfo, "loja-pago");
  return ref;
}
