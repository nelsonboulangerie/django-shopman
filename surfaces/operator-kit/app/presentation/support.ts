// Presentation pura do Suporte na Central. Sem Nuxt, sem fetch.
// O chamado é o registro; a solicitação é o chamado que pede mudança; o
// compromisso (DEV-) é o trabalho. `Pedido` aqui nunca aparece: é o Order do cliente.

import type {
  SupportCapabilities,
  SupportPriority,
  SupportStatus,
  SupportTicket,
  SupportType,
} from "../types/support";

export const SUPPORT_TYPE_LABELS: Record<SupportType, string> = {
  question: "Dúvida",
  complaint: "Queixa",
  bug: "Defeito",
  request: "Solicitação",
  idea: "Ideia",
  decision: "Decisão",
};

export const SUPPORT_STATUS_LABELS: Record<SupportStatus, string> = {
  new: "Novo",
  triage: "Em triagem",
  waiting_requester: "Aguardando quem abriu",
  waiting_owner: "Aguardando o dono",
  approved: "Aprovado",
  rejected: "Recusado",
  in_dev: "Em desenvolvimento",
  resolved: "Resolvido",
  closed: "Fechado",
  deferred: "Adiado",
};

export const SUPPORT_PRIORITY_LABELS: Record<SupportPriority, string> = {
  low: "Baixa",
  normal: "Normal",
  high: "Alta",
  urgent: "Urgente",
};

export type SupportFilter = "all" | "atendimento" | "solicitacao";

export const SUPPORT_FILTERS: { id: SupportFilter; label: string }[] = [
  { id: "all", label: "Todos" },
  { id: "atendimento", label: "Atendimento" },
  { id: "solicitacao", label: "Solicitações" },
];

export type SupportQueue = "atendimento" | "solicitacao";

/** Atendimento resolve agora; Solicitações pedem decisão do dono. */
export function supportQueue(type: SupportType): SupportQueue {
  return type === "request" || type === "idea" || type === "decision"
    ? "solicitacao"
    : "atendimento";
}

export function statusLabel(status: SupportStatus): string {
  return SUPPORT_STATUS_LABELS[status] ?? status;
}

export function typeLabel(type: SupportType): string {
  return SUPPORT_TYPE_LABELS[type] ?? type;
}

export function priorityLabel(priority: SupportPriority): string {
  return SUPPORT_PRIORITY_LABELS[priority] ?? priority;
}

export function statusColor(
  status: SupportStatus,
): "primary" | "success" | "info" | "warning" | "error" | "neutral" {
  switch (status) {
    case "new":
    case "triage":
      return "info";
    case "waiting_owner":
    case "waiting_requester":
    case "deferred":
      return "warning";
    case "approved":
    case "in_dev":
      return "primary";
    case "resolved":
      return "success";
    case "rejected":
      return "error";
    default:
      return "neutral";
  }
}

export function isTerminal(status: SupportStatus): boolean {
  return status === "rejected" || status === "resolved" || status === "closed";
}

export function ticketTitle(ticket: Pick<SupportTicket, "subject" | "description">): string {
  const subject = ticket.subject.trim();
  if (subject) return subject;
  const first = ticket.description.split("\n", 1)[0]?.trim() ?? "";
  return first.length > 80 ? `${first.slice(0, 77)}...` : first || "Chamado sem título";
}

export function filterTickets(tickets: SupportTicket[], filter: SupportFilter): SupportTicket[] {
  if (filter === "all") return tickets;
  return tickets.filter((ticket) => supportQueue(ticket.type) === filter);
}

export function canTriage(ticket: Pick<SupportTicket, "status">, caps: SupportCapabilities): boolean {
  return caps.triage && ["new", "triage", "waiting_requester"].includes(ticket.status);
}

export function canDecide(ticket: Pick<SupportTicket, "status">, caps: SupportCapabilities): boolean {
  return caps.approve && ["new", "triage", "waiting_owner"].includes(ticket.status);
}

export function canLinkDev(ticket: Pick<SupportTicket, "status">, caps: SupportCapabilities): boolean {
  return caps.link_dev && ["approved", "in_dev"].includes(ticket.status);
}

export function canReply(ticket: Pick<SupportTicket, "status">): boolean {
  return !isTerminal(ticket.status);
}

/** Idade curta e legível: "agora", "há 12 min", "há 3 h", "há 2 d". */
export function formatAge(iso: string, nowMs: number): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const minutes = Math.max(0, Math.floor((nowMs - then) / 60_000));
  if (minutes < 1) return "agora";
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `há ${hours} h`;
  const days = Math.floor(hours / 24);
  return `há ${days} d`;
}

export interface ContextRow {
  label: string;
  value: string;
}

const CONTEXT_LABELS: Record<string, string> = {
  app: "App",
  route: "Tela",
  shop_ref: "Loja",
  sector_ref: "Setor",
  workstation_ref: "Posto",
  terminal_ref: "Terminal",
  device_ref: "Dispositivo",
  business_date: "Dia operacional",
  last_error_id: "Erro",
  app_version: "Versão",
  connectivity: "Conexão",
  request_id: "Requisição",
  actor_ref: "Pessoa",
};

/** O contexto que o sistema já sabe, em linhas legíveis. Refs, nunca PII. */
export function contextRows(context: Record<string, unknown> | null | undefined): ContextRow[] {
  if (!context || typeof context !== "object") return [];
  const rows: ContextRow[] = [];
  for (const [key, label] of Object.entries(CONTEXT_LABELS)) {
    const value = context[key];
    if (typeof value === "string" || typeof value === "number") {
      const text = String(value).trim();
      if (text) rows.push({ label, value: text });
    }
  }
  const focus = context.focus;
  if (focus && typeof focus === "object") {
    const kind = String((focus as Record<string, unknown>).kind ?? "").trim();
    const ref = String((focus as Record<string, unknown>).ref ?? "").trim();
    if (kind || ref) rows.push({ label: "Em foco", value: [kind, ref].filter(Boolean).join(" ") });
  }
  return rows;
}
