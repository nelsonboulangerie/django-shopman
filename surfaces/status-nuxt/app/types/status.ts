export type PublicStatusLevel = "operational" | "degraded" | "outage" | "maintenance" | "unknown";

export interface PublicStatusComponent {
  id: string;
  label: string;
  description: string;
  status: PublicStatusLevel;
}

export interface PublicStatusSnapshot {
  schemaVersion: 1;
  overall: PublicStatusLevel;
  observedAt: string | null;
  components: PublicStatusComponent[];
}

export interface PublicIncidentUpdate {
  at: string;
  status: "investigating" | "identified" | "monitoring" | "resolved";
  message: string;
}

export interface PublicIncident {
  id: string;
  title: string;
  startedAt: string;
  resolvedAt: string | null;
  affectedComponents: string[];
  updates: PublicIncidentUpdate[];
}
