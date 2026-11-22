// #2876: o cartão Pronto e o detalhe do pedido abrem o MESMO sheet das Entregas, pela
// mesma orquestração (`useCourierCall`). O que a confirmação em linha do Painel provava
// (um toque nunca chama; a custódia vai junto; o pedido mudou, a confirmação cai)
// continua provado aqui, agora no sheet.
import { nextTick, ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import type { DeliveriesProjection, DeliveryStopProjection } from "../../app/generated/ordersContract";

const env = installNuxtGlobals();
const execute = vi.fn(async () => true);
const executeRide = vi.fn(async () => ({ outcome: "applied" }));
const executePath = vi.fn(async () => ({ outcome: "applied" }));
vi.stubGlobal("useOrderIntention", () => ({ execute, executeRide, executePath }));
vi.stubGlobal("useEditingQuotes", () => ref({}));
vi.stubGlobal("useHouseCrew", () => ({
  crew: ref(null), values: ref({}), valuesQ: ref({}), refresh: vi.fn(), toggleShift: vi.fn(), toggling: ref(""),
}));
const { useCourierCall } = await import("../../app/composables/useCourierCall");

const A47 = "WEB-0A47";
const C03 = "WEB-0C03";
const D12 = "WEB-0D12";
const action = (ref: string) => ({
  ref: "courier-dispatch", kind: "mutation", label: "Chamar sozinho", priority: "", enabled: true, reason: "", href: "",
  method: "POST", idempotency: "required", confirmation: {}, payload_schema: { base_revision: `r-${ref}` },
});
function stop(ref: string, extra: Partial<DeliveryStopProjection> = {}): DeliveryStopProjection {
  return {
    ref, code: ref.slice(-3), customer: "Ana", place: "Gleba Palhano", address: "", latitude: -23.32, longitude: -51.17,
    stage: "Pronto", volumes: 1, done: false, change_out_suggested_q: 0, needs_machine: false, change_label: "",
    group_refusal: "", error: "", dispatch_action: action(ref) as never, dispatch_again_action: null,
    charge_outdated: null, fiscal_status: "", danfe_state: "", danfe_problem: "", ...extra,
  };
}
function deliveries(extra: Partial<DeliveriesProjection> = {}): DeliveriesProjection {
  return {
    origin: { latitude: -23.33, longitude: -51.18 },
    waiting: [
      stop(A47, { change_out_suggested_q: 5000 }),
      stop(C03, { change_out_suggested_q: 2000, latitude: -23.31 }),
      stop(D12, { stage: "Em preparo", latitude: -23.36 }),
    ],
    rides: [], max_stops: 4, machines: [], courier_on: true, house_on: false, maps_key: "",
    group_action: { ...action("group"), ref: "courier-ride", payload_schema: { base_revisions: { [A47]: "a", [C03]: "c" } } } as never,
    free_numbers: [3, 4, 5], next_number: 3,
    ride_plan: {
      suggestions: [{
        key: `${A47}+${C03}`, refs: [A47, C03], codes: ["A47", "C03"], places: "Gleba Palhano", quoted: true, suggested: true,
        late_code: "C03", late_minutes: 6, together_q: 1100, minutes: 18, km: 7.4, with_return: false, separate_q: 1700, saving_q: 600,
      }],
      service: "taon", service_reason: "default",
      service_options: [{ ref: "taon", name: "TaOn", kind: "machine", is_default: true }],
    } as never,
    ...extra,
  };
}

function setup(data = deliveries()) {
  const source = ref<DeliveriesProjection | null>(data);
  const refresh = vi.fn(async () => undefined);
  const onCalled = vi.fn();
  const flow = useCourierCall({ data: source, refresh, onCalled });
  return { source, refresh, onCalled, flow };
}

describe("o sheet aberto por um pedido", () => {
  beforeEach(() => {
    env.reset();
    execute.mockClear();
    executeRide.mockClear();
  });

  it("abre com o companheiro da sugestão marcado, na letra livre; um toque nunca chama", () => {
    const { flow } = setup();
    expect(flow.openOrder(A47)).toBe("");
    const sheet = flow.sheet.value;
    expect(sheet.open).toBe(true);
    expect(sheet.title).toBe("Chamar entregador para A47");
    expect(sheet.rides.map((ride) => [ride.letter, ride.stops.map((s) => s.code)])).toEqual([["C", ["A47", "C03"]]]);
    expect(sheet.callLabel).toBe("Chamar corrida com A47 e C03");
    expect(sheet.aloneLabel).toBe("Chamar só A47");
    expect(sheet.companions?.choices[0]).toMatchObject({ code: "C03", suggested: true, checked: true });
    // A cotação da sugestão mora sob o companheiro: o cartão da corrida não a repete.
    expect(sheet.companions?.lines.map((line) => line.text)).toEqual([
      "Juntas: R$ 11,00 · 18 min · 7,4 km ✔", "Separadas sairiam R$ 17,00",
    ]);
    expect(sheet.rides[0]!.lines).toEqual([]);
    expect(sheet.drawer).toBe("Sai da gaveta: R$ 70,00 de troco.");
    expect(execute).not.toHaveBeenCalled();
    expect(executeRide).not.toHaveBeenCalled();
  });

  it("confirmar chama UMA corrida com os dois, com o troco de cada um e a letra", async () => {
    const { flow, onCalled } = setup();
    flow.openOrder(A47);
    flow.setChange(C03, "25,00");
    await flow.confirmSheet();
    expect(executeRide).toHaveBeenCalledTimes(1);
    expect(executeRide.mock.calls[0]![1]).toEqual({
      refs: [A47, C03], change_out: { [A47]: "50,00", [C03]: "25,00" }, machine: "", ride_number: 3,
    });
    expect(onCalled).toHaveBeenCalledWith([A47, C03]);
    expect(flow.sheet.value.open).toBe(false);
  });

  it("Chamar só A47: o companheiro sai e vai a chamada de um pedido, com o troco dele", async () => {
    const { flow } = setup();
    flow.openOrder(A47);
    await flow.confirmAlone();
    expect(executeRide).not.toHaveBeenCalled();
    expect(execute).toHaveBeenCalledTimes(1);
    expect(execute.mock.calls[0]!.slice(0, 2)).toEqual([A47, "courier-dispatch"]);
    expect(execute.mock.calls[0]![3]).toEqual({ change_out: "50,00", ride_number: 3 });
  });

  it("desmarcar o companheiro troca o botão; em preparo entra só se o operador marcar", () => {
    const { flow } = setup();
    flow.openOrder(A47);
    flow.toggleCompanion(C03);
    expect(flow.sheet.value.callLabel).toBe("Chamar entregador para A47");
    expect(flow.sheet.value.aloneLabel).toBe("");
    const d12 = flow.sheet.value.companions?.choices.find((choice) => choice.code === "D12");
    expect(d12).toMatchObject({ checked: false, stage: "Em preparo" });
    flow.toggleCompanion(D12);
    expect(flow.sheet.value.callLabel).toBe("Chamar corrida com A47 e D12");
  });

  it("sem sugestão cotada, nada vem marcado", () => {
    const data = deliveries();
    (data.ride_plan as { suggestions: { suggested: boolean; quoted: boolean }[] }).suggestions[0]!.suggested = false;
    (data.ride_plan as { suggestions: { suggested: boolean; quoted: boolean }[] }).suggestions[0]!.quoted = false;
    const { flow } = setup(data);
    flow.openOrder(A47);
    expect(flow.sheet.value.rides[0]!.stops.map((s) => s.code)).toEqual(["A47"]);
    expect(flow.sheet.value.companions?.note).toEqual({ text: "A TaOn não cotou agora. Marque C03 se quiser levar junto.", warning: true });
  });

  it("o pedido mudou (chamado em outro dispositivo): o sheet fecha e o toque de antes não vale", async () => {
    const { flow, source } = setup();
    flow.openOrder(A47);
    source.value = deliveries({ waiting: [stop(C03), stop(D12)] });
    await nextTick();
    await nextTick();
    expect(flow.sheet.value.open).toBe(false);
    expect(execute).not.toHaveBeenCalled();
  });

  it("chamada sem resposta: não abre, e diz por quê", () => {
    const { flow } = setup(deliveries({
      waiting: [stop(A47, { dispatch_again_action: action(A47) as never, error: "A TaOn não respondeu à última chamada." })],
    }));
    expect(flow.openOrder(A47)).toBe("A TaOn não respondeu à última chamada.");
    expect(flow.sheet.value.open).toBe(false);
  });

  it("maquininha: a única livre vai na corrida; sem nenhuma, o chamar espera com o motivo", async () => {
    const card = deliveries({
      waiting: [stop(A47, { needs_machine: true })],
      machines: [{ ref: "machine:azul", label: "Azul" }],
      ride_plan: null,
    });
    const { flow } = setup(card);
    flow.openOrder(A47);
    expect(flow.sheet.value.rides[0]).toMatchObject({ needsMachine: true, machine: "machine:azul" });
    expect(flow.sheet.value.canCall).toBe(true);
    await flow.confirmSheet();
    expect(execute.mock.calls[0]![3]).toEqual({ equipment: ["machine:azul"], ride_number: 3 });

    const none = setup(deliveries({ waiting: [stop(A47, { needs_machine: true })], machines: [], ride_plan: null })).flow;
    none.openOrder(A47);
    expect(none.sheet.value.canCall).toBe(false);
    expect(none.sheet.value.reason).toBe("Faltam maquininhas: 1 corridas levam cartão e nenhuma está livre.");
  });

  it("Voltar desfaz a corrida do sheet; nada foi gravado", () => {
    const { flow } = setup();
    flow.openOrder(A47);
    flow.closeSheet();
    expect(flow.sheet.value.open).toBe(false);
    expect(flow.editing.value).toEqual([]);
  });
});
