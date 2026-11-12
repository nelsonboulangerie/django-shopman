// Contrato do Suporte no BFF da Central. Espelha `shopman/backstage/api/support.py`.
// `Pedido` é o Order do cliente; aqui só existe chamado, solicitação e compromisso.

export type SupportType = "question" | "complaint" | "bug" | "request" | "idea" | "decision";
export type SupportStatus =
  | "new"
  | "triage"
  | "waiting_requester"
  | "waiting_owner"
  | "approved"
  | "rejected"
  | "in_dev"
  | "resolved"
  | "closed"
  | "deferred";
export type SupportPriority = "low" | "normal" | "high" | "urgent";
export type SupportAudience = "internal" | "external";
export type SupportDecisionKind = "approve" | "reject" | "defer";

export interface SupportCapabilities {
  create: boolean;
  triage: boolean;
  view_all: boolean;
  approve: boolean;
  link_dev: boolean;
  audit: boolean;
}

export interface SupportMessage {
  id: number;
  author: string | null;
  body: string;
  internal_note: boolean;
  channel: string;
  ai_meta: Record<string, unknown>;
  created_at: string;
}

export interface SupportDecision {
  id: number;
  decided_by: string;
  decision: SupportDecisionKind;
  reason: string;
  created_at: string;
}

export interface SupportTicket {
  ref: string;
  audience: SupportAudience;
  type: SupportType;
  status: SupportStatus;
  priority: SupportPriority;
  subject: string;
  description: string;
  context: Record<string, unknown>;
  requester: string;
  requester_role: string;
  assignee: string | null;
  sla_due: string | null;
  review_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
  approval_basis: string;
  ledger_ref: string;
  resolution: string;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  messages?: SupportMessage[];
  decisions?: SupportDecision[];
}

export interface SupportTicketDetail extends SupportTicket {
  messages: SupportMessage[];
  decisions: SupportDecision[];
}

export interface SupportListResponse {
  tickets: SupportTicket[];
}
