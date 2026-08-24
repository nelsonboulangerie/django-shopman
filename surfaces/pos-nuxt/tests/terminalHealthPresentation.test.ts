// Saúde do terminal com a sonda promovida (presentation/terminalHealth).
//
// O contrato: o servidor projeta o que sabe (config), a sonda desta página
// responde o que só a estação alcança (o agente está de pé?), e a fusão nunca
// mente — nem "OK" de metadata quando o agente caiu, nem alarme num balcão que
// nunca teve agente.
import { describe, expect, it } from "vitest";

import type { POSTerminalComponentProjection } from "~/types/pos";
import {
  AGENT_OFFLINE_MESSAGE,
  terminalHealthRows,
  terminalOverallStatus,
} from "~/presentation/terminalHealth";

const FISCAL = { status: "ready", label: "Fiscal pronto", message: "" };

const component = (
  key: string,
  status: string,
  message = "",
): POSTerminalComponentProjection => ({ key, label: key, status, message });

describe("terminalHealthRows", () => {
  it("sem agente configurado não inventa linha nem mexe no servidor", () => {
    const rows = terminalHealthRows(
      [component("printer", "ready", "epson"), component("cash_drawer", "ready", "abre com a chave")],
      FISCAL,
      null,
    );

    expect(rows.map((row) => row.key)).toEqual(["printer", "cash_drawer", "fiscal"]);
    expect(rows[0]).toMatchObject({ status: "ready", message: "epson" });
  });

  it("sonda ainda no ar: linha de agente honesta, nada promovido", () => {
    const rows = terminalHealthRows(
      [component("cash_drawer", "deferred", "verificado na estação")],
      FISCAL,
      { ok: null, message: "" },
    );

    expect(rows[0]).toMatchObject({ key: "agent", status: "deferred" });
    expect(rows[1]).toMatchObject({ key: "cash_drawer", status: "deferred" });
  });

  it("agente de pé promove impressora e gaveta a verde de verdade", () => {
    const rows = terminalHealthRows(
      [
        component("printer", "absent", "não instalado"),
        component("cash_drawer", "deferred", "verificado na estação"),
        component("scanner", "absent", "não instalado"),
      ],
      FISCAL,
      { ok: true, message: "Fila TM-T20 respondendo." },
    );

    const byKey = Object.fromEntries(rows.map((row) => [row.key, row]));
    expect(byKey.agent).toMatchObject({ status: "ready", message: "Fila TM-T20 respondendo." });
    // Terminal com agente TEM caminho de impressão, declarado ou não em metadata.
    expect(byKey.printer).toMatchObject({ status: "ready" });
    expect(byKey.cash_drawer).toMatchObject({ status: "ready" });
    // O que o agente não mede continua como o servidor disse.
    expect(byKey.scanner).toMatchObject({ status: "absent", message: "não instalado" });
  });

  it("agente caído: estado honesto com o destino dos recibos, e o card acende", () => {
    const rows = terminalHealthRows(
      [component("printer", "ready", "epson"), component("cash_drawer", "deferred", "verificado na estação")],
      FISCAL,
      { ok: false, message: "O agente da estação não está rodando." },
    );

    const byKey = Object.fromEntries(rows.map((row) => [row.key, row]));
    expect(byKey.agent).toMatchObject({ status: "error", message: AGENT_OFFLINE_MESSAGE });
    expect(byKey.printer!.status).toBe("error");
    expect(byKey.cash_drawer!.status).toBe("error");
    expect(terminalOverallStatus(rows)).toBe("error");
  });

  it("warning de configuração do servidor não é curado por agente saudável", () => {
    const rows = terminalHealthRows(
      [component("printer", "warning", "largura de rolo inválida ('oitenta')")],
      FISCAL,
      { ok: true, message: "Fila TM-T20 respondendo." },
    );

    expect(rows.find((row) => row.key === "printer")).toMatchObject({
      status: "warning",
      message: "largura de rolo inválida ('oitenta')",
    });
  });
});

describe("terminalOverallStatus", () => {
  it("segue o critério do servidor: erro > atenção > pronto; ausente/na estação não acendem", () => {
    expect(terminalOverallStatus([component("a", "absent"), component("b", "deferred")])).toBe("ready");
    expect(terminalOverallStatus([component("a", "warning"), component("b", "ready")])).toBe("warning");
    expect(terminalOverallStatus([component("a", "warning"), component("b", "error")])).toBe("error");
  });

  it("a linha fiscal não participa do badge geral (ela tem badge próprio)", () => {
    const rows = terminalHealthRows([component("printer", "ready", "epson")], {
      status: "error",
      label: "Fiscal com falha",
      message: "",
    }, null);

    expect(terminalOverallStatus(rows)).toBe("ready");
  });
});
