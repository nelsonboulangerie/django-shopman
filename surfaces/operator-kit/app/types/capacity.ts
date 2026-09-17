// Resposta de GET /health/capacity (server/utils/capacityRoute.ts).
export interface CapacityThresholds {
  attention_percent: number;
  critical_percent: number;
  sustain_minutes: number;
}

export interface CapacityResponse {
  service: string;
  available: boolean;
  /** Régua que valeu no contêiner: sistema do contêiner (cgroup) ou soma dos processos. */
  source: CapacitySource;
  memory: { used_bytes: number; limit_bytes: number | null; percent: number | null } | null;
  cpu: { percent: number | null; limit_cores: number; window_ms: number } | null;
  measured_at: string;
  level: string;
  thresholds: CapacityThresholds | null;
}

export type CapacitySource = "cgroup-v2" | "cgroup-v1" | "proc" | "none";

export type CapacityLevel = "unknown" | "normal" | "attention" | "critical";
