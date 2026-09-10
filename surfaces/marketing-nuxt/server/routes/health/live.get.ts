import {
  getRequestIP,
  setResponseHeaders,
  setResponseStatus,
} from "h3";

const limiter = new ProbeRateLimiter();

export default defineEventHandler((event) => {
  setResponseHeaders(event, {
    "cache-control": "no-store",
    "content-type": "application/json; charset=utf-8",
    "x-content-type-options": "nosniff",
  });
  if (!limiter.allow(getRequestIP(event) || "unknown")) {
    setResponseStatus(event, 429);
    return { status: "error", checks: { rate_limit: "fail" } };
  }
  return { status: "ok", checks: { bff: "ok" } };
});
