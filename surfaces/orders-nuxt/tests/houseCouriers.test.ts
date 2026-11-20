// "Quem leva" (M3, #2526): o padrão do Admin marcado, a casa a um toque, e sem ninguém
// da casa na escala a tela fica como era.
import { describe, expect, it } from "vitest";

import type { DeliveryStopProjection } from "~/generated/ordersContract";
import {
  DEFAULT_CARRIER,
  busyNotice,
  carrierChips,
  chosenCarrier,
  houseQuoteLines,
  houseRideAction,
  houseRideInputs,
  houseRideResource,
  joinCodes,
  sendLabel,
  shiftChips,
  type HouseCourier,
  type HouseCrew,
} from "~/presentation/houseCouriers";

const person = (ref: string, name: string, extra: Partial<HouseCourier> = {}): HouseCourier => ({
  ref, name, on_shift: true, state: "free", state_label: "Livre", value_q: null, value: "", ...extra,
});

const crew = (couriers: HouseCourier[], extra: Partial<HouseCrew> = {}): HouseCrew => ({
  active: true,
  service: { ref: "casa", name: "Entregadores da casa" },
  default: { ref: "taon", name: "TaOn" },
  couriers,
  ...extra,
});

describe("os chips de quem leva", () => {
  it("sem ninguém da casa na escala, a linha não existe", () => {
    expect(carrierChips(crew([person("rui", "Rui", { on_shift: false })]), { quoteQ: 1100, quoting: false })).toEqual([]);
    expect(carrierChips(crew([person("diego", "Diego")], { active: false }), { quoteQ: 1100, quoting: false })).toEqual([]);
    expect(carrierChips(null, { quoteQ: 1100, quoting: false })).toEqual([]);
  });

  it("o padrão do Admin vem primeiro, com a cotação; a casa depois, com estado e valor da tabela", () => {
    const chips = carrierChips(
      crew([person("diego", "Diego"), person("rui", "Rui", { state: "busy", state_label: "Na rua" })]),
      { quoteQ: 1100, quoting: false, values: { diego: "R$ 15,00", rui: "R$ 18,00" } },
    );
    expect(chips.map((chip) => [chip.key, chip.label, chip.state, chip.value, chip.busy])).toEqual([
      [DEFAULT_CARRIER, "TaOn", "", "R$ 11,00", false],
      ["diego", "Diego", "Livre", "R$ 15,00", false],
      ["rui", "Rui", "Na rua", "R$ 18,00", true],
    ]);
  });

  it("o chip do serviço diz quando cota e quando não cotou", () => {
    const people = crew([person("diego", "Diego")]);
    expect(carrierChips(people, { quoteQ: null, quoting: true })[0]!.value).toBe("Cotando…");
    expect(carrierChips(people, { quoteQ: null, quoting: false })[0]!.value).toBe("Sem cotação agora");
  });

  it("a escolha só vale para quem ainda está na escala", () => {
    const people = crew([person("diego", "Diego"), person("rui", "Rui", { on_shift: false })]);
    expect(chosenCarrier(people, "diego")?.name).toBe("Diego");
    expect(chosenCarrier(people, "rui")).toBeNull();
    expect(chosenCarrier(people, DEFAULT_CARRIER)).toBeNull();
  });
});

describe("o que o sheet diz com a casa escolhida", () => {
  it("uma linha só, o valor da tabela", () => {
    expect(houseQuoteLines("R$ 15,00")).toEqual([{ text: "Valor da tabela: R$ 15,00", strong: true }]);
    expect(houseQuoteLines("")[0]!.strong).toBe(false);
  });

  it("o botão diz para quem vai e quais pedidos", () => {
    expect(joinCodes(["A47"])).toBe("A47");
    expect(joinCodes(["A47", "C03"])).toBe("A47 e C03");
    expect(joinCodes(["A47", "B12", "C03"])).toBe("A47, B12 e C03");
    expect(sendLabel("Diego", ["A47", "C03"])).toBe("Enviar para Diego: A47 e C03");
  });

  it("quem está na rua avisa que a corrida espera, sem travessão", () => {
    expect(busyNotice(person("rui", "Rui", { state: "busy" }))).toBe("Rui está na rua. A corrida espera a volta.");
    expect(busyNotice(person("diego", "Diego"))).toBe("");
    expect(busyNotice(null)).toBe("");
  });
});

describe("a intenção de enviar à casa", () => {
  const stop = (ref: string, revision: string | null, enabled = true) =>
    ({
      ref,
      dispatch_action: revision === null ? null : {
        ref: "courier-dispatch", kind: "mutation", label: "Chamar sozinho", priority: "", enabled,
        reason: enabled ? "" : "Sem permissão.", href: "", method: "POST", idempotency: "required",
        confirmation: {}, payload_schema: { base_revision: revision, expected_actor_id: 7 },
      },
    }) as Pick<DeliveryStopProjection, "ref" | "dispatch_action">;

  it("leva a revisão que a tela leu de cada pedido e quem a leu", () => {
    const action = houseRideAction([stop("A", "r1"), stop("B", "r2")]);
    expect(action.enabled).toBe(true);
    expect(action.payload_schema).toEqual({ expected_actor_id: 7, base_revisions: { A: "r1", B: "r2" } });
  });

  it("sem a revisão de algum pedido, não envia e diz por quê", () => {
    const action = houseRideAction([stop("A", "r1"), stop("B", null)]);
    expect(action.enabled).toBe(false);
    expect(action.reason).toBe("Os pedidos mudaram. Atualize antes de enviar a corrida.");
    expect(houseRideAction([stop("A", "r1", false)]).reason).toBe("Sem permissão.");
  });

  it("a mesma corrida é a mesma intenção em qualquer ordem", () => {
    expect(houseRideResource(["C", "A"])).toBe(houseRideResource(["A", "C"]));
    expect(houseRideInputs({ refs: ["A"], courier: "diego", change_out: { A: "20,00" }, machine: "", number: 2 })).toEqual({
      refs: ["A"], courier: "diego", change_out: { A: "20,00" }, machine: "", ride_number: 2,
    });
  });
});

describe("entregadores de hoje", () => {
  it("todo ativo vira chip; quem está na escala vem marcado, e na rua diz", () => {
    expect(shiftChips(crew([
      person("diego", "Diego", { state: "busy", state_label: "Na rua" }),
      person("rui", "Rui", { on_shift: false }),
    ]))).toEqual([
      { ref: "diego", label: "Diego · Na rua", on: true },
      { ref: "rui", label: "Rui", on: false },
    ]);
  });

  it("sem o serviço da casa ativo, a linha não aparece", () => {
    expect(shiftChips(crew([person("diego", "Diego")], { active: false }))).toEqual([]);
  });
});
