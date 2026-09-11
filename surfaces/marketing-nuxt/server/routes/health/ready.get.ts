import {
  getRequestIP,
  setResponseHeaders,
  setResponseStatus,
} from "h3";

const limiter = new ProbeRateLimiter();

export default defineEventHandler(async (event) => {
  setResponseHeaders(event, {
    "cache-control": "no-store",
    "content-type": "application/json; charset=utf-8",
    "x-content-type-options": "nosniff",
  });
  if (!limiter.allow(getRequestIP(event) || "unknown")) {
    setResponseStatus(event, 429);
    return { status: "error", checks: { rate_limit: "fail" } };
  }

  const config = useRuntimeConfig(event);
  const result = await checkDjangoReadiness(
    resolveDjangoBaseUrl(config.djangoBaseUrl),
  );
  if (result.status !== "ok") setResponseStatus(event, 503);
  return result;
});
