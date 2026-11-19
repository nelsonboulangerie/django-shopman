import { describe, expect, it } from "vitest";

import { POS_SHORTCUT_GROUPS } from "../app/presentation/shortcuts";

// O DICIONÁRIO É O CONTRATO: uma tecla que existe e não está listada aqui não
// existe para o operador. Estes testes prendem as duas teclas do checkout que
// mudaram de dono (F10 abre a divisão da conta, e o CPF na nota foi para o F). A
// ajuda que as mostra é a do kit (`OperatorShortcutsHelp`, V6-KIT).
describe("atalhos do PDV, o dicionário das teclas", () => {
  const teclas = (rotulo: string) =>
    POS_SHORTCUT_GROUPS.flatMap((group) => group.items).find((item) => item.label.includes(rotulo))?.keys;

  // Os três fatos do pedido seguem a ordem da barra, que é a do funil da
  // encomenda (dono, 19/11/2026, #2754): cliente, quando, recebimento. A tecla é
  // da POSIÇÃO, então F7 e F8 trocaram de dono.
  it("F6 é o cliente, F7 é o quando e F8 é o recebimento, nessa ordem", () => {
    expect(teclas("Cliente (")).toEqual(["F6"]);
    expect(teclas("Quando (")).toEqual(["F7"]);
    expect(teclas("Recebimento (")).toEqual(["F8"]);
    const facts = POS_SHORTCUT_GROUPS[0]!.items.map((item) => item.keys[0]).filter((key) => ["F6", "F7", "F8"].includes(key!));
    expect(facts).toEqual(["F6", "F7", "F8"]);
  });

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
