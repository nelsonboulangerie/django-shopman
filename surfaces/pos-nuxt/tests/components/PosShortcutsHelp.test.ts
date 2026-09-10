import { describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosShortcutsHelp from "~/components/PosShortcutsHelp.vue";

// O DICIONÁRIO É O CONTRATO: uma tecla que existe e não está listada aqui não
// existe para o operador. Estes testes prendem as duas teclas do checkout que
// mudaram de dono — F10 abre a divisão da conta, e o CPF na nota foi para o F.
describe("PosShortcutsHelp — o dicionário das teclas", () => {
  const linha = async (rotulo: string) => {
    await mountSuspended(PosShortcutsHelp, { props: { open: true } });
    const item = document.body.querySelectorAll("li");
    return Array.from(item).find((li) => li.textContent?.includes(rotulo));
  };
  const teclas = (li: Element | undefined) =>
    Array.from(li?.querySelectorAll("kbd") || []).map((k) => k.textContent);

  it("no pagamento, F10 é dividir a conta", async () => {
    expect(teclas(await linha("Dividir a conta"))).toEqual(["F10"]);
  });

  it("no pagamento, o CPF na nota é a letra F", async () => {
    expect(teclas(await linha("CPF na nota (liga/desliga)"))).toEqual(["F"]);
  });

  it("na comanda, o F10 continua sendo transferir itens", async () => {
    // As duas telas nunca coexistem: o mesmo par de teclas significa "as duas
    // ações daqui", e a comanda não mudou.
    expect(teclas(await linha("Transferir itens para outra comanda"))).toEqual(["F10"]);
  });
});
