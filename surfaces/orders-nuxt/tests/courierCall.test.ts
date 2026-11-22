// #2876: chamar o entregador a partir de UM pedido (cartão Pronto e detalhe), no
// MESMO sheet das Entregas. Decisão 1 = A do dono: o companheiro da sugestão vem
// marcado como "Sugestão da casa", a cotação é só leitura.
import { describe, expect, it } from "vitest";
import type { DeliveryStopProjection } from "../app/generated/ordersContract";
import {
  companionChoices,
  companionNote,
  drawerLine,
  initialRide,
  moneyToQ,
  orderCallDescription,
  orderCallLabel,
  suggestionFor,
} from "../app/presentation/courierCall";
import { rideCalls, type RideSuggestion } from "../app/presentation/deliveries";
import { waitingBandText, withCourierCall, type Affordance } from "../app/presentation/board";

function stop(ref: string, extra: Partial<DeliveryStopProjection> = {}): DeliveryStopProjection {
  return {
    ref, code: ref.slice(-3), customer: "Ana", place: "Gleba Palhano", address: "", latitude: -23.32, longitude: -51.17,
    stage: "Pronto", volumes: 1, done: false, change_out_suggested_q: 0, needs_machine: false, change_label: "",
    group_refusal: "", error: "", dispatch_action: null, dispatch_again_action: null, charge_outdated: null,
    fiscal_status: "", danfe_state: "", danfe_problem: "", ...extra,
  };
}
const A47 = "WEB-0A47";
const C03 = "WEB-0C03";
const plan = (extra: Partial<RideSuggestion> = {}): RideSuggestion => ({
  key: `${A47}+${C03}`, refs: [A47, C03], codes: ["A47", "C03"], places: "Gleba Palhano", quoted: true, suggested: true,
  late_code: "C03", late_minutes: 6, together_q: 1100, minutes: 18, km: 7.4, with_return: false, separate_q: 1700,
  saving_q: 600, ...extra,
});

describe("a corrida com que o sheet abre", () => {
  it("com a sugestão da casa (cotada e mais barata), o companheiro já vem marcado", () => {
    expect(initialRide(A47, plan(), 4)).toEqual([A47, C03]);
    expect(suggestionFor(C03, [plan()])?.key).toBe(`${A47}+${C03}`);
  });

  it("sem cotação ou sem sugestão, só o pedido: dinheiro da casa não se decide no escuro", () => {
    expect(initialRide(A47, plan({ suggested: false, quoted: false }), 4)).toEqual([A47]);
    expect(initialRide(A47, null, 4)).toEqual([A47]);
  });

  it("o companheiro que já está em outra corrida em edição não entra", () => {
    expect(initialRide(A47, plan(), 4, new Set([C03]))).toEqual([A47]);
  });
});

describe("Vai junto nesta corrida?", () => {
  const anchor = stop(A47, { latitude: -23.32, longitude: -51.17 });
  const near = stop("WEB-0B12", { latitude: -23.321, longitude: -51.171 });
  const far = stop("WEB-0F09", { latitude: -23.4, longitude: -51.3 });
  const mate = stop(C03, { latitude: -23.35, longitude: -51.2, change_label: "Troco para R$ 50,00" });

  it("o companheiro da sugestão primeiro e marcado; depois os mais perto", () => {
    const choices = companionChoices(anchor, [anchor, far, near, mate], [A47, C03], { plan: plan(), maxStops: 4 });
    expect(choices.map((choice) => choice.code)).toEqual(["C03", "B12", "F09"]);
    expect(choices[0]).toMatchObject({ suggested: true, checked: true, note: "Troco para R$ 50,00" });
    expect(choices[1]).toMatchObject({ suggested: false, checked: false });
  });

  it("quem não vai em corrida nenhuma, ou já está em outra, fica de fora", () => {
    const refused = stop("WEB-0G07", { group_refusal: "Chamada sem resposta." });
    const choices = companionChoices(anchor, [anchor, refused, near, mate], [A47], {
      plan: null, maxStops: 4, taken: new Set([near.ref]),
    });
    expect(choices.map((choice) => choice.code)).toEqual(["C03"]);
  });

  it("corrida cheia: quem não está nela fica desabilitado", () => {
    const choices = companionChoices(anchor, [anchor, near, mate], [A47, C03], { plan: plan(), maxStops: 2 });
    expect(choices).toEqual([expect.objectContaining({ code: "C03", checked: true, disabled: false })]);
    const full = companionChoices(anchor, [anchor, near, mate], [A47, near.ref], { plan: plan(), maxStops: 2 });
    expect(full.map((choice) => [choice.code, choice.disabled])).toEqual([["C03", true]]);
  });

  it("sem cotação da TaOn, a frase convida a marcar; pedido em preparo avisa que a hora não é certa", () => {
    const unquoted = companionChoices(anchor, [anchor, mate], [A47], { plan: plan({ quoted: false, suggested: false }), maxStops: 4 });
    expect(companionNote(plan({ quoted: false }), unquoted, "TaOn")).toEqual({
      text: "A TaOn não cotou agora. Marque C03 se quiser levar junto.", warning: true,
    });
    const preparing = companionChoices(anchor, [anchor, stop(C03, { stage: "Em preparo" })], [A47], { plan: null, maxStops: 4 });
    expect(companionNote(null, preparing)?.text).toBe(
      "C03 ainda está em preparo e a casa não sabe a hora em que fica pronto. Marque só se sai agora.",
    );
    expect(companionNote(plan(), companionChoices(anchor, [anchor, mate], [A47, C03], { plan: plan(), maxStops: 4 }))).toBeNull();
  });
});

describe("o que o sheet aberto por um pedido escreve", () => {
  it("o botão diz o que vai acontecer", () => {
    expect(orderCallLabel(["A47"])).toBe("Chamar entregador para A47");
    expect(orderCallLabel(["A47", "C03"])).toBe("Chamar corrida com A47 e C03");
    expect(orderCallLabel(["A47", "C03", "B12"])).toBe("Chamar corrida com A47, C03 e B12");
  });

  it("a linha de baixo do título diz quem, onde, e quem paga, sem travessão", () => {
    const text = orderCallDescription(stop(A47));
    expect(text).toBe("A47 · Ana · Gleba Palhano · Pronto. A corrida é paga pela casa e o frete dos clientes não muda.");
    expect(text).not.toMatch(/[—–]/);
  });

  it("Sai da gaveta soma o troco de todas as paradas; ilegível ou zero, nada", () => {
    expect(drawerLine(["50,00", "20,00"])).toBe("Sai da gaveta: R$ 70,00 de troco.");
    expect(drawerLine(["", "0"])).toBe("");
    expect(drawerLine(["50,00", "abc"])).toBe("");
    expect(moneyToQ("R$ 1.250,50")).toBe(125050);
  });
});

// A custódia que a confirmação em linha do Painel pedia (troco e maquininha) agora sai
// do sheet, pela MESMA chamada das Entregas (`rideCalls`).
describe("a custódia que sai com o entregador", () => {
  it("troco pré-preenchido pelo pedido vai junto na chamada", () => {
    const [call] = rideCalls([{ number: 3, refs: [A47] }], [stop(A47, { change_out_suggested_q: 2600 })], {});
    expect(call).toMatchObject({ kind: "single", refs: [A47], change_out: { [A47]: "26,00" }, machine: "" });
  });

  it("o troco que o operador corrigiu é o que vai", () => {
    const [call] = rideCalls([{ number: 3, refs: [A47] }], [stop(A47, { change_out_suggested_q: 2600 })], {}, { [A47]: "30,00" });
    expect(call!.change_out).toEqual({ [A47]: "30,00" });
  });

  it("a maquininha da corrida vai quando algum pedido paga no cartão", () => {
    const [call] = rideCalls([{ number: 3, refs: [A47, C03] }], [stop(A47), stop(C03, { needs_machine: true })], { 3: "machine:azul" });
    expect(call).toMatchObject({ kind: "group", machine: "machine:azul" });
  });

  it("pedido pago: nada de troco nem maquininha", () => {
    const [call] = rideCalls([{ number: 3, refs: [A47] }], [stop(A47)], {});
    expect(call).toMatchObject({ change_out: {}, machine: "" });
  });
});

describe("o cartão Pronto e a faixa da Saída (Painel)", () => {
  const despachar: Affordance = { ref: "advance", label: "Despachar A47", icon: "lucide:truck", priority: "primary", needsInput: false };

  it("o cartão que dá para chamar ganha o Chamar entregador como gesto principal; o de antes vira secundário", () => {
    const list = withCourierCall([despachar], true);
    expect(list.map((aff) => [aff.ref, aff.label, aff.priority])).toEqual([
      ["call_courier", "Chamar entregador", "primary"],
      ["advance", "Despachar A47", "secondary"],
    ]);
    expect(withCourierCall([despachar], false)).toEqual([despachar]);
  });

  it("a faixa conta quem aguarda; zero some; desconhecido, sem número (nunca zero)", () => {
    expect(waitingBandText(5)).toBe("Aguardando entregador: 5");
    expect(waitingBandText(0)).toBe("");
    expect(waitingBandText(null)).toBe("Aguardando entregador");
  });
});
