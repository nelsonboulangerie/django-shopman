// Corpo da rota GET /health/capacity (server/routes/health/capacity.get.ts).
// Mora em utils para o teste exercitar autenticação e fallback sem subir o Nitro.
import { setResponseStatus, type H3Event } from "h3";
import {
  parseCapacityThresholds,
  reportCapacityToDjango,
  resolveOperatorServiceName,
  type CapacityReportResult,
} from "./capacityReport";
import { readContainerCapacity, type ContainerCapacityReading } from "./containerCapacity";
import { applyPrivateNoStore } from "./operatorSecurity";
import { applyOperatorSecurityHeaders } from "./securityHeaders";

export interface CapacityRouteDeps {
  read: () => Promise<ContainerCapacityReading>;
  report: (event: H3Event, service: string, reading: ContainerCapacityReading) => Promise<CapacityReportResult>;
}

const defaultCapacityRouteDeps: CapacityRouteDeps = {
  read: () => readContainerCapacity(),
  report: reportCapacityToDjango,
};

export async function handleCapacityRequest(event: H3Event, deps: CapacityRouteDeps = defaultCapacityRouteDeps) {
  applyOperatorSecurityHeaders(event);
  applyPrivateNoStore(event);

  const config = useRuntimeConfig(event);
  const service = resolveOperatorServiceName(config as Parameters<typeof resolveOperatorServiceName>[0]);
  const reading = await deps.read();

  let upstream: CapacityReportResult;
  try {
    upstream = await deps.report(event, service, reading);
  } catch {
    // Django fora: sem quem confirme o operador, não há leitura para mostrar.
    setResponseStatus(event, 502);
    return { detail: "Não foi possível conferir o acesso agora." };
  }

  if (upstream.status !== 200) {
    // 403 do Django (sessão caída ou sem permissão) passa adiante com o código,
    // para a tela distinguir; qualquer outra recusa vira 502, sem vazar corpo.
    const refused = upstream.status === 401 || upstream.status === 403;
    setResponseStatus(event, refused ? upstream.status : 502);
    const detail = typeof upstream.data?.detail === "string" ? upstream.data.detail : "Leitura de capacidade indisponível.";
    const error = refused && upstream.data?.error && typeof upstream.data.error === "object" ? upstream.data.error : undefined;
    return error ? { detail, error } : { detail };
  }

  return {
    service,
    available: reading.available,
    source: reading.source,
    memory: reading.memory,
    cpu: reading.cpu,
    measured_at: reading.measured_at,
    level: typeof upstream.data?.level === "string" ? upstream.data.level : "unknown",
    thresholds: parseCapacityThresholds(upstream.data?.thresholds),
  };
}
