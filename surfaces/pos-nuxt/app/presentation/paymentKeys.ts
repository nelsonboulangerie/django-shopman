// O TECLADO FÍSICO NO SALDO DA ENCOMENDA (`PosPreorderBalancePayment`), pelo mapa
// canônico de atalhos do kit (`useOperatorShortcutMap`): as mesmas teclas da tela de
// Pagamento da venda, porque é a mesma tela.
//   · dígito, vírgula (ou ponto) e Backspace editam a linha SELECIONADA;
//   · "=" é o Exato;
//   · uma letra lança a forma de pagamento correspondente (`methodShortcuts`);
//   · Enter recebe e entrega, com o saldo coberto; F10 divide a conta; Esc volta.
// Com diálogo aberto ou foco num campo, nenhuma age (regra do mapa do kit).

import type { OperatorShortcutCombination, OperatorShortcutCommand } from "../../../operator-kit/app/types/operatorShortcut";
import { defineOperatorShortcutMap } from "../../../operator-kit/app/utils/operatorShortcuts";

/** Os contextos que a tela liga: há linha selecionada; o saldo está coberto. */
export type BalancePaymentContext = "tender-selected" | "covered";

const OWNER = "PosPreorderBalancePayment";
const DIGITS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"] as const;
const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");

function command(
  id: string,
  label: string,
  combinations: OperatorShortcutCombination[],
  alternative: string,
  enabledContexts: BalancePaymentContext[] = [],
  extra: Partial<OperatorShortcutCommand<BalancePaymentContext>> = {},
): OperatorShortcutCommand<BalancePaymentContext> {
  return { id, label, combinations, scope: "screen", owner: OWNER, enabledContexts, forbiddenContexts: [], alternative, ...extra };
}

export const BALANCE_PAYMENT_SHORTCUTS = defineOperatorShortcutMap([
  ...DIGITS.map((digit) => command(
    `balance.digit.${digit}`,
    `Dígito ${digit}`,
    [{ code: `Digit${digit}` }, { code: `Numpad${digit}` }],
    `Tecla ${digit} do teclado de valor`,
    ["tender-selected"],
    { allowRepeat: true },
  )),
  command("balance.comma", "Vírgula (centavos)", [{ code: "Comma" }, { code: "Period" }, { code: "NumpadDecimal" }, { code: "NumpadComma" }], "Tecla , do teclado de valor", ["tender-selected"]),
  command("balance.backspace", "Apagar um dígito", [{ code: "Backspace" }], "Tecla de apagar do teclado de valor", ["tender-selected"], { allowRepeat: true }),
  command("balance.exact", "Exato", [{ code: "Equal" }], "Botão Exato", ["tender-selected"]),
  ...LETTERS.map((letter) => command(
    `balance.method.${letter}`,
    `Forma de pagamento ${letter}`,
    [{ code: `Key${letter}` }],
    "Botões das formas de pagamento",
  )),
  command("balance.receive", "Receber e entregar", [{ code: "Enter" }, { code: "NumpadEnter" }], "Botão Receber e entregar", ["covered"]),
  command("balance.split", "Dividir conta", [{ code: "F10" }], "Botão Dividir conta"),
  command("balance.back", "Voltar à encomenda", [{ code: "Escape" }], "Botão Voltar à encomenda"),
] as const);

