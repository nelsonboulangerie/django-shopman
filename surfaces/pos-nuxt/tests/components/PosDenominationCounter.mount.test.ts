// O contador da Sessão (abrir e fechar o caixa) é AJUDA: abrir o contador não pode
// apagar o valor que o operador já digitou no campo. Só a contagem guardada no
// estado do app (`stateKey`, o Fim do dia) volta ao pai no mount (beta 05/11, PDV-04).
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { describe, expect, it } from "vitest";

import PosDenominationCounter from "~/components/PosDenominationCounter.vue";
import type { POSChangeDenomination } from "~/types/pos";

const denominations: POSChangeDenomination[] = [
  { q: 5000, label: "50", shape: "note" },
  { q: 50, label: "0,50", shape: "coin" },
];

describe("PosDenominationCounter no mount", () => {
  it("sem stateKey, não emite total no mount (o campo digitado fica)", async () => {
    const wrapper = await mountSuspended(PosDenominationCounter, { props: { denominations } });
    expect(wrapper.emitted("total-q")).toBeUndefined();
    expect(wrapper.emitted("progress")).toBeUndefined();
  });

  it("com stateKey, a contagem guardada volta ao pai no mount", async () => {
    const key = "test-denom-counter:restored";
    useState<Record<number, string>>(`${key}:counts`, () => ({})).value[5000] = "2";
    const wrapper = await mountSuspended(PosDenominationCounter, { props: { denominations, stateKey: key } });
    expect(wrapper.emitted("total-q")?.[0]).toEqual([10000]);
  });
});
