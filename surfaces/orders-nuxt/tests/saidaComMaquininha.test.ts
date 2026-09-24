import { describe, expect, it } from "vitest";

import {
  cardAffordances,
  courierReturnOrders,
  dispatchSteps,
  machinesOutSentence,
  oneTapDispatch,
  onRoadLine,
} from "../app/presentation/board";
import { machines, readyCard } from "./support/dispatchFixtures";

describe("saída: o sistema escolhe a maquininha", () => {
  it("uma livre e nada mais a perguntar: um toque, com a livre", () => {
    expect(oneTapDispatch(readyCard(), [readyCard()])).toEqual([{ ref: "DLV-0420", equipment: ["card_machine:az"] }]);
  });
  it("as duas livres: pergunta (um toque na cor)", () => {
    expect(oneTapDispatch(readyCard({ equipment_options: machines.bothFree }), [])).toBeNull();
  });
  it("nenhuma livre: abre o diálogo que diz onde elas estão", () => {
    expect(oneTapDispatch(readyCard({ equipment_options: machines.noneFree }), [])).toBeNull();
    expect(machinesOutSentence(machines.noneFree)).toBe("As duas maquininhas estão na rua: pedidos 0415 e 0418.");
    expect(machinesOutSentence([machines.noneFree[0]!])).toBe("A maquininha está na rua: pedido 0415.");
  });
  it("pedido sem pagamento na porta não fala de maquininha", () => {
    const cash = readyCard({ dispatch_needs_machine: false, payment_method: "pix" });
    expect(oneTapDispatch(cash, [cash])).toEqual([{ ref: "DLV-0420" }]);
  });
  it("outro pedido pronto para sair: pergunta se vai junto", () => {
    const other = readyCard({ ref: "DLV-0421" });
    expect(oneTapDispatch(readyCard(), [readyCard(), other])).toBeNull();
  });
  it("na mesma saída, quem precisa de maquininha abre; os outros entram nela e a compartilham", () => {
    const cash = readyCard({ ref: "DLV-0421", dispatch_needs_machine: false, change_out_suggested_q: 2600 });
    expect(dispatchSteps([cash, readyCard()], { machineRef: "card_machine:pr" })).toEqual([
      { ref: "DLV-0420", equipment: ["card_machine:pr"] },
      { ref: "DLV-0421", changeOut: "26,00", tripRef: "DLV-0420" },
    ]);
  });
});

describe("volta: um gesto só", () => {
  const onRoad = readyCard({
    status: "dispatched", next_status: "delivered", equipment_label: "Saiu com a maquininha Azul", trip_with: ["DLV-0418"],
    courier_return_orders: ["DLV-0415", "DLV-0418"], courier_return_lines: ["Maquininha Azul", "R$ 20,00 de troco"],
    can_settle_delivery_cash: true, equipment_back_pending: true,
    actions: [{ ref: "courier-back", kind: "mutation", label: "Entregador voltou", priority: "primary", enabled: true, reason: "", href: "", method: "POST", payload_schema: {}, idempotency: "required", confirmation: { required: true } }],
  });
  it("o card na rua diz só com que maquininha saiu e com quem foi junto", () => {
    expect(onRoadLine(onRoad)).toBe("Saiu com a maquininha Azul · junto com 0418");
    expect(onRoadLine(readyCard())).toBe("");
  });
  it("'Entregador voltou' é o único gesto: sem 'Acertar entrega' nem 'Maquininha voltou' avulsos", () => {
    expect(cardAffordances(onRoad).map((a) => [a.ref, a.label])).toEqual([["courier_back", "Entregador voltou"]]);
  });
  it("a confirmação lista os pedidos da saída", () => {
    expect(courierReturnOrders(onRoad)).toBe("Fecha a saída dos pedidos 0415 e 0418.");
    expect(courierReturnOrders({ courier_return_orders: ["DLV-0415"] })).toBe("");
  });
});
