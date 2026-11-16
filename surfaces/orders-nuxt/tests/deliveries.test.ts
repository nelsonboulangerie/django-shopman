import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import type {
  DeliveryRideProjection,
  DeliveryStopProjection,
} from "~/generated/ordersContract";
import {
  bagsWord,
  beforeHandoff,
  cancelConfirmation,
  needsMachine,
  nextFreeNumber,
  rideCalls,
  rideLetter,
  rideLine,
  whatsappLink,
} from "~/presentation/deliveries";
import { metroLines } from "~/presentation/metroLines";

function stop(ref: string, extra: Partial<DeliveryStopProjection> = {}): DeliveryStopProjection {
  return {
    ref, code: ref.slice(-3), customer: "Ana", place: "Centro", address: "", latitude: 0, longitude: 0,
    stage: "Pronto", volumes: 1, done: false, change_out_suggested_q: 0, needs_machine: false,
    change_label: "", group_refusal: "", error: "", dispatch_action: null, ...extra,
  };
}

function ride(extra: Partial<DeliveryRideProjection> = {}): DeliveryRideProjection {
  return {
    key: "1", number: 1, letter: "A", state: "searching", status_label: "", stops: [stop("NB-A01")], driver: null, position: null,
    called_at: "", called_by: "", pickup_eta_at: "", arrived_pickup_at: "", picked_up_at: "", delivery_eta_at: "",
    tracking_url: "", cost_display: "", bags: 1, undeclared: [], lead_ref: "NB-A01", back_action: null,
    back_lines: [], cancel_action: null, cancel_state: "", cancel_message: "", ...extra,
  };
}

describe("números das corridas", () => {
  it("dá o menor dos que o servidor diz livres, menos os das corridas em edição", () => {
    // 1, 2 e 4 estão na rua: o servidor manda só os livres (até a letra Z).
    const free = [3, 5, 6, 7, 8];
    expect(nextFreeNumber(free, [])).toBe(3);
    expect(nextFreeNumber(free, [3])).toBe(5);
    expect(nextFreeNumber(free, [3, 5, 6])).toBe(7);
  });

  it("a sétima corrida tem número próprio: o teto é o do servidor, não o das seis cores", () => {
    expect(nextFreeNumber([7, 8], [])).toBe(7);
  });

  it("nada quando o servidor não tem número livre, ou todos estão em edição", () => {
    expect(nextFreeNumber([], [])).toBeNull();
    expect(nextFreeNumber([2], [2])).toBeNull();
  });
});

describe("confirmação de cancelar a corrida", () => {
  const base = { label: "Cancelar corrida" };

  it("antes do aceite: a pergunta e o botão do servidor, sem motivo para escolher", () => {
    const copy = cancelConfirmation({
      ...base,
      confirmation: {
        required: true,
        description: "Cancelar a corrida B? A05 e C12 voltam para Aguardando.",
        confirm_label: "Cancelar a corrida B",
      },
    });
    expect(copy.question).toBe("Cancelar a corrida B? A05 e C12 voltam para Aguardando.");
    expect(copy.confirmLabel).toBe("Cancelar a corrida B");
    expect(copy.reasons).toEqual([]);
  });

  it("depois do aceite: cada motivo do servidor vira um botão, com o reason_id dele", () => {
    const copy = cancelConfirmation({
      ...base,
      confirmation: {
        required: true,
        description: "Cancelar a corrida B? A05 volta para Aguardando.",
        reason_question: "Por que cancelar a corrida B?",
        consequence: "A05 volta para Aguardando.",
        reasons: [
          { id: 12, label: "O entregador não está vindo" },
          { id: 37, label: "Está demorando demais" },
          { id: 40, label: "Não consegui falar com o entregador" },
        ],
      },
    });
    expect(copy.reasonQuestion).toBe("Por que cancelar a corrida B?");
    expect(copy.consequence).toBe("A05 volta para Aguardando.");
    expect(copy.reasons.map((reason) => [reason.id, reason.label])).toEqual([
      [12, "O entregador não está vindo"],
      [37, "Está demorando demais"],
      [40, "Não consegui falar com o entregador"],
    ]);
    expect(new Set(copy.reasons.map((reason) => reason.icon)).size).toBe(3);
  });

  it("motivo sem id inteiro ou sem rótulo não vira botão; sem frases, o texto mínimo", () => {
    const copy = cancelConfirmation({
      ...base,
      confirmation: { reasons: [{ id: "12", label: "x" }, { id: 37 }, { id: 40, label: "Não consegui falar com o entregador" }] },
    });
    expect(copy.reasons.map((reason) => reason.id)).toEqual([40]);
    expect(copy.question).toBe("Cancelar a corrida?");
    expect(copy.confirmLabel).toBe("Cancelar corrida");
    expect(cancelConfirmation(null).reasons).toEqual([]);
  });
});

describe("letra da corrida", () => {
  it("nomeia a corrida por letra, como o operador a chama", () => {
    expect([1, 2, 6, 26].map(rideLetter)).toEqual(["A", "B", "F", "Z"]);
    expect(rideLetter(27)).toBe("A");
  });

  it("sem número válido não inventa letra", () => {
    expect([0, -1, null, undefined, 1.5].map((n) => rideLetter(n as number))).toEqual(["", "", "", "", ""]);
  });

  // Decisão do dono (16/11/2026): corrida é LETRA em toda tela, nunca número. O número
  // segue no dado (escolhe a cor e a letra), mas não se escreve para o
  // operador: nem solto no template, nem depois de "corrida" numa frase ou aria-label.
  it("nenhuma tela do Gestor escreve o número da corrida", () => {
    const root = new URL("../app/", import.meta.url);
    const files = (readdirSync(root, { recursive: true }) as string[]).filter(
      (file) => /\.(vue|ts)$/.test(file) && !file.startsWith("generated/"),
    );
    const shown = /\{\{\s*(?:ride|r|openRide|activeRide)\.number\s*\}\}/;
    const spoken = /[Cc]orridas?\s+\$\{(?!\s*rideLetter\()[^}]*\bnumber\b/;
    const offenders = files.filter((file) => {
      const source = readFileSync(new URL(file, root), "utf8");
      return shown.test(source) || spoken.test(source);
    });
    expect(offenders).toEqual([]);
    expect(files.length).toBeGreaterThan(50);
  });
});

describe("chamar as corridas editadas", () => {
  const stops = [
    stop("NB-A01", { change_out_suggested_q: 2000 }),
    stop("NB-A02", { needs_machine: true }),
    stop("NB-A03"),
  ];

  it("um pedido vai sozinho; dois ou mais, numa corrida só; corrida vazia não vai", () => {
    const calls = rideCalls(
      [{ number: 1, refs: ["NB-A01", "NB-A02"] }, { number: 2, refs: ["NB-A03"] }, { number: 3, refs: [] }],
      stops,
      "machine:1",
    );
    expect(calls).toEqual([
      { kind: "group", number: 1, refs: ["NB-A01", "NB-A02"], change_out: { "NB-A01": "20,00" }, machine: "machine:1" },
      { kind: "single", number: 2, refs: ["NB-A03"], change_out: {}, machine: "" },
    ]);
  });

  it("chama na ordem dos números, para cada corrida ficar com a letra que mostrava", () => {
    const editing = [{ number: 3, refs: ["NB-A03"] }, { number: 2, refs: ["NB-A01", "NB-A02"] }];
    expect(rideCalls(editing, stops, "").map((call) => call.number)).toEqual([2, 3]);
    // A ordem da edição na tela não muda.
    expect(editing.map((ride) => ride.number)).toEqual([3, 2]);
  });

  it("a maquininha só é pergunta quando algum pedido é de cartão na porta", () => {
    expect(needsMachine([{ number: 1, refs: ["NB-A03"] }], stops)).toBe(false);
    expect(needsMachine([{ number: 1, refs: ["NB-A02"] }], stops)).toBe(true);
  });
});

describe("a corrida numa linha", () => {
  const now = Date.parse("2026-11-14T12:00:00-03:00");

  it("a caminho: quanto falta e as sacolas a separar", () => {
    const line = rideLine(
      ride({ state: "coming", driver: { name: "Rita", phone: "", vehicle: "" }, pickup_eta_at: "2026-11-14T12:06:00-03:00", bags: 3 }),
      now,
    );
    expect(line.title).toBe("Rita chega em 6 min");
    expect(line.hint).toBe("Separe 3 sacolas no balcão de saída");
  });

  it("pedido sem sacolas declaradas aparece pelo nome", () => {
    expect(rideLine(ride({ state: "coming", undeclared: ["A05"] }), now).hint).toBe(
      "Falta dizer quantas sacolas: A05",
    );
  });

  it("em rota: entregues e o término", () => {
    const line = rideLine(
      ride({ state: "route", stops: [stop("NB-A01", { done: true }), stop("NB-A02")] }),
      now,
    );
    expect(line.hint).toBe("1 de 2 entregues");
  });

  it("as sacolas importam só até sair da loja", () => {
    expect(beforeHandoff({ state: "atStore" })).toBe(true);
    expect(beforeHandoff({ state: "route" })).toBe(false);
    expect(bagsWord(1)).toBe("1 sacola");
  });
});

describe("WhatsApp do entregador", () => {
  it("só dígitos e o 55 do Brasil", () => {
    expect(whatsappLink("(43) 99999-0000")).toBe("https://wa.me/5543999990000");
    expect(whatsappLink("")).toBe("");
  });
});

describe("rotas como linhas de metrô", () => {
  it("o trecho comum corre lado a lado; fora dele, cada uma no seu eixo", () => {
    const [a, b] = metroLines(
      [
        { id: 1, points: [{ x: 0, y: 0 }, { x: 100, y: 0 }] },
        { id: 2, points: [{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 80 }] },
      ],
      5,
    );
    // as pontas ficam no lugar (encostam nos círculos)
    expect(a!.points[0]).toEqual({ x: 0, y: 0 });
    // a junta do trecho comum se afasta da outra linha
    const bJoint = b!.points[1]!;
    expect(Math.abs(bJoint.y)).toBeGreaterThan(1);
  });

  it("linhas que não se encontram ficam onde estão", () => {
    const lines = [
      { id: 1, points: [{ x: 0, y: 0 }, { x: 100, y: 0 }] },
      { id: 2, points: [{ x: 0, y: 0 }, { x: 0, y: 100 }] },
    ];
    expect(metroLines(lines, 5)).toEqual(lines);
  });
});
