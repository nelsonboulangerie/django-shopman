import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import type {
  DeliveryRideProjection,
  DeliveryStopProjection,
} from "~/generated/ordersContract";
import {
  backCheck,
  bagsWord,
  beforeHandoff,
  ridesNeedingMachine,
  nextFreeNumber,
  rideCalls,
  rideLetter,
  rideLine,
  rideChargeNotices,
  rideNotice,
  rideStale,
  toggleStop,
  whatsappLink,
} from "~/presentation/deliveries";
import { metroLines } from "~/presentation/metroLines";

function stop(ref: string, extra: Partial<DeliveryStopProjection> = {}): DeliveryStopProjection {
  return {
    ref, code: ref.slice(-3), customer: "Ana", place: "Centro", address: "", latitude: 0, longitude: 0,
    stage: "Pronto", volumes: 1, done: false, change_out_suggested_q: 0, needs_machine: false,
    change_label: "", group_refusal: "", error: "", dispatch_action: null, dispatch_again_action: null,
    charge_outdated: null, ...extra,
  };
}

function ride(extra: Partial<DeliveryRideProjection> = {}): DeliveryRideProjection {
  return {
    key: "1", number: 1, letter: "A", state: "searching", status_label: "", service_name: "TaOn", stops: [stop("NB-A01")], driver: null, position: null,
    called_at: "", called_by: "", pickup_eta_at: "", arrived_pickup_at: "", picked_up_at: "", delivery_eta_at: "",
    tracking_url: "", cost_display: "", cost_label: "", bags: 1, undeclared: [], lead_ref: "NB-A01", back_action: null,
    back_lines: [], cancel_action: null, cancel_state: "", cancel_message: "", reopened_at: "", reopened_driver: "",
    near_pickup_at: "", waited_pickup_at: "", reopened_reason: "", custody_line: "", open_too_long: false, sync_since: "", ...extra,
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
      { 1: "machine:1" },
    );
    expect(calls).toEqual([
      { kind: "group", number: 1, refs: ["NB-A01", "NB-A02"], change_out: { "NB-A01": "20,00" }, machine: "machine:1" },
      { kind: "single", number: 2, refs: ["NB-A03"], change_out: {}, machine: "" },
    ]);
  });

  it("chama na ordem dos números, para cada corrida ficar com a letra que mostrava", () => {
    const editing = [{ number: 3, refs: ["NB-A03"] }, { number: 2, refs: ["NB-A01", "NB-A02"] }];
    expect(rideCalls(editing, stops, {}).map((call) => call.number)).toEqual([2, 3]);
    // A ordem da edição na tela não muda.
    expect(editing.map((ride) => ride.number)).toEqual([3, 2]);
  });

  it("a maquininha só é pergunta quando algum pedido é de cartão na porta", () => {
    expect(ridesNeedingMachine([{ number: 1, refs: ["NB-A03"] }], stops)).toEqual([]);
    expect(ridesNeedingMachine([{ number: 1, refs: ["NB-A02"] }], stops)).toEqual([1]);
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
    expect(line.hint).toBe("Separe 3 sacolas para Rita");
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

describe("a corrida que segue chamada sem nada a fazer", () => {
  const now = Date.parse("2026-11-16T14:40:00-03:00");

  it("o entregador desistiu: diz quem e quando, e que a TaOn já procura outro", () => {
    const reopened = ride({
      state: "reopened", status_label: "Procurando outro entregador",
      reopened_at: "2026-11-16T14:32:00-03:00", reopened_driver: "Diego",
    });
    expect(rideLine(reopened, now)).toEqual({
      icon: "i-lucide-user-x", title: "Diego desistiu às 14h32", hint: "A TaOn já procura outro",
    });
    const notice = rideNotice(reopened, now);
    expect(notice?.title).toBe("Diego desistiu às 14h32. A TaOn já procura outro.");
    expect(notice?.description).toContain("Chamar de novo faria uma segunda corrida paga.");
    expect(notice?.key).toBe("reopened:2026-11-16T14:32:00-03:00");
    // A TaOn nem sempre manda o nome de quem saiu.
    expect(rideLine({ ...reopened, reopened_driver: "" }, now).title).toBe("O entregador desistiu às 14h32");
    // As sacolas seguem no balcão: ainda não saíram da loja.
    expect(beforeHandoff(reopened)).toBe(true);
  });

  it("a TaOn trocou o entregador: a mesma corrida, sem falha e sem chamar de novo", () => {
    const transfer = ride({
      state: "reopened", status_label: "Procurando outro entregador",
      reopened_at: "2026-11-16T14:32:00-03:00", reopened_driver: "Diego", reopened_reason: "transfer",
    });
    expect(rideLine(transfer, now)).toEqual({
      icon: "i-lucide-repeat", title: "A TaOn está trocando de entregador", hint: "A corrida continua a mesma",
    });
    expect(rideNotice(transfer, now)?.description).toContain("Chamar de novo faria uma segunda corrida paga.");
  });

  it("a TaOn juntou com outra corrida: nunca é \"Ninguém aceitou\"", () => {
    const grouped = ride({ state: "grouped", status_label: "Junto com outra corrida", stops: [stop("NB-E09")] });
    expect(rideLine(grouped, now)).toEqual({
      icon: "i-lucide-link", title: "A TaOn juntou com outra corrida", hint: "Ela já tem entregador",
    });
    expect(rideNotice(grouped, now)?.description).toBe(
      "E09 foi para uma corrida que já tem entregador. Não precisa chamar de novo.",
    );
    const two = ride({ state: "grouped", stops: [stop("NB-A47"), stop("NB-C03")] });
    expect(rideNotice(two, now)?.description).toBe(
      "A47 e C03 foram para uma corrida que já tem entregador. Não precisa chamar de novo.",
    );
  });

  it("corrida no caminho de sempre não tem aviso", () => {
    expect(rideNotice(ride({ state: "searching" }), now)).toBeNull();
    expect(rideNotice(ride({ state: "late" }), now)).toBeNull();
  });
});

describe("corrida em apuros", () => {
  const now = Date.parse("2026-11-16T14:40:00-03:00");
  const driver = { name: "Diego", phone: "", vehicle: "Honda CG prata · ABC1D23", photo_url: "" };

  it("nas redondezas (AN), a previsão já não importa: está chegando", () => {
    const near = ride({ state: "coming", driver, pickup_eta_at: "2026-11-16T14:50:00-03:00",
                        near_pickup_at: "2026-11-16T14:39:00-03:00" });
    expect(rideLine(near, now).title).toBe("Diego está chegando");
  });

  it("na loja, o relógio da espera conta e diz o que entregar", () => {
    const waiting = ride({
      state: "atStore", driver, arrived_pickup_at: "2026-11-16T14:33:00-03:00", bags: 2,
      stops: [stop("NB-A47", { volumes: 2 })],
    });
    expect(rideLine(waiting, now)).toEqual({
      icon: "i-lucide-store", title: "Diego espera na loja há 7 min", hint: "Entregue 2 sacolas de A47",
    });
    expect(rideNotice(waiting, now)).toBeNull();
    // A TaOn avisou que a espera passou do combinado (AW): vira aviso.
    const late = { ...waiting, waited_pickup_at: "2026-11-16T14:38:00-03:00" };
    const notice = rideNotice(late, now);
    expect(notice?.color).toBe("warning");
    expect(notice?.title).toBe("Diego espera na loja há 7 min.");
    expect(notice?.footer).toBeUndefined();
  });

  it("corrida aberta além da idade acompanhada avisa sem inventar falha", () => {
    const old = ride({ state: "route", driver, open_too_long: true });
    expect(rideNotice(old, now)?.title).toBe("Corrida aberta há muito tempo.");
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

describe("F4a: o toque em Aguardando", () => {
  const stops = [stop("NB-A01"), stop("NB-A02"), stop("NB-A03"), stop("NB-A04"), stop("NB-A05")];
  const free = [1, 2, 3];

  it("o primeiro toque abre a corrida e põe o pedido nela", () => {
    const result = toggleStop([], 0, "NB-A01", stops, 4, free);
    expect(result.editing).toEqual([{ number: 1, refs: ["NB-A01"] }]);
    expect(result.active).toBe(1);
    expect(result.notice).toBe("");
  });

  it("tocar de novo tira o pedido", () => {
    const result = toggleStop([{ number: 1, refs: ["NB-A01"] }], 1, "NB-A01", stops, 4, free);
    expect(result.editing[0]!.refs).toEqual([]);
  });

  it("o quinto toque não some: vai para a corrida B, e a frase diz", () => {
    const full = [{ number: 1, refs: ["NB-A01", "NB-A02", "NB-A03", "NB-A04"] }];
    const result = toggleStop(full, 1, "NB-A05", stops, 4, free);
    expect(result.editing).toEqual([
      { number: 1, refs: ["NB-A01", "NB-A02", "NB-A03", "NB-A04"] },
      { number: 2, refs: ["NB-A05"] },
    ]);
    expect(result.active).toBe(2);
    expect(result.notice).toBe("A corrida A já tem 4 pedidos. A05 foi para a corrida B.");
  });

  it("sem letra livre, a corrida cheia pede para tirar um", () => {
    const full = [{ number: 1, refs: ["NB-A01", "NB-A02", "NB-A03", "NB-A04"] }];
    const result = toggleStop(full, 1, "NB-A05", stops, 4, [1]);
    expect(result.editing).toEqual(full);
    expect(result.notice).toBe("A corrida A já tem 4 pedidos. Tire um para pôr A05.");
  });

  it("pedido recusado não entra, e o motivo vem do servidor", () => {
    const refused = [stop("NB-A01", { group_refusal: "O pedido A01 tem uma chamada sem resposta da TaOn. Confira na central antes." })];
    const result = toggleStop([], 0, "NB-A01", refused, 4, free);
    expect(result.editing).toEqual([]);
    expect(result.notice).toBe("O pedido A01 tem uma chamada sem resposta da TaOn. Confira na central antes.");
  });

  it("não muda a edição recebida (a tela troca pelo resultado)", () => {
    const editing = [{ number: 1, refs: ["NB-A01"] }];
    toggleStop(editing, 1, "NB-A02", stops, 4, free);
    expect(editing).toEqual([{ number: 1, refs: ["NB-A01"] }]);
  });
});

describe("F4a: o que o Painel diz, a página diz", () => {
  const now = Date.parse("2026-11-18T14:20:00-03:00");

  it("ninguém aceitou: com os minutos", () => {
    expect(rideLine(ride({ state: "late", called_at: "2026-11-18T14:08:00-03:00" }), now).title).toBe(
      "Ninguém aceitou em 12 min",
    );
    expect(rideLine(ride({ state: "late", called_at: "" }), now).title).toBe("Ninguém aceitou ainda");
  });

  it("separe as sacolas para quem vem buscar", () => {
    const coming = ride({ state: "coming", bags: 3, driver: { name: "Diego", phone: "", vehicle: "" } });
    expect(rideLine(coming, now).hint).toBe("Separe 3 sacolas para Diego");
    expect(rideLine(ride({ state: "coming", bags: 2 }), now).hint).toBe("Separe 2 sacolas no balcão de saída");
  });

  it("a TaOn parou de informar: a frase do Painel", () => {
    expect(rideStale(ride({ sync_since: "2026-11-18T14:05:00-03:00" }))).toBe(
      "A TaOn não informa a corrida desde 14h05.",
    );
    expect(rideStale(ride({ sync_since: "" }))).toBe("");
    expect(rideStale(ride({ state: "back", sync_since: "2026-11-18T14:05:00-03:00" }))).toBe("");
  });

  it("a cobrança que ficou para trás, por parada", () => {
    const outdated = { sent: "Cobrar R$ 50,00 em dinheiro · troco para R$ 100,00", current: "Cobrar R$ 58,00 em dinheiro", collected: true };
    const notices = rideChargeNotices(
      ride({ stops: [stop("NB-A01", { charge_outdated: outdated }), stop("NB-A02"), stop("NB-A03", { charge_outdated: outdated, done: true })] }),
    );
    expect(notices).toHaveLength(1);
    expect(notices[0]!.code).toBe("A01");
    expect(notices[0]!.title).toBe("A01: o pedido mudou depois da chamada");
    expect(notices[0]!.description).toContain("ligue para ele");
  });

  it("o retorno confere os pedidos da corrida e o que volta na mão", () => {
    expect(backCheck(ride({ stops: [stop("NB-A01"), stop("NB-A02")], back_lines: ["R$ 50,00 em dinheiro"] }))).toEqual({
      courier_return_orders: ["NB-A01", "NB-A02"],
      courier_return_lines: ["R$ 50,00 em dinheiro"],
    });
  });
});

describe("F4a: um toque nunca encerra nem cancela a corrida", () => {
  const page = readFileSync(new URL("../app/pages/delivery.vue", import.meta.url), "utf8");

  it("Entregador voltou passa pela conferência", () => {
    expect(page).toContain("<CourierBackDialog");
    expect(page).toMatch(/@back="backRide = ride"/);
    expect(page).not.toMatch(/@back="rideAction\(/);
  });

  it("Chamar de novo arma antes de chamar", () => {
    expect(page).toMatch(/@click="armedAgain = stop\.ref"/);
    expect(page).toContain("data-waiting-again-confirm");
  });

  it("a corrida encerrada se diz pela letra", () => {
    expect(page).not.toContain("Saída fechada");
    expect(page).toContain("encerrada.");
  });
});
