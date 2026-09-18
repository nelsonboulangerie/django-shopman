// Readiness do BFF: inclui a prontidão do Django. Para smoke e diagnóstico,
// NÃO para o health check da plataforma (ver server/utils/healthProbe.ts).
import { defineEventHandler } from "h3";
import { resolveDjangoBaseUrl } from "../../utils/djangoBaseUrl";
import { ProbeRateLimiter, respondHealthReady } from "../../utils/healthProbe";

const limiter = new ProbeRateLimiter();

export default defineEventHandler((event) =>
  respondHealthReady(event, limiter, () =>
    resolveDjangoBaseUrl(useRuntimeConfig(event).djangoBaseUrl),
  ),
);
