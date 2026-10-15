interface Env {
  STOREFRONT_LIVENESS_URL?: string;
  OPERATIONS_LIVENESS_URL?: string;
}

type ProbeResult = "operational" | "outage" | "unknown";

const PUBLIC_COMPONENTS = [
  {
    id: "online_store",
    label: "Loja online",
    description: "Cardápio, carrinho e acompanhamento de pedidos.",
    env: "STOREFRONT_LIVENESS_URL" as const,
    fallback: "https://api.boulangerie.com.br/api/v1/health/live/",
  },
  {
    id: "service_operations",
    label: "Atendimento e operações",
    description: "Capacidades que sustentam o atendimento nas lojas.",
    env: "OPERATIONS_LIVENESS_URL" as const,
    fallback: "https://api.boulangerie.com.br/health/live/",
  },
] as const;

async function probe(url: string): Promise<ProbeResult> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 4_000);
  try {
    const response = await fetch(url, {
      headers: { accept: "application/json", "user-agent": "Nelson-Watchman-Public-Status/1" },
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
  const components = await Promise.all(PUBLIC_COMPONENTS.map(async (component) => ({
    id: component.id,
    label: component.label,
    description: component.description,
    status: await probe(env[component.env] || component.fallback),
  })));
  const statuses = components.map(({ status }) => status);
  const overall = statuses.includes("outage") ? "outage" : statuses.includes("unknown") ? "unknown" : "operational";

  return Response.json({
    schemaVersion: 1,
    overall,
    observedAt: new Date().toISOString(),
    components,
  }, {
    headers: {
      "cache-control": "public, max-age=15, s-maxage=30, stale-if-error=120",
      "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
      "referrer-policy": "no-referrer",
      "x-content-type-options": "nosniff",
      "x-frame-options": "DENY",
    },
  });
};
