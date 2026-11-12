import { describe, expect, it } from "vitest";

import {
  canDecide,
  canLinkDev,
  canTriage,
  contextRows,
  filterTickets,
  formatAge,
  isTerminal,
  operatorSupportContext,
  statusColor,
  supportQueue,
  ticketTitle,
  typeLabel,
} from "../app/presentation/support";
import type { SupportCapabilities, SupportTicket } from "../app/types/support";

const caps = (over: Partial<SupportCapabilities> = {}): SupportCapabilities => ({
  create: true,
  triage: false,
  view_all: false,
  approve: false,
  link_dev: false,
  audit: false,
  ...over,
});

const ticket = (over: Partial<SupportTicket> = {}): SupportTicket => ({
  ref: "HELP-0001",
  audience: "internal",
  type: "question",
  status: "new",
  priority: "normal",
  subject: "",
  description: "A via do PDV não saiu",
  context: {},
  requester: "ana",
  requester_role: "operator",
  assignee: null,
  sla_due: null,
  review_at: null,
  approved_by: null,
  approved_at: null,
  approval_basis: "",
  ledger_ref: "",
  resolution: "",
  created_at: "2026-11-12T10:00:00Z",
  updated_at: "2026-11-12T10:00:00Z",
  closed_at: null,
  ...over,
});

describe("presentation/support", () => {
  it("distingue Atendimento de Solicitações", () => {
    expect(supportQueue("question")).toBe("atendimento");
    expect(supportQueue("complaint")).toBe("atendimento");
    expect(supportQueue("bug")).toBe("atendimento");
    expect(supportQueue("request")).toBe("solicitacao");
    expect(supportQueue("idea")).toBe("solicitacao");
    expect(supportQueue("decision")).toBe("solicitacao");
  });

  it("Solicitação não se chama Pedido", () => {
    expect(typeLabel("request")).toBe("Solicitação");
    expect(typeLabel("question")).toBe("Dúvida");
  });

  it("cor do estado segue a urgência da decisão", () => {
    expect(statusColor("waiting_owner")).toBe("warning");
    expect(statusColor("rejected")).toBe("error");
    expect(statusColor("resolved")).toBe("success");
    expect(statusColor("in_dev")).toBe("primary");
    expect(statusColor("closed")).toBe("neutral");
  });

  it("título cai na descrição quando não há assunto", () => {
    expect(ticketTitle(ticket({ subject: "  " }))).toBe("A via do PDV não saiu");
    expect(ticketTitle(ticket({ subject: "Impressora", description: "x" }))).toBe("Impressora");
  });

  it("idade é curta e legível", () => {
    const now = Date.parse("2026-11-12T12:00:00Z");
    expect(formatAge("2026-11-12T11:59:40Z", now)).toBe("agora");
    expect(formatAge("2026-11-12T11:48:00Z", now)).toBe("há 12 min");
    expect(formatAge("2026-11-12T09:00:00Z", now)).toBe("há 3 h");
    expect(formatAge("2026-11-09T12:00:00Z", now)).toBe("há 3 d");
  });

  it("contexto vira linhas legíveis, sem PII", () => {
    const rows = contextRows({
      app: "hub",
      route: "/pos",
      workstation_ref: "pdv-02",
      terminal_ref: "PDV-02",
      focus: { kind: "order", ref: "ORD-1" },
      empty: "",
    });

    expect(rows).toContainEqual({ label: "Tela", value: "/pos" });
    expect(rows).toContainEqual({ label: "Posto", value: "pdv-02" });
    expect(rows).toContainEqual({ label: "Terminal", value: "PDV-02" });
    expect(rows).toContainEqual({ label: "Em foco", value: "order ORD-1" });
    expect(rows.some((row) => row.label === "empty")).toBe(false);
  });

  it("só oferece triagem, decisão e DEV- a quem pode, no estado certo", () => {
    expect(canTriage(ticket({ status: "new" }), caps({ triage: true }))).toBe(true);
    expect(canTriage(ticket({ status: "approved" }), caps({ triage: true }))).toBe(false);
    expect(canDecide(ticket({ status: "waiting_owner" }), caps({ approve: true }))).toBe(true);
    expect(canDecide(ticket({ status: "waiting_owner" }), caps())).toBe(false);
    expect(canLinkDev(ticket({ status: "approved" }), caps({ link_dev: true }))).toBe(true);
    expect(canLinkDev(ticket({ status: "new" }), caps({ link_dev: true }))).toBe(false);
  });

  it("terminal não recebe resposta", () => {
    expect(isTerminal("resolved")).toBe(true);
    expect(isTerminal("closed")).toBe(true);
    expect(isTerminal("rejected")).toBe(true);
    expect(isTerminal("in_dev")).toBe(false);
  });

  it("contexto genérico carrega app, rota e extras", () => {
    expect(operatorSupportContext("kds", "/", { workstation_ref: "kds-01" })).toEqual({
      app: "kds",
      route: "/",
      workstation_ref: "kds-01",
    });
  });

  it("filtro separa as duas filas", () => {
    const list = [ticket({ ref: "HELP-1", type: "question" }), ticket({ ref: "HELP-2", type: "request" })];
    expect(filterTickets(list, "all")).toHaveLength(2);
    expect(filterTickets(list, "atendimento").map((item) => item.ref)).toEqual(["HELP-1"]);
    expect(filterTickets(list, "solicitacao").map((item) => item.ref)).toEqual(["HELP-2"]);
  });
});
