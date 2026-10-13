// O ENTREGADOR (TaOn) no balcão (dono, 13/10/2026): a régua é do servidor (o bloco e
// as ações do Gestor); aqui se prende o que a tela faz com o que veio.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  courierBadgeColor,
  courierCallLabel,
  courierPanelVisible,
  courierRowLine,
  GESTOR_ONLY_COURIER_LINE,
  showsDeliveryExitNotice,
  custodyBody,
  noFreeMachineSentence,
  telHref,
  vehicleLine,
} from "../app/presentation/courier";
import type { PreorderCourier } from "../app/types/preorders";
import { freeMachines, machinePhrase, moneyInput } from "../../operator-kit/app/presentation/custody";

const here = dirname(fileURLToPath(import.meta.url));
const app = (...parts: string[]) => readFileSync(resolve(here, "..", "app", ...parts), "utf8");

const block = (overrides: Partial<PreorderCourier> = {}): PreorderCourier => ({
  provider: "machine",
  status: "",
  status_label: "",
  active: false,
  driver: null,
  tracking_url: "",
  confirmation_code: "",
  attempts_count: 0,
  error: null,
  can_dispatch: false,
  ...overrides,
});

describe("a linha da corrida na lista", () => {
  it("diz a frase do servidor com o tom", () => {
    expect(courierRowLine({ courier_label: "Entregador não chamado", courier_tone: "warning", situation: "ready", situation_label: "Pronto" }))
      .toEqual({ label: "Entregador não chamado", tone: "warning" });
    expect(courierRowLine({ courier_label: "Não atendida", courier_tone: "danger", situation: "ready", situation_label: "Pronto" }))
      .toEqual({ label: "Não atendida", tone: "danger" });
  });

  it("não fala quando não há o que dizer, nem repete o selo de situação", () => {
    expect(courierRowLine({ courier_label: "", courier_tone: "", situation: "to_pay", situation_label: "A pagar" })).toBeNull();
    expect(courierRowLine({ situation: "to_pay", situation_label: "A pagar" })).toBeNull();
    expect(courierRowLine({ courier_label: "Saiu para entrega", courier_tone: "info", situation: "out_for_delivery", situation_label: "Saiu para entrega" })).toBeNull();
    expect(courierRowLine({ courier_label: "Entregue", courier_tone: "success", situation: "delivered", situation_label: "Entregue" })).toBeNull();
  });
});

describe("o painel do entregador no detalhe", () => {
  it("aparece quando há corrida, chamada sem resposta, falha ou chamar agora", () => {
    expect(courierPanelVisible(null)).toBe(false);
    expect(courierPanelVisible(block())).toBe(false);
    expect(courierPanelVisible(block({ can_dispatch: true }))).toBe(true);
    expect(courierPanelVisible(block({ can_dispatch_again: true }))).toBe(true);
    expect(courierPanelVisible(block({ status: "A" }))).toBe(true);
    expect(courierPanelVisible(block({ error: { message: "Recusada", at: "" } }))).toBe(true);
  });

  it("o gesto tem o nome do Gestor: Chamar entregador, e depois de corrida não concluída, Chamar outro entregador", () => {
    expect(courierCallLabel(block())).toBe("Chamar entregador");
    expect(courierCallLabel(block({ status: "N" }))).toBe("Chamar outro entregador");
    expect(courierCallLabel(block({ attempts_count: 1 }))).toBe("Chamar outro entregador");
  });

  it("o tom vira a cor do selo do Nuxt UI", () => {
    expect(courierBadgeColor("danger")).toBe("error");
    expect(courierBadgeColor("warning")).toBe("warning");
    expect(courierBadgeColor("")).toBe("neutral");
    expect(courierBadgeColor(undefined)).toBe("neutral");
  });

  it("quem vem: veículo e telefone discável", () => {
    expect(vehicleLine({ name: "Carlos", phone: "", vehicle_model: "Moto", vehicle_plate: "ABC1D23" })).toBe("Moto · ABC1D23");
    expect(vehicleLine(null)).toBe("");
    expect(telHref("(43) 99876-1234")).toBe("tel:43998761234");
  });
});

describe("o aviso de saída pelo Gestor (seguimento)", () => {
  it("sai quando o PDV já oferece o Entregador, e fica sem ele (TaOn desligada)", () => {
    expect(showsDeliveryExitNotice({ fulfillment_type: "delivery" }, block({ can_dispatch: true }))).toBe(false);
    expect(showsDeliveryExitNotice({ fulfillment_type: "delivery" }, block({ status: "A" }))).toBe(false);
    expect(showsDeliveryExitNotice({ fulfillment_type: "delivery" }, null)).toBe(true);
    expect(showsDeliveryExitNotice({ fulfillment_type: "pickup" }, null)).toBe(true);
  });

  it("o que ainda é só do Gestor cabe numa frase, sem travessão", () => {
    expect(GESTOR_ONLY_COURIER_LINE).toBe("No Gestor de pedidos: cancelar a corrida e registrar a volta do troco ou da maquininha.");
    expect(GESTOR_ONLY_COURIER_LINE).not.toMatch(/[\u2013\u2014]/);
  });
});

describe("a custódia da chamada", () => {
  const machines = [
    { ref: "card_machine:A", label: "Maquininha 1", enabled: true },
    { ref: "card_machine:B", label: "Azul", enabled: false, reason: "Na rua com o pedido 1043" },
    { ref: "cash_bag", label: "Malote" },
  ];

  it("só as maquininhas livres saem", () => {
    expect(freeMachines(machines).map((m) => m.ref)).toEqual(["card_machine:A"]);
    expect(machinePhrase("Azul")).toBe("maquininha Azul");
    expect(machinePhrase("Maquininha 1")).toBe("maquininha 1");
  });

  it("sem maquininha livre, diz onde estão e o que fazer", () => {
    expect(noFreeMachineSentence(machines)).toBe("Azul: Na rua com o pedido 1043. Espere uma voltar para chamar.");
    expect(noFreeMachineSentence([])).toBe("Nenhuma maquininha livre. Espere uma voltar para chamar.");
  });

  it("o corpo leva só o que a chamada perguntou, no formato do Gestor", () => {
    expect(moneyInput(2000)).toBe("20,00");
    expect(custodyBody({ change_out_suggested_q: 2000, needs_machine: false, recorded: false }, { changeOut: "20,00", machineRef: "card_machine:A" }))
      .toEqual({ change_out: "20,00" });
    expect(custodyBody({ change_out_suggested_q: 0, needs_machine: true, recorded: false }, { changeOut: "", machineRef: "card_machine:A" }))
      .toEqual({ equipment: ["card_machine:A"] });
    expect(custodyBody(undefined, { changeOut: "5", machineRef: "" })).toEqual({});
  });
});

describe("a fiação", () => {
  it("o balcão chama pelas MESMAS rotas e ações do Gestor", () => {
    const actions = app("composables", "usePosPreorderActions.ts");
    expect(actions).toContain('courier("courier-dispatch", custody)');
    expect(actions).toContain('courier("courier-dispatch-again")');
    expect(actions).toContain("/api/v1/backstage/orders/${encodeURIComponent(detail.ref)}/${ref}/");
    expect(actions).toContain("detailAction(detail, ref)");
  });

  it("o detalhe aberto se refaz no evento de pedido (SSE), não só a lista", () => {
    const preorders = app("composables", "usePosPreorders.ts");
    expect(preorders).toContain("refreshNuxtData(preordersLiveKeys(openDetail.value))");
  });

  it("a custódia vem do kit nos dois apps (Gestor e PDV)", () => {
    const panel = app("components", "PosCourierPanel.vue");
    expect(panel).toContain('from "../../../operator-kit/app/presentation/custody"');
    const gestor = readFileSync(resolve(here, "..", "..", "orders-nuxt", "app", "components", "OrderCourierPanel.vue"), "utf8");
    expect(gestor).toContain('from "../../../operator-kit/app/presentation/custody"');
    expect(app("presentation", "courier.ts")).not.toMatch(/export function (freeMachines|machinePhrase|moneyInput)/);
  });

  it("o painel mora no painel do Balcão e o chamar de novo confirma com a frase do servidor", () => {
    const page = app("pages", "preorders", "[ref].vue");
    expect(page).toContain("<PosCourierPanel");
    expect(page).toContain("detailAction(detail, 'courier-dispatch')");
    const panel = app("components", "PosCourierPanel.vue");
    expect(panel).toContain("dispatchAgainAction?.confirmation?.description");
    expect(panel).toContain("dispatchAction?.confirmation?.description");
  });
});
