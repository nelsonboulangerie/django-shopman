// O TECLADO FÍSICO NA TELA DE PAGAMENTO — uma régua só para a venda (`pages/index.vue`)
// e para o saldo da encomenda (`PosPreorderBalancePayment`): a mesma tela, as
// mesmas teclas. Fora de campo de texto e sem modificador:
//   · dígito, vírgula (ou ponto) e Backspace editam a linha SELECIONADA;
//   · "=" é o Exato;
//   · uma letra lança a forma de pagamento correspondente (`methodShortcuts`);
// e quem chama decide o que cada uma faz.

export type PaymentKeyIntent =
  | { kind: "digit"; digit: string }
  | { kind: "comma" }
  | { kind: "backspace" }
  | { kind: "exact" }
  | { kind: "letter"; letter: string };

/**
 * A intenção de uma tecla na tela de Pagamento, ou `null` quando ela não é desta
 * tela. As teclas do valor só valem com uma linha selecionada: sem linha, o
 * teclado de valor não tem o que editar.
 */
export function paymentKeyIntent(
  event: Pick<KeyboardEvent, "key" | "metaKey" | "ctrlKey" | "altKey">,
  hasSelectedTender: boolean,
): PaymentKeyIntent | null {
  if (event.metaKey || event.ctrlKey || event.altKey) return null;
  const key = event.key;
  if (hasSelectedTender) {
    if (key >= "0" && key <= "9" && key.length === 1) return { kind: "digit", digit: key };
    if (key === "," || key === "." || key === "Decimal") return { kind: "comma" };
    if (key === "Backspace") return { kind: "backspace" };
    if (key === "=") return { kind: "exact" };
  }
  if (/^[a-zA-Z]$/.test(key)) return { kind: "letter", letter: key.toUpperCase() };
  return null;
}
