import { describe, expect, it } from "vitest";

import { POS_SHORTCUT_GROUPS } from "../app/presentation/shortcuts";

// O DICIONÁRIO É O CONTRATO: uma tecla que existe e não está listada aqui não
// existe para o operador. Estes testes prendem as duas teclas do checkout que
// mudaram de dono (F10 abre a divisão da conta, e o CPF na nota foi para o F). A
// ajuda que as mostra é a do kit (`OperatorShortcutsHelp`, V6-KIT).
describe("atalhos do PDV, o dicionário das teclas", () => {
  const teclas = (rotulo: string) =>
    POS_SHORTCUT_GROUPS.flatMap((group) => group.items).find((item) => item.label.includes(rotulo))?.keys;

  it("no pagamento, F10 é dividir a conta", () => {
    expect(teclas("Dividir a conta")).toEqual(["F10"]);
  });

  it("no pagamento, o CPF na nota é a letra F", () => {
    expect(teclas("CPF na nota (liga/desliga)")).toEqual(["F"]);
  });

  it("na comanda, o F10 continua sendo transferir itens", () => {
    // As duas telas nunca coexistem: o mesmo par de teclas significa "as duas
    // ações daqui", e a comanda não mudou.
    expect(teclas("Transferir itens para outra comanda")).toEqual(["F10"]);
  });
});
