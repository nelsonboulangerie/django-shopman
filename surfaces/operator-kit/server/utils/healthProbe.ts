// Probes do BFF das superfícies de operador — servidos pela layer em
// `server/routes/health/{live,ready}.get.ts`, então os oito apps respondem nas
// mesmas URLs sem copiar a rota.
//
// Duas perguntas, dois custos:
//   - `/health/live`  prova só que o processo Nitro atende. NÃO chama o Django.
//     É o health check da plataforma: roda a cada poucos segundos, e renderizar
//     a shell SSR (o `/` de antes) a cada chamada era custo sem informação nova.
//   - `/health/ready` inclui a prontidão do Django (`/health/ready/`). É para
//     smoke e diagnóstico, NUNCA para o health check da plataforma: tiraria o app
//     do ar por uma queda que reiniciar o Nitro não cura, e multiplicaria as
//     chamadas ao Django pelo número de apps.
//
// O corpo é deliberadamente pobre (`ok`/`fail`): nada do upstream é lido nem
// repassado, e o motivo de uma falha nunca sai na resposta pública.
import {
  getRequestIP,
  setResponseHeaders,
  setResponseStatus,
  type H3Event,
} from "h3";

export type ProbeState = "ok" | "fail";

export interface LivenessResult {
  status: "ok";
  checks: { bff: "ok" };
}

export interface ReadinessResult {
  status: ProbeState;
  checks: {
    bff: "ok";
    api: ProbeState;
  };
}

export interface RateLimitedResult {
  status: "error";
  checks: { rate_limit: "fail" };
}

interface RateBucket {
  openedAt: number;
  count: number;
}

export class ProbeRateLimiter {
  private readonly buckets = new Map<string, RateBucket>();

  constructor(
    private readonly limit = 600,
    private readonly windowMs = 60_000,
    private readonly maxClients = 2_048,
    private readonly now: () => number = Date.now,
  ) {}

  allow(clientKey: string): boolean {
    const now = this.now();
    const bucket = this.buckets.get(clientKey);
    if (!bucket || now - bucket.openedAt >= this.windowMs) {
      if (!bucket && this.buckets.size >= this.maxClients) {
        const oldest = this.buckets.keys().next().value as string | undefined;
        if (oldest !== undefined) this.buckets.delete(oldest);
      }
      this.buckets.set(clientKey, { openedAt: now, count: 1 });
      return true;
    }
    bucket.count += 1;
    this.buckets.delete(clientKey);
    this.buckets.set(clientKey, bucket);
    return bucket.count <= this.limit;
  }

  get trackedClients(): number {
    return this.buckets.size;
  }
}

export async function checkDjangoReadiness(
  djangoBaseUrl: string,
  fetchImpl: typeof fetch = globalThis.fetch,
  timeoutMs = 1_500,
): Promise<ReadinessResult> {
  const base = `${djangoBaseUrl.replace(/\/+$/, "")}/`;
  const target = new URL("/health/ready/", base).toString();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetchImpl(target, {
      method: "GET",
      headers: { accept: "application/json" },
      cache: "no-store",
      redirect: "error",
      signal: controller.signal,
    });
    const api: ProbeState = response.status === 200 ? "ok" : "fail";
    return {
      status: api,
      checks: { bff: "ok", api },
    };
  } catch {
    return {
      status: "fail",
      checks: { bff: "ok", api: "fail" },
    };
  } finally {
    clearTimeout(timeout);
  }
}

function startProbeResponse(
  event: H3Event,
  limiter: ProbeRateLimiter,
): RateLimitedResult | null {
  setResponseHeaders(event, {
    "cache-control": "no-store",
    "content-type": "application/json; charset=utf-8",
    "x-content-type-options": "nosniff",
  });
  if (limiter.allow(getRequestIP(event) || "unknown")) return null;
  setResponseStatus(event, 429);
  return { status: "error", checks: { rate_limit: "fail" } };
}

export function respondHealthLive(
  event: H3Event,
  limiter: ProbeRateLimiter,
): LivenessResult | RateLimitedResult {
  return startProbeResponse(event, limiter) ?? { status: "ok", checks: { bff: "ok" } };
}

export async function respondHealthReady(
  event: H3Event,
  limiter: ProbeRateLimiter,
  djangoBaseUrl: () => string,
  fetchImpl: typeof fetch = globalThis.fetch,
): Promise<ReadinessResult | RateLimitedResult> {
  const limited = startProbeResponse(event, limiter);
  if (limited) return limited;

  let result: ReadinessResult;
  try {
    result = await checkDjangoReadiness(djangoBaseUrl(), fetchImpl);
  } catch {
    // Upstream ausente/local/inseguro em produção: o resolver recusa com uma
    // mensagem de configuração, que não é assunto de resposta pública. Para o
    // probe é só "o Django não está alcançável".
    result = { status: "fail", checks: { bff: "ok", api: "fail" } };
  }
  if (result.status !== "ok") setResponseStatus(event, 503);
  return result;
}
