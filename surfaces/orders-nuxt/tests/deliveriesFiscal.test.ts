import { describe, expect, it } from "vitest";

import { deliveriesFiscalAlerts } from "../app/presentation/deliveriesFiscal";

// A nota fiscal na página Entregas (F10, ENT-19): só avisa, nunca segura a corrida.
const stop = (over: Record<string, unknown> = {}) => ({
  ref: "ORD-0412",
  code: "0412",
  done: false,
  fiscal_status: "authorized",
  danfe_state: "printed",
  danfe_problem: "",
  ...over,
});

describe("deliveriesFiscalAlerts", () => {
  it("nada a fazer, nenhum aviso", () => {
    expect(deliveriesFiscalAlerts({ waiting: [stop()], rides: [{ letter: "A", stops: [stop({ ref: "ORD-2" })] }] })).toEqual([]);
    expect(deliveriesFiscalAlerts(null)).toEqual([]);
  });

  it("NFC-e não autorizada numa corrida: diz qual corrida, que ela segue, e abre o pedido", () => {
    const [alert, ...rest] = deliveriesFiscalAlerts({
      waiting: [],
      rides: [{ letter: "B", stops: [stop({ fiscal_status: "failed" })] }],
    });
    expect(rest).toEqual([]);
    expect(alert).toEqual({
      id: "nfce:ORD-0412",
      color: "warning",
      icon: "i-lucide-file-x",
      title: "NFC-e não autorizada no pedido 0412",
      description: "Está na corrida B, que segue normalmente. O Reprocessar NFC-e fica no pedido.",
      action: { label: "Abrir o pedido", to: "/ORD-0412" },
    });
  });

  it("NFC-e não autorizada aguardando: a chamada segue", () => {
    const [alert] = deliveriesFiscalAlerts({ waiting: [stop({ fiscal_status: "failed" })], rides: [] });
    expect(alert!.description).toBe(
      "O pedido aguarda entregador, e a chamada segue normalmente. O Reprocessar NFC-e fica no pedido.",
    );
  });

  it("DANFE por imprimir traz o motivo do servidor; entregue, não avisa mais", () => {
    const problem = "A impressora de Balcão recusou a DANFE. Confira o papel e imprima de novo.";
    const alerts = deliveriesFiscalAlerts({
      waiting: [],
      rides: [
        {
          letter: "A",
          stops: [
            stop({ danfe_state: "not_printed", danfe_problem: problem }),
            stop({ ref: "ORD-9", code: "0009", danfe_state: "not_printed", done: true }),
          ],
        },
      ],
    });
    expect(alerts).toHaveLength(1);
    expect(alerts[0]).toMatchObject({
      id: "danfe:ORD-0412",
      title: "DANFE não impressa no pedido 0412",
      description: `Está na corrida A. ${problem}`,
      action: { label: "Abrir o pedido", to: "/ORD-0412" },
    });
  });

  it("DANFE sem motivo: diz onde está o gesto", () => {
    const [alert] = deliveriesFiscalAlerts({ waiting: [stop({ danfe_state: "not_printed" })], rides: [] });
    expect(alert!.description).toBe("O Imprimir DANFE fica no pedido.");
  });

  it("corridas primeiro, depois Aguardando; nenhum texto com travessão", () => {
    const alerts = deliveriesFiscalAlerts({
      waiting: [stop({ ref: "W", code: "W", fiscal_status: "failed" })],
      rides: [{ letter: "A", stops: [stop({ ref: "R", code: "R", fiscal_status: "failed", danfe_state: "not_printed" })] }],
    });
    expect(alerts.map((a) => a.id)).toEqual(["nfce:R", "danfe:R", "nfce:W"]);
    for (const alert of alerts) expect(`${alert.title} ${alert.description}`).not.toMatch(/[—–]/);
  });
});
