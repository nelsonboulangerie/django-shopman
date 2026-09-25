import { describe, expect, it } from "vitest";

import { attentionCount, attentionTiles, endOfDayTiles, openShiftTile, sessionActionTiles } from "~/presentation/cash";

// A antesala do turno aberto se organiza em três perguntas: quantas coisas
// pedem uma pessoa agora, quais ações viram tile, e o que só aparece para quem
// pode. As três são puras — a página só desenha.

// ⚠️ `attentionCount` decide SE o bloco "Precisa de você" existe — não é mais
// crachá na tela. Somar devolução, pedido de troco e conta na casa num número
// só dizia ao operador que havia quatro coisas sem dizer de que natureza, e era
// por esse número que ele decidia se largava o balcão.
describe("attentionCount — se o bloco 'Precisa de você' existe", () => {
  it("soma devoluções, pedidos de troco e contas na casa", () => {
    expect(attentionCount({
      pendingCashRefunds: [{}],
      pendingChangeRequests: [{}, {}],
      accountBalances: [{}, {}, {}],
    })).toBe(6);
  });

  it("zero quando não há nada — e zero é o único uso dele na tela", () => {
    expect(attentionCount({ pendingCashRefunds: [], pendingChangeRequests: [], accountBalances: [] })).toBe(0);
  });
});

describe("sessionActionTiles — a grade da Gaveta", () => {
  const base = { movementKinds: ["sangria", "suprimento"], canOpenDrawer: true, drawerUnavailableReason: "" };

  it("na ordem do balcão: troco, movimentos da capability, gaveta — fechar mora no fim do expediente", () => {
    expect(sessionActionTiles(base).map((t) => t.key)).toEqual([
      "request_change", "movement:sangria", "movement:suprimento", "open_drawer",
    ]);
  });

  it("o movimento leva o tipo e o rótulo que o operador lê (Entrada/Saída)", () => {
    const tiles = sessionActionTiles(base);
    const cashOut = tiles.find((t) => t.key === "movement:sangria")!;
    expect(cashOut.kind).toBe("sangria");
    expect(cashOut.label).toBe("Saída de caixa");
    expect(cashOut.description).toContain("PIN do gerente");
    expect(cashOut.icon).toBe("lucide:banknote-arrow-down");
    const cashIn = tiles.find((t) => t.key === "movement:suprimento")!;
    expect(cashIn.label).toBe("Entrada de caixa");
    expect(cashIn.icon).toBe("lucide:banknote-arrow-up");
  });

  it("segue a capability: só os tipos que ela oferece viram tile", () => {
    const keys = sessionActionTiles({ ...base, movementKinds: ["sangria"] }).map((t) => t.key);
    expect(keys).toContain("movement:sangria");
    expect(keys).not.toContain("movement:suprimento");
  });

  it("sem caminho de software a gaveta NÃO some: desabilita e diz por quê", () => {
    // Sumir calado fez o dono achar que o PDV estava quebrado.
    const tile = sessionActionTiles({
      ...base, canOpenDrawer: false, drawerUnavailableReason: "Gaveta na impressora, sem agente nesta estação.",
    }).find((t) => t.key === "open_drawer")!;
    expect(tile.disabled).toBe(true);
    expect(tile.description).toBe("Gaveta na impressora, sem agente nesta estação.");
    // Com caminho, o tile convida e explica o registro.
    const withPath = sessionActionTiles(base).find((t) => t.key === "open_drawer")!;
    expect(withPath.disabled).toBe(false);
    expect(withPath.description).toBe("Sem venda, com motivo registrado");
  });

  it("nenhum card da gaveta é destrutivo: o que encerra é o fechar caixa, no fim do expediente", () => {
    expect(sessionActionTiles(base).filter((t) => t.tone === "destructive")).toHaveLength(0);
  });
});

describe("endOfDayTiles — o corredor da noite, só para quem pode", () => {
  const closing = { already_closed: false, today_display: "16/09/2026", existing_closing_display: "" };

  it("caixa fechado, sem auditoria e sem fechamento: lista vazia (a seção não existe)", () => {
    expect(endOfDayTiles({ canAuditCash: false, dayClosing: null })).toEqual([]);
  });

  it("na ordem do corredor: fechar caixa, fechamento do dia, relatório", () => {
    const keys = endOfDayTiles({ shiftOpen: true, canAuditCash: true, dayClosing: closing }).map((t) => t.key);
    expect(keys).toEqual(["close_shift", "day_closing", "cash_report"]);
  });

  it("fechar caixa só com turno aberto, e é destrutivo no tom — o único", () => {
    const tiles = endOfDayTiles({ shiftOpen: true, canAuditCash: false, dayClosing: null });
    expect(tiles.map((t) => t.key)).toEqual(["close_shift"]);
    expect(tiles[0]!.tone).toBe("destructive");
  });

  it("o relatório é de quem audita", () => {
    const keys = endOfDayTiles({ canAuditCash: true, dayClosing: null }).map((t) => t.key);
    expect(keys).toEqual(["cash_report"]);
  });

  it("o fechamento diz o dia, e diz que conta só o produzido; feito, vira 'Ver'", () => {
    const pending = endOfDayTiles({ canAuditCash: false, dayClosing: closing })[0]!;
    expect(pending.label).toBe("Fechamento do dia");
    expect(pending.description).toBe("16/09/2026 · contar as sobras do que a casa produz");
    expect(pending.badge).toBeUndefined();

    const done = endOfDayTiles({
      canAuditCash: false,
      dayClosing: { ...closing, already_closed: true, existing_closing_display: "Fechado às 19:40" },
    })[0]!;
    expect(done.label).toBe("Ver fechamento do dia");
    expect(done.description).toBe("Fechado às 19:40");
    expect(done.badge).toBe("Feito");
  });

  it("acabou de fechar o caixa com o dia por fechar: o fechamento vira o PRÓXIMO PASSO", () => {
    const next = endOfDayTiles({ justClosedShift: true, canAuditCash: false, dayClosing: closing })[0]!;
    expect(next.tone).toBe("primary");
    expect(next.badge).toBe("Próximo passo");
    // Dia já fechado não é próximo passo de ninguém.
    const done = endOfDayTiles({
      justClosedShift: true, canAuditCash: false, dayClosing: { ...closing, already_closed: true },
    })[0]!;
    expect(done.tone).toBe("default");
  });
});

describe("openShiftTile — o gesto de quem chega", () => {
  it("é o destaque, e diz o fundo sugerido", () => {
    const tile = openShiftTile({ floatSuggestionDisplay: "R$ 200,00", endOfDayInProgress: false });
    expect(tile.key).toBe("open_shift");
    expect(tile.tone).toBe("primary");
    expect(tile.description).toContain("R$ 200,00");
  });

  it("cede o destaque ao fim de dia em curso", () => {
    expect(openShiftTile({ floatSuggestionDisplay: "", endOfDayInProgress: true }).tone).toBe("default");
  });
});

describe("attentionTiles — um card por natureza, cada um com o seu número", () => {
  it("natureza sem pendência não vira card", () => {
    expect(attentionTiles({ pendingCashRefunds: [], pendingChangeRequests: [], accountBalances: [] })).toEqual([]);
  });

  it("devolução, troco e conta na casa, na ordem da urgência, com selo próprio", () => {
    const tiles = attentionTiles({ pendingCashRefunds: [{}], pendingChangeRequests: [{}, {}], accountBalances: [{}] });
    expect(tiles.map((t) => [t.key, t.badge])).toEqual([
      ["attention:refunds", "1"], ["attention:change", "2"], ["attention:accounts", "1"],
    ]);
    expect(tiles.every((t) => t.tone === "attention")).toBe(true);
    expect(tiles[0]!.label).toBe("Devolução em dinheiro");
    expect(tiles[1]!.label).toBe("Pedidos de troco");
  });
});
