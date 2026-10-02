/**
 * O ASSISTENTE DA ENCOMENDA: etapas, ordem e prontidão.
 *
 * A regra de "o que falta" NÃO mora aqui. Ela tem dono: `orderSetupIssue`
 * (`usePosSale`), espelho de `validate_sales_mode` no servidor
 * (`shop/services/pos_sales_mode.py`). O issue é a PRIMEIRA pendência na ordem
 * cliente → recebimento → endereço → data; este módulo só traduz essa resposta
 * em etapas. Uma etapa está pronta quando o issue já passou dela. Nada aqui lê o
 * carrinho: se a regra mudar, o assistente acompanha sem ninguém lembrar dele.
 *
 * Por isso as invalidações chegam sozinhas. Tirar o cliente devolve o issue a
 * "customer"; trocar retirada por entrega sem endereço devolve "address"; apagar
 * o dia devolve "schedule". O assistente só precisa obedecer.
 */

export type OrderSetupIssue = "customer" | "fulfillment" | "address" | "schedule" | "";
export type OrderSetupStepKey = Exclude<OrderSetupIssue, "">;

/** A ordem da regra: a mesma em que `orderSetupIssue` pergunta. */
export const ORDER_SETUP_ORDER: readonly OrderSetupStepKey[] = ["customer", "fulfillment", "address", "schedule"];

export const ORDER_SETUP_STEP_LABELS: Record<OrderSetupStepKey, string> = {
  customer: "Cliente",
  fulfillment: "Recebimento",
  address: "Endereço",
  schedule: "Data e horário",
};

export interface OrderSetupStep {
  key: OrderSetupStepKey;
  label: string;
  ready: boolean;
}

/**
 * As etapas da vez. O endereço só existe na entrega: na retirada ele não é
 * etapa pulada, é etapa que não existe ("Etapa 3 de 3", não "de 4").
 */
export function orderSetupSteps(issue: OrderSetupIssue, delivery: boolean): OrderSetupStep[] {
  const issueIndex = issue ? ORDER_SETUP_ORDER.indexOf(issue) : ORDER_SETUP_ORDER.length;
  return ORDER_SETUP_ORDER
    .filter((key) => key !== "address" || delivery || issue === "address")
    .map((key) => ({ key, label: ORDER_SETUP_STEP_LABELS[key], ready: ORDER_SETUP_ORDER.indexOf(key) < issueIndex }));
}

/** Uma etapa só abre com todas as anteriores prontas (o molde do `CampaignForm`). */
export function orderSetupStepEnabled(steps: OrderSetupStep[], index: number): boolean {
  return index >= 0 && index < steps.length && steps.slice(0, index).every((step) => step.ready);
}

/** A etapa da vez: a primeira pendente, ou a última quando tudo está pronto. */
export function firstPendingStep(steps: OrderSetupStep[]): OrderSetupStepKey {
  return (steps.find((step) => !step.ready) ?? steps[steps.length - 1])!.key;
}

/**
 * Para onde o assistente vai quando a resposta da regra muda.
 *
 * - A etapa aberta ficou pronta (o operador escolheu no diálogo): segue para a
 *   próxima pendente. É o "assistente": ninguém precisa apertar Continuar
 *   depois de cada diálogo.
 * - A etapa aberta deixou de existir (entrega virou retirada) ou ficou fechada
 *   porque uma anterior voltou a pendente (o cliente saiu): volta à pendente.
 * - Fora isso, fica onde o operador está (ele pode estar revendo uma etapa feita).
 */
export function nextOrderSetupStep(input: {
  steps: OrderSetupStep[];
  current: OrderSetupStepKey;
  wasReady: boolean;
}): OrderSetupStepKey {
  const index = input.steps.findIndex((step) => step.key === input.current);
  if (index < 0 || !orderSetupStepEnabled(input.steps, index)) return firstPendingStep(input.steps);
  if (!input.wasReady && input.steps[index]!.ready) return firstPendingStep(input.steps);
  return input.current;
}
