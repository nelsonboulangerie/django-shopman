import { describe, expect, it } from "vitest";
import { COURIER_CHARGE_TITLE, courierChargeNotice } from "../app/presentation/courierCharge";

// P2-28: o pedido mudou depois de chamar o entregador e a observação da corrida
// (o que cobrar na porta) ficou para trás.

const OUTDATED = {
  sent: "Cobrar R$ 50,00 em dinheiro · troco para R$ 100,00",
  current: "Cobrar R$ 63,00 em dinheiro · sem troco",
  collected: false,
};

describe("courierChargeNotice", () => {
  it("sem diferença, sem aviso", () => {
    expect(courierChargeNotice(null, { cancelHere: true })).toBeNull();
    expect(courierChargeNotice(undefined, { cancelHere: false })).toBeNull();
  });

  it("antes da coleta, no Gestor: o que a corrida leva, o de agora e cancelar para chamar de novo", () => {
    const notice = courierChargeNotice(OUTDATED, { cancelHere: true });
    expect(notice?.title).toBe(COURIER_CHARGE_TITLE);
    expect(notice?.description).toBe(
      "Na corrida: Cobrar R$ 50,00 em dinheiro · troco para R$ 100,00. "
        + "No pedido: Cobrar R$ 63,00 em dinheiro · sem troco. "
        + "A TaOn não muda a corrida aberta: solicite o cancelamento e chame o entregador de novo.",
    );
  });

  it("no PDV, o cancelamento mora no Gestor", () => {
    expect(courierChargeNotice(OUTDATED, { cancelHere: false })?.description).toContain(
      "no Gestor de pedidos, solicite o cancelamento",
    );
  });

  it("depois da coleta, o telefone", () => {
    const notice = courierChargeNotice({ ...OUTDATED, collected: true }, { cancelHere: true });
    expect(notice?.description).toMatch(/O entregador já coletou: ligue para ele e passe a cobrança nova\.$/);
  });

  it("sem travessão", () => {
    for (const collected of [false, true]) {
      for (const cancelHere of [false, true]) {
        const notice = courierChargeNotice({ ...OUTDATED, collected }, { cancelHere });
        expect(`${notice?.title} ${notice?.description}`).not.toMatch(/[—–]/);
      }
    }
  });
});
