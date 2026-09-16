import { describe, expect, it } from "vitest";

import { attentionCount, endOfDayTiles, sessionActionTiles } from "~/presentation/cash";

// A antesala do turno aberto se organiza em três perguntas: quantas coisas
// pedem uma pessoa agora, quais ações viram tile, e o que só aparece para quem
// pode. As três são puras — a página só desenha.

describe("attentionCount — o número do 'Precisa de você'", () => {
  it("soma devoluções, pedidos de troco e contas na casa", () => {
    expect(attentionCount({
      pendingCashRefunds: [{}],
      pendingChangeRequests: [{}, {}],
      accountBalances: [{}, {}, {}],
    })).toBe(6);
  });

  it("zero quando não há nada — e zero é o que apaga o bloco", () => {
    expect(attentionCount({ pendingCashRefunds: [], pendingChangeRequests: [], accountBalances: [] })).toBe(0);
  });
});

describe("sessionActionTiles — a grade da Gaveta", () => {
  const base = { movementKinds: ["sangria", "suprimento"], canOpenDrawer: true, drawerUnavailableReason: "" };

  it("na ordem do balcão: troco, movimentos da capability, gaveta, fechar", () => {
    expect(sessionActionTiles(base).map((t) => t.key)).toEqual([
      "request_change", "movement:sangria", "movement:suprimento", "open_drawer", "close_shift",
    ]);
  });

  it("o movimento leva o tipo e o rótulo que o operador lê (Entrada/Saída)", () => {
    const tiles = sessionActionTiles(base);
    const cashOut = tiles.find((t) => t.key === "movement:sangria")!;
    expect(cashOut.action).toBe("movement");
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

  it("fechar caixa é destrutivo no tom, e só ele", () => {
    const tiles = sessionActionTiles(base);
    expect(tiles.find((t) => t.key === "close_shift")!.tone).toBe("destructive");
    expect(tiles.filter((t) => t.tone === "destructive")).toHaveLength(1);
  });
});

describe("endOfDayTiles — só para quem pode", () => {
  const closing = { already_closed: false, today_display: "16/09/2026", existing_closing_display: "" };

  it("sem auditoria e sem fechamento, lista vazia (a seção não existe)", () => {
    expect(endOfDayTiles({ canAuditCash: false, dayClosing: null })).toEqual([]);
  });

  it("o relatório é de quem audita", () => {
    const keys = endOfDayTiles({ canAuditCash: true, dayClosing: null }).map((t) => t.key);
    expect(keys).toEqual(["cash_report"]);
  });

  it("o fechamento diz o dia e vira 'Ver' depois de feito", () => {
    const pending = endOfDayTiles({ canAuditCash: false, dayClosing: closing })[0]!;
    expect(pending.label).toBe("Fazer o fechamento");
    expect(pending.description).toBe("16/09/2026 · contagem cega de sobras e perdas.");

    const done = endOfDayTiles({
      canAuditCash: false,
      dayClosing: { ...closing, already_closed: true, existing_closing_display: "Fechado às 19:40" },
    })[0]!;
    expect(done.label).toBe("Ver fechamento");
    expect(done.description).toBe("Fechado às 19:40");
  });
});
