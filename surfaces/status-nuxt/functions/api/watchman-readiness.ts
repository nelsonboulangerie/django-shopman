interface Env {
  OPERATIONS_READINESS_URL?: string;
  STOREFRONT_READINESS_URL?: string;
}

const READINESS_CHECKS = [
  {
    id: "web_operator",
    env: "OPERATIONS_READINESS_URL" as const,
    fallback: "https://api.boulangerie.com.br/health/ready/",
  },
  {
    id: "web_storefront",
    env: "STOREFRONT_READINESS_URL" as const,
    fallback: "https://api.boulangerie.com.br/api/v1/health/ready/",
  },
] as const;

type ProbeStatus = "operational" | "outage" | "unknown";

async function probe(url: string): Promise<ProbeStatus> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 4_000);
  try {
    const response = await fetch(url, {
      headers: { accept: "application/json", "user-agent": "Nelson-Watchman-Composite-Readiness/1" },
      signal: controller.signal,
      cf: { cacheTtl: 0 },
    });
    if (response.ok) return "operational";
    return response.status >= 500 ? "outage" : "unknown";
  } catch {
    return "outage";
  } finally {
    clearTimeout(timeout);
  }
}

export const onRequestGet: PagesFunction<Env> = async ({ env }) => {
  const checks = await Promise.all(READINESS_CHECKS.map(async (check) => ({
    id: check.id,
    status: await probe(env[check.env] || check.fallback),
  })));
  const failedChecks = checks.filter(({ status }) => status !== "operational").map(({ id }) => id);
  const healthy = failedChecks.length === 0;

  return Response.json({
    schemaVersion: 1,
    status: healthy ? "ok" : "unavailable",
    observedAt: new Date().toISOString(),
    checks,
    failedChecks,
  }, {
    status: healthy ? 200 : 503,
    headers: {
      "cache-control": "no-store",
      "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
      "referrer-policy": "no-referrer",
      "x-content-type-options": "nosniff",
      "x-frame-options": "DENY",
    },
  });
};
