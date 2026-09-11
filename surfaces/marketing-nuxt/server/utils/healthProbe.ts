export type ProbeState = "ok" | "fail";

export interface ReadinessResult {
  status: ProbeState;
  checks: {
    bff: "ok";
    api: ProbeState;
  };
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
