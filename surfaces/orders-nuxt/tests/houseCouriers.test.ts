// "Quem leva" (M3, #2526): o padrão do Admin marcado, a casa a um toque, e sem ninguém
// da casa na escala a tela fica como era.
import { describe, expect, it } from "vitest";

import type { DeliveryStopProjection } from "~/generated/ordersContract";
import {
  DEFAULT_CARRIER,
  busyNotice,
  callSummaryByCarrier,
  carrierChips,
  OTHER_CARRIER,
  chipLine,
  chipValue,
  choiceFromChip,
  noteLabel,
  otherCouriers,
  houseCodes,
  houseGesturePath,
  houseGestureResource,
  houseGestures,
  houseSlipPath,
  slipPrintedMessage,
  callCourier,
  withHouseRides,
  ordersWord,
  mixedTotalLines,
  rideValueQ,
  chosenCarrier,
  houseQuoteLines,
  houseRideAction,
  houseRideInputs,
  houseRideResource,
  joinCodes,
  sendLabel,
  shiftChips,
  toPayToday,
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

describe("refinamentos do Quem leva (M3c)", () => {
  const five = crew([
    person("ana", "Ana"),
    person("bruno", "Bruno"),
    person("caio", "Caio", { state: "busy", state_label: "Volta 12h50" }),
    person("diego", "Diego"),
    person("eva", "Eva"),
  ]);

  it("com mais de 3 na escala, o último chip vira Outro da casa; os livres vêm primeiro", () => {
    const chips = carrierChips(five, { quoteQ: 1100, quoting: false });
    expect(chips.map((chip) => chip.label)).toEqual(["TaOn", "Ana", "Bruno", "Outro da casa"]);
    expect(chips[3]!.state).toBe("Mais 3 na escala");
    expect(otherCouriers(five).map((courier) => courier.ref)).toEqual(["diego", "eva", "caio"]);
  });

  it("tocar em Outro da casa escolhe o primeiro da lista, e o chip diz quem é, com o ✔", () => {
    const ref = choiceFromChip(five, OTHER_CARRIER);
    expect(ref).toBe("diego");
    expect(chipValue(five, ref)).toBe(OTHER_CARRIER);
    const chips = carrierChips(five, { quoteQ: 1100, quoting: false, chosen: ref, values: { diego: "R$ 15,00" } });
    expect(chipLine(chips[3]!)).toBe("Diego · R$ 15,00 ✔");
    expect(chipValue(five, "ana")).toBe("ana");
  });

  it("até 3 na escala, cada um tem o seu chip", () => {
    const three = crew([person("ana", "Ana"), person("bruno", "Bruno"), person("caio", "Caio")]);
    expect(carrierChips(three, { quoteQ: 1100, quoting: false }).map((chip) => chip.key)).toEqual([DEFAULT_CARRIER, "ana", "bruno", "caio"]);
    expect(otherCouriers(three)).toEqual([]);
  });

  it("quem está na rua diz a hora da volta no chip", () => {
    const chips = carrierChips(crew([person("caio", "Caio", { state: "busy", state_label: "Volta 12h50" })]), { quoteQ: null, quoting: false, values: { caio: "R$ 18,00" } });
    expect(chipLine(chips[1]!)).toBe("Volta 12h50 · R$ 18,00");
  });

  it("sem a TaOn, só a casa: sem chip do serviço, e o primeiro livre vem marcado", () => {
    const people = crew([person("caio", "Caio", { state: "busy", state_label: "Na rua" }), person("diego", "Diego")]);
    const chips = carrierChips(people, { quoteQ: null, quoting: false, serviceOn: false });
    expect(chips.map((chip) => [chip.key, chip.chosen])).toEqual([["diego", true], ["caio", false]]);
    expect(chosenCarrier(people, undefined, false)?.ref).toBe("diego");
    expect(chosenCarrier(people, undefined, true)).toBeNull();
    expect(chosenCarrier(crew([]), undefined, false)).toBeNull();
  });

  it("a observação vai junto quando escrita, e o campo diz para quem", () => {
    expect(noteLabel("Diego")).toBe("Observação para Diego (opcional)");
    expect(houseRideInputs({ refs: ["A"], courier: "diego", change_out: {}, machine: "", note: "  Interfone quebrado.  " }).note).toBe("Interfone quebrado.");
    expect("note" in houseRideInputs({ refs: ["A"], courier: "diego", change_out: {}, machine: "", note: "  " })).toBe(false);
  });
});

describe("o ✔ marca quem leva", () => {
  const people = crew([person("diego", "Diego")]);
  const lines = (chosen: string) =>
    carrierChips(people, { quoteQ: 1650, quoting: false, values: { diego: "R$ 15,00" }, chosen }).map(chipLine);

  it("vem no padrão e anda com a escolha, nunca em dois", () => {
    expect(lines(DEFAULT_CARRIER)).toEqual(["R$ 16,50 ✔", "Livre · R$ 15,00"]);
    expect(lines("diego")).toEqual(["R$ 16,50", "Livre · R$ 15,00 ✔"]);
  });
});

describe("o total segue quem leva cada corrida", () => {
  it("a casa conta pela tabela, a TaOn pela cotação", () => {
    expect(rideValueQ({ house: true, houseValueQ: 1500, quoteQ: 1650 })).toBe(1500);
    expect(rideValueQ({ house: false, houseValueQ: 1500, quoteQ: 1650 })).toBe(1650);
    // Sem o valor de quem leva, nada: nunca o de outro serviço no lugar.
    expect(rideValueQ({ house: true, houseValueQ: undefined, quoteQ: 1650 })).toBeNull();
  });

  it("com Diego, o rodapé diz o valor da tabela, não a cotação da TaOn", () => {
    expect(callSummaryByCarrier(2, 1, [rideValueQ({ house: true, houseValueQ: 1500, quoteQ: 1650 })])).toBe(
      "2 pedidos em 1 corrida · R$ 15,00",
    );
  });

  it("corridas misturadas somam o valor de cada uma; faltou um, sem total", () => {
    expect(callSummaryByCarrier(3, 2, [1500, 1250])).toBe("3 pedidos em 2 corridas · R$ 27,50");
    expect(callSummaryByCarrier(3, 2, [1500, null])).toBe("3 pedidos em 2 corridas");
    expect(mixedTotalLines([1500, 1250])).toEqual([{ text: "Total: R$ 27,50", strong: true }]);
    expect(mixedTotalLines([1500, null])).toEqual([]);
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

describe("a corrida da casa na lista (M3b)", () => {
  const action = (label: string, confirm = true) =>
    ({
      ref: "x", kind: "mutation", label, priority: "", enabled: true, reason: "", href: "", method: "POST",
      payload_schema: { base_revision: "r", expected_actor_id: 1 }, idempotency: "required",
      confirmation: confirm ? { required: true, description: "?" } : { required: false },
    }) as never;
  const house = (extra: Record<string, unknown>) =>
    ({
      house: {
        courier_ref: "diego", courier_name: "Diego", moment: "", hint: "", delivered: 0, total: 2, link_claimed: false,
        depart_action: null, deliver_actions: [], resend_action: null, release_action: null, ...extra,
      },
    }) as never;

  it("antes de sair: Saiu é o gesto do momento, o link vem depois", () => {
    const list = houseGestures(house({ depart_action: action("Despachar a corrida C"), resend_action: action("Reenviar o link", false) }));
    expect(list.map((item) => [item.key, item.primary])).toEqual([["depart", true], ["resend", false], ["slip", false]]);
  });

  it("a via impressa com o QR do link vale enquanto o link vale, e não pede confirmação (#2406)", () => {
    const slip = houseGestures(house({ resend_action: action("Reenviar o link") })).find((item) => item.key === "slip");
    expect(slip?.action.label).toBe("Imprimir a via");
    expect(slip?.icon).toBe("i-lucide-printer");
    expect((slip?.action.confirmation as { required: boolean }).required).toBe(false);
    expect(houseSlipPath("CASA-7/x")).toBe("/api/v1/backstage/deliveries/couriers/rides/CASA-7%2Fx/slip/");
    expect(slipPrintedMessage("C", false)).toBe("Via da corrida C impressa.");
    expect(slipPrintedMessage("C", true)).toBe("2ª via da corrida C impressa.");
  });

  it("na rua: um Entregue por parada aberta, o primeiro em destaque; soltar só com o link preso", () => {
    const list = houseGestures(house({
      deliver_actions: [
        { ref: "WEB-A47", code: "A47", action: action("A47 entregue") },
        { ref: "WEB-C03", code: "C03", action: action("C03 entregue") },
      ],
      release_action: action("Soltar o link"),
    }));
    expect(list.map((item) => [item.key, item.ref ?? "", item.primary])).toEqual([
      ["deliver:WEB-A47", "WEB-A47", true], ["deliver:WEB-C03", "WEB-C03", false], ["release", "", false],
    ]);
  });

  it("a TaOn não tem gesto da casa", () => {
    expect(houseGestures({ house: null })).toEqual([]);
  });

  it("os códigos riscam o que foi entregue e a quantidade diz pedido ou pedidos", () => {
    expect(houseCodes([{ code: "A47", done: true }, { code: "C03", done: false }])).toEqual([
      { code: "A47", done: true }, { code: "C03", done: false },
    ]);
    expect(ordersWord(1)).toBe("1 pedido");
    expect(ordersWord(2)).toBe("2 pedidos");
  });

  it("cada gesto tem a sua porta e a sua intenção", () => {
    expect(houseGesturePath("CASA-1", "deliver")).toBe("/api/v1/backstage/deliveries/couriers/rides/CASA-1/deliver/");
    expect(houseGestureResource("CASA-1", { key: "deliver:WEB-A47" })).toBe("house-ride:CASA-1:deliver:WEB-A47");
  });
});

describe("a corrida da casa no detalhe e na Saída (M3d)", () => {
  const ride = (key: string, refs: string[], house = true) =>
    ({
      key,
      stops: refs.map((ref) => ({ ref })),
      driver: { name: "Diego", phone: "(43) 99999-0000", vehicle: "", photo_url: "" },
      house: house ? { courier_name: "Diego" } : null,
    }) as never;

  it("Ligar para Diego só na corrida da casa e com telefone", () => {
    expect(callCourier(ride("CASA-1", ["A"]))).toEqual({ label: "Ligar para Diego", href: "tel:43999990000" });
    expect(callCourier(ride("776", ["A"], false))).toBeNull();
    expect(callCourier({ house: { courier_name: "Diego" }, driver: null } as never)).toBeNull();
  });

  it("os pedidos da corrida da casa viram um cartão no lugar do primeiro; TaOn e solto seguem", () => {
    const rows = [
      { card: { ref: "A" }, heading: "A coletar" },
      { card: { ref: "B" }, heading: "" },
      { card: { ref: "T" }, heading: "" },
      { card: { ref: "X" }, heading: "" },
    ];
    const out = withHouseRides(rows, [ride("CASA-1", ["A", "B"]), ride("776", ["T"], false)]);
    expect(out.map((row) => [row.card.ref, row.heading, (row.house as { key?: string } | undefined)?.key ?? ""])).toEqual([
      ["A", "A coletar", "CASA-1"], ["T", "", ""], ["X", "", ""],
    ]);
  });

  it("o rótulo da parte passa para o próximo quando o pedido que o tinha sai da coluna", () => {
    const rows = [
      { card: { ref: "X" }, heading: "A coletar" },
      { card: { ref: "A" }, heading: "Saiu para entrega" },
      { card: { ref: "B" }, heading: "" },
    ];
    const out = withHouseRides(rows, [ride("CASA-1", ["B", "A"])]);
    expect(out.map((row) => [row.card.ref, row.heading])).toEqual([["X", "A coletar"], ["A", "Saiu para entrega"]]);
    const moved = withHouseRides(
      [{ card: { ref: "B" }, heading: "Saiu para entrega" }, { card: { ref: "A" }, heading: "" }, { card: { ref: "Y" }, heading: "" }],
      [ride("CASA-1", ["A", "B"])],
    );
    expect(moved.map((row) => [row.card.ref, row.heading])).toEqual([["B", "Saiu para entrega"], ["Y", ""]]);
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

describe("o acerto do dia (M4)", () => {
  it("uma linha por entregador com rota fechada hoje, a frase do servidor", () => {
    const lines = toPayToday(crew([
      person("diego", "Diego", { to_pay_today: "A pagar a Diego hoje: R$ 27,00 (2 corridas)" }),
      person("rui", "Rui", { to_pay_today: "" }),
      person("ana", "Ana", { on_shift: false, to_pay_today: "A pagar a Ana hoje: R$ 12,00 (1 corrida)" }),
    ]));
    expect(lines).toEqual([
      { ref: "diego", text: "A pagar a Diego hoje: R$ 27,00 (2 corridas)" },
      { ref: "ana", text: "A pagar a Ana hoje: R$ 12,00 (1 corrida)" },
    ]);
  });

  it("sem o serviço da casa ativo, nada", () => {
    expect(toPayToday(crew([person("diego", "Diego", { to_pay_today: "A pagar a Diego hoje: R$ 12,00 (1 corrida)" })], { active: false }))).toEqual([]);
    expect(toPayToday(null)).toEqual([]);
  });
});
